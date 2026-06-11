from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from model.market import normalize_probs, proportional_devig
from model.metrics import rps_three_way


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p1c"
MANUAL_MARKET_ODDS_TEMPLATE = DATA_DIR / "manual_historical_market_odds_template.csv"
MIN_BACKTEST_MATCHES = 30
WEIGHT_GRID = [step / 20 for step in range(21)]
REQUIRED_COLUMNS = {
    "match_date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "market_home_odds",
    "market_draw_odds",
    "market_away_odds",
    "bookmaker",
    "snapshot_time",
    "source",
}


@dataclass(frozen=True)
class BacktestRow:
    match_date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    market_home_odds: float
    market_draw_odds: float
    market_away_odds: float
    bookmaker: str
    snapshot_time: str
    source: str

    @property
    def outcome(self) -> str:
        if self.home_score > self.away_score:
            return "3"
        if self.home_score == self.away_score:
            return "1"
        return "0"


def discover_sources() -> dict[str, Any]:
    return {
        "the_odds_api": {
            "api_key_present": bool(os.getenv("THE_ODDS_API_KEY")),
            "status": "CONFIGURED" if os.getenv("THE_ODDS_API_KEY") else "NOT_AVAILABLE",
            "note": "historical support must be verified with quota-safe dry-run",
        },
        "football_data_csv": {
            "status": "NOT_AVAILABLE",
            "note": "no verified national-team historical odds CSV bundled; club leagues are not accepted",
        },
        "manual_csv": {
            "template_exists": MANUAL_MARKET_ODDS_TEMPLATE.exists(),
            "path": str(MANUAL_MARKET_ODDS_TEMPLATE),
        },
    }


def validate_manual_csv(path: Path = MANUAL_MARKET_ODDS_TEMPLATE) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "rows": 0, "missing_columns": sorted(REQUIRED_COLUMNS), "errors": [f"missing file: {path}"]}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        rows = [dict(row) for row in reader]
    errors = [] if missing else _validate_rows(rows)
    return {"ok": not missing and not errors, "rows": len(rows), "missing_columns": missing, "errors": errors}


