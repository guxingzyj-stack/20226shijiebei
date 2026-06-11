from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from model import db
from model.market import normalize_probs, shin_devig_three_way
from model.metrics import rps_three_way


MIN_REQUIRED_MATCHES = 30
WEIGHT_GRID = [step / 20 for step in range(21)]
FINISHED_STATUSES = {"finished", "completed", "已完赛", "完赛"}


@dataclass(frozen=True)
class MatchRow:
    match_id: str
    status: str
    kickoff_at: datetime | None
    result_home: int | None
    result_away: int | None


@dataclass(frozen=True)
class OddsRow:
    match_id: str
    play_type: str
    odds: dict[str, float]
    fetched_at: datetime


@dataclass(frozen=True)
class PredictionRow:
    match_id: str
    model_version: int
    p_home: float
    p_draw: float
    p_away: float
    created_at: datetime | None


def status() -> dict[str, Any]:
    try:
        with db.get_conn() as conn:
            data = load_production_rows(conn)
    except Exception as exc:
        return _not_checked(f"DATABASE unavailable: {exc}")
    return build_prospective_calibration_summary(**data)


def run(dry_run: bool = True) -> dict[str, Any]:
    result = status()
    result["dry_run"] = dry_run
    result["would_write_db"] = False
    return result


def load_production_rows(conn: psycopg.Connection) -> dict[str, list[Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT match_id, status, kickoff_at, result_home, result_away FROM matches ORDER BY kickoff_at NULLS LAST")
        matches = [
            MatchRow(
                match_id=str(row["match_id"]),
                status=str(row.get("status") or ""),
                kickoff_at=row.get("kickoff_at"),
                result_home=_optional_int(row.get("result_home")),
                result_away=_optional_int(row.get("result_away")),
            )
            for row in cur.fetchall()
        ]
        cur.execute("SELECT match_id, play_type, odds, fetched_at FROM odds_snapshots WHERE play_type IN ('had', 'hhad') ORDER BY fetched_at")
        odds = [
            OddsRow(
                match_id=str(row["match_id"]),
                play_type=str(row.get("play_type") or ""),
                odds={str(key): float(value) for key, value in dict(row.get("odds") or {}).items()},
                fetched_at=row["fetched_at"],
            )
            for row in cur.fetchall()
        ]
        cur.execute("SELECT match_id, model_version, p_home, p_draw, p_away, created_at FROM predictions ORDER BY created_at")
        predictions = [
            PredictionRow(
                match_id=str(row["match_id"]),
                model_version=int(row["model_version"]),
                p_home=float(row["p_home"]),
                p_draw=float(row["p_draw"]),
                p_away=float(row["p_away"]),
                created_at=row.get("created_at"),
            )
            for row in cur.fetchall()
        ]
    return {"matches": matches, "odds": odds, "predictions": predictions}


def build_prospective_calibration_summary(
    matches: list[MatchRow],
    odds: list[OddsRow],
    predictions: list[PredictionRow],
    min_required_matches: int = MIN_REQUIRED_MATCHES,
) -> dict[str, Any]:
    odds_by_match = _group_by_match(odds)
    predictions_by_match = _group_by_match(predictions)
    skipped = {
        "not_finished": 0,
        "missing_result": 0,
        "missing_kickoff": 0,
        "missing_had_market_odds": 0,
        "missing_prediction": 0,
        "unsupported_hhad_only": 0,
    }
    evaluable: list[dict[str, Any]] = []
    hhad_available_count = 0
    leakage_risk = False
    for match in matches:
        if match.status not in FINISHED_STATUSES:
            skipped["not_finished"] += 1
            continue
        if match.result_home is None or match.result_away is None:
            skipped["missing_result"] += 1
            continue
        if match.kickoff_at is None:
            skipped["missing_kickoff"] += 1
            continue
        close_odds = _latest_pre_kickoff_had(odds_by_match.get(match.match_id, []), match.kickoff_at)
        if close_odds is None:
            if _latest_pre_kickoff_hhad(odds_by_match.get(match.match_id, []), match.kickoff_at) is not None:
                hhad_available_count += 1
                skipped["unsupported_hhad_only"] += 1
            else:
                skipped["missing_had_market_odds"] += 1
            continue
        prediction = _latest_pre_kickoff_prediction(predictions_by_match.get(match.match_id, []), match.kickoff_at)
        if prediction is None:
            skipped["missing_prediction"] += 1
            if any(row.created_at is None for row in predictions_by_match.get(match.match_id, [])):
                leakage_risk = True
            continue
        if prediction.created_at is None:
            leakage_risk = True
            skipped["missing_prediction"] += 1
            continue
        market = shin_devig_three_way({key: float(close_odds.odds[key]) for key in ("3", "1", "0")})
        dc = normalize_probs({"3": prediction.p_home, "1": prediction.p_draw, "0": prediction.p_away})
        outcome = _outcome(match.result_home, match.result_away)
        evaluable.append({"market": market, "dc": dc, "outcome": outcome, "model_version": prediction.model_version})
    metrics = _metrics(evaluable) if len(evaluable) >= min_required_matches and not leakage_risk else None
    partial = _metrics(evaluable) if evaluable else None
    result = "PASS" if metrics is not None else "WAIT"
    blocker = None
    if result == "WAIT":
        if leakage_risk:
            blocker = "leakage_risk"
        elif len(evaluable) < min_required_matches:
            blocker = "insufficient_finished_matches"
        else:
            blocker = "waiting_for_finished_matches"
    return {
        "data_availability": {
            "total_matches": len(matches),
            "finished_matches": sum(1 for match in matches if match.status in FINISHED_STATUSES),
            "matches_with_had_close_odds": _count_matches_with_had_close_odds(matches, odds_by_match),
            "matches_with_predictions": _count_matches_with_pre_kickoff_predictions(matches, predictions_by_match),
            "evaluable_matches": len(evaluable),
            "min_required_matches": min_required_matches,
            "hhad_available_count": hhad_available_count,
        },
        "skips": skipped,
        "metrics": {
            "market_rps": metrics["market_rps"] if metrics else None,
            "dc_rps": metrics["dc_rps"] if metrics else None,
            "blended_rps": metrics["blended_rps"] if metrics else None,
            "best_w_dc": metrics["best_w_dc"] if metrics else None,
            "partial_metrics_available": partial is not None,
            "partial_metrics": partial,
            "not_for_production_weight_change": True,
        },
        "leakage": {
            "leakage_risk": leakage_risk,
            "prediction_time_policy": "prediction.created_at must be <= kickoff_at; missing created_at is leakage risk",
            "odds_time_policy": "use latest HAD odds_snapshot with fetched_at <= kickoff_at",
        },
        "result": result,
        "blocker": blocker,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    market_scores = [_rps(row["market"], row["outcome"]) for row in rows]
    dc_scores = [_rps(row["dc"], row["outcome"]) for row in rows]
    blended_scores_by_weight: dict[float, list[float]] = {weight: [] for weight in WEIGHT_GRID}
    for row in rows:
        for weight in WEIGHT_GRID:
            blended = normalize_probs({key: weight * row["dc"][key] + (1 - weight) * row["market"][key] for key in ("3", "1", "0")})
            blended_scores_by_weight[weight].append(_rps(blended, row["outcome"]))
    means = {weight: _mean(scores) for weight, scores in blended_scores_by_weight.items()}
    best_w = min(means, key=lambda weight: (means[weight], weight))
    return {"market_rps": _mean(market_scores), "dc_rps": _mean(dc_scores), "blended_rps": means[best_w], "best_w_dc": best_w}


def _latest_pre_kickoff_had(rows: list[OddsRow], kickoff_at: datetime) -> OddsRow | None:
    candidates = [row for row in rows if row.play_type == "had" and row.fetched_at <= kickoff_at and set(row.odds) >= {"3", "1", "0"}]
    return max(candidates, key=lambda row: row.fetched_at) if candidates else None


def _latest_pre_kickoff_hhad(rows: list[OddsRow], kickoff_at: datetime) -> OddsRow | None:
    candidates = [row for row in rows if row.play_type == "hhad" and row.fetched_at <= kickoff_at]
    return max(candidates, key=lambda row: row.fetched_at) if candidates else None


def _latest_pre_kickoff_prediction(rows: list[PredictionRow], kickoff_at: datetime) -> PredictionRow | None:
    if any(row.created_at is None for row in rows):
        return None
    candidates = [row for row in rows if row.created_at is not None and row.created_at <= kickoff_at]
    return max(candidates, key=lambda row: row.created_at) if candidates else None


def _count_matches_with_had_close_odds(matches: list[MatchRow], odds_by_match: dict[str, list[OddsRow]]) -> int:
    return sum(1 for match in matches if match.kickoff_at is not None and _latest_pre_kickoff_had(odds_by_match.get(match.match_id, []), match.kickoff_at) is not None)


def _count_matches_with_pre_kickoff_predictions(matches: list[MatchRow], predictions_by_match: dict[str, list[PredictionRow]]) -> int:
    return sum(1 for match in matches if match.kickoff_at is not None and _latest_pre_kickoff_prediction(predictions_by_match.get(match.match_id, []), match.kickoff_at) is not None)


def _group_by_match(rows: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.match_id, []).append(row)
    return grouped


def _rps(probs: dict[str, float], outcome: str) -> float:
    return rps_three_way(probs["3"], probs["1"], probs["0"], outcome)


def _outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "3"
    if home_score == away_score:
        return "1"
    return "0"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _not_checked(reason: str) -> dict[str, Any]:
    return {
        "data_availability": {
            "total_matches": "NOT_CHECKED",
            "finished_matches": "NOT_CHECKED",
            "matches_with_had_close_odds": "NOT_CHECKED",
            "matches_with_predictions": "NOT_CHECKED",
            "evaluable_matches": 0,
            "min_required_matches": MIN_REQUIRED_MATCHES,
        },
        "skips": {},
        "metrics": {
            "market_rps": None,
            "dc_rps": None,
            "blended_rps": None,
            "best_w_dc": None,
            "partial_metrics_available": False,
            "not_for_production_weight_change": True,
        },
        "leakage": {
            "leakage_risk": True,
            "prediction_time_policy": "NOT_CHECKED",
            "odds_time_policy": "NOT_CHECKED",
        },
        "result": "WAIT",
        "blocker": reason,
    }


def print_report(report: dict[str, Any]) -> None:
    print("P1-C Prime Prospective Calibration Report")
    print("")
    print("1. Data availability")
    for key, value in report["data_availability"].items():
        print(f"- {key}: {value}")
    print("")
    print("2. Skips")
    for key, value in report["skips"].items():
        print(f"- {key}: {value}")
    print("")
    print("3. Metrics")
    for key, value in report["metrics"].items():
        print(f"- {key}: {value}")
    print("")
    print("4. Leakage")
    for key, value in report["leakage"].items():
        print(f"- {key}: {value}")
    print("")
    print("5. Result")
    print(f"- result: {report['result']}")
    print(f"- blocker: {report['blocker']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C prime prospective calibration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    report = status() if args.command == "status" else run(dry_run=args.dry_run)
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