def load_manual_rows(path: Path = MANUAL_MARKET_ODDS_TEMPLATE) -> list[BacktestRow]:
    report = validate_manual_csv(path)
    if not report["ok"]:
        raise ValueError(f"manual historical market CSV validation failed: {report}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [_row_from_csv(raw) for raw in csv.DictReader(handle)]


def market_probs(row: BacktestRow) -> dict[str, float]:
    return proportional_devig(
        {
            "3": row.market_home_odds,
            "1": row.market_draw_odds,
            "0": row.market_away_odds,
        }
    )


def neutral_dc_probs(row: BacktestRow) -> dict[str, float]:
    _ = row
    return {"3": 1 / 3, "1": 1 / 3, "0": 1 / 3}


def blend_probs(dc: dict[str, float], market: dict[str, float], w_dc: float) -> dict[str, float]:
    w_market = 1 - w_dc
    return normalize_probs({key: w_dc * dc[key] + w_market * market[key] for key in ("3", "1", "0")})


def run_backtest(
    rows: list[BacktestRow],
    dc_prob_fn: Callable[[BacktestRow], dict[str, float]] = neutral_dc_probs,
    min_matches: int = MIN_BACKTEST_MATCHES,
) -> dict[str, Any]:
    if len(rows) < min_matches:
        return {
            "status": "insufficient_historical_market_data",
            "result": "WAIT",
            "rows": len(rows),
            "required_rows": min_matches,
            "market_rps": None,
            "dc_rps": None,
            "blended_rps": None,
            "best_w_dc": None,
            "blocker": "real historical market odds sample is too small",
        }
    market_scores: list[float] = []
    dc_scores: list[float] = []
    blended_scores_by_weight: dict[float, list[float]] = {weight: [] for weight in WEIGHT_GRID}
    for row in rows:
        mkt = market_probs(row)
        dc = normalize_probs(dc_prob_fn(row))
        market_scores.append(_rps(mkt, row.outcome))
        dc_scores.append(_rps(dc, row.outcome))
        for weight in WEIGHT_GRID:
            blended_scores_by_weight[weight].append(_rps(blend_probs(dc, mkt, weight), row.outcome))
    means = {weight: _mean(scores) for weight, scores in blended_scores_by_weight.items()}
    best_w_dc = min(means, key=lambda weight: (means[weight], weight))
    return {
        "status": "ok",
        "result": "PASS",
        "rows": len(rows),
        "required_rows": min_matches,
        "market_rps": _mean(market_scores),
        "dc_rps": _mean(dc_scores),
        "blended_rps": means[best_w_dc],
        "best_w_dc": best_w_dc,
        "blocker": None,
    }


def run_manual_backtest(dry_run: bool = False, path: Path = MANUAL_MARKET_ODDS_TEMPLATE) -> dict[str, Any]:
    validation = validate_manual_csv(path)
    if not validation["ok"]:
        return {
            "status": "validation_failed",
            "result": "FAIL",
            "validation": validation,
            "would_write_db": False,
        }
    rows = load_manual_rows(path)
    result = run_backtest(rows)
    result["dry_run"] = dry_run
    result["would_write_db"] = False
    result["source"] = "manual_csv"
    result["validation"] = validation
    return result


def fetch_odds_api_dry_run() -> dict[str, Any]:
    if not os.getenv("THE_ODDS_API_KEY"):
        return {"status": "NOT_AVAILABLE", "reason": "THE_ODDS_API_KEY is not set", "would_write_db": False}
    return {
        "status": "DRY_RUN_ONLY",
        "reason": "key is present; historical quota/support must be checked outside tests without printing the key",
        "would_write_db": False,
    }


def _row_from_csv(row: dict[str, str]) -> BacktestRow:
    return BacktestRow(
        match_date=str(row["match_date"]).strip(),
        home_team=str(row["home_team"]).strip(),
        away_team=str(row["away_team"]).strip(),
        home_score=int(str(row["home_score"]).strip()),
        away_score=int(str(row["away_score"]).strip()),
        market_home_odds=float(str(row["market_home_odds"]).strip()),
        market_draw_odds=float(str(row["market_draw_odds"]).strip()),
        market_away_odds=float(str(row["market_away_odds"]).strip()),
        bookmaker=str(row["bookmaker"]).strip(),
        snapshot_time=str(row["snapshot_time"]).strip(),
        source=str(row["source"]).strip(),
    )


def _validate_rows(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    required_values = REQUIRED_COLUMNS
    for index, row in enumerate(rows, start=2):
        for column in required_values:
            if not str(row.get(column) or "").strip():
                errors.append(f"row {index}: missing required {column}")
        for column in ("home_score", "away_score"):
            _validate_int(row, column, index, errors)
        for column in ("market_home_odds", "market_draw_odds", "market_away_odds"):
            value = _validate_float(row, column, index, errors)
            if value is not None and value <= 1:
                errors.append(f"row {index}: {column} must be greater than 1")
        _validate_datetime(row, "match_date", index, errors, date_only=True)
        _validate_datetime(row, "snapshot_time", index, errors, date_only=False)
    return errors


def _validate_int(row: dict[str, str], column: str, index: int, errors: list[str]) -> None:
    try:
        int(str(row.get(column) or "").strip())
    except ValueError:
        errors.append(f"row {index}: invalid integer {column}")


def _validate_float(row: dict[str, str], column: str, index: int, errors: list[str]) -> float | None:
    try:
        return float(str(row.get(column) or "").strip())
    except ValueError:
        errors.append(f"row {index}: invalid numeric {column}")
        return None


def _validate_datetime(row: dict[str, str], column: str, index: int, errors: list[str], date_only: bool) -> None:
    value = str(row.get(column) or "").strip()
    if not value:
        return
    try:
        if date_only:
            datetime.fromisoformat(value).date()
        else:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"row {index}: invalid datetime {column}")


def _rps(probs: dict[str, float], outcome: str) -> float:
    return rps_three_way(probs["3"], probs["1"], probs["0"], outcome)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C historical market backtest")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("discover-sources")
    subparsers.add_parser("validate")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--dry-run", action="store_true")
    subparsers.add_parser("report")
    fetch_parser = subparsers.add_parser("fetch-odds-api")
    fetch_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "discover-sources":
        result = discover_sources()
    elif args.command == "validate":
        result = validate_manual_csv()
    elif args.command == "run":
        result = run_manual_backtest(dry_run=args.dry_run)
    elif args.command == "report":
        result = run_manual_backtest(dry_run=True)
    elif args.command == "fetch-odds-api":
        result = fetch_odds_api_dry_run()
    else:
        parser.error(f"unknown command: {args.command}")
    print(result)
    return 0 if result.get("result") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
