from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from model import p3_ingest


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
DEFAULT_SOURCE_FILE = DATA_DIR / "real_performance_squad_source.csv"
DEFAULT_RAW_DIR = DATA_DIR / "raw_performance"
DEFAULT_OUT = DATA_DIR / "real_performance_squad.csv"

OUTPUT_COLUMNS = [
    "team",
    "player_name",
    "club",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "source",
    "retrieved_at",
    "confidence",
    "notes",
]


def build_real_performance_csv(
    out: Path = DEFAULT_OUT,
    source_file: Path = DEFAULT_SOURCE_FILE,
    raw_dir: Path = DEFAULT_RAW_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    source_paths = _source_paths(source_file, raw_dir)
    if not source_paths:
        return {
            "ok": False,
            "result": "WAIT",
            "p3_mode": p3_ingest.P3_MODE,
            "requires_xg_xa": p3_ingest.REQUIRES_XG_XA,
            "xg_xa_optional": p3_ingest.XG_XA_OPTIONAL,
            "light_required_fields": p3_ingest.LIGHT_REQUIRED_FIELDS,
            "reason": "no_legal_recent_performance_source",
            "source_files": [],
            "would_write_db": False,
            "would_write_csv": False,
            "rows": 0,
            "teams": 0,
            "coverage_by_team": {},
            "teams_below_70_percent": [],
            "unmatched_players": [],
            "fake_or_example_rows_detected": False,
            "candidate_w_gbm": 0,
            "production_w_gbm": p3_ingest.PRODUCTION_W_GBM,
            "output": str(out),
        }
    rows, read_errors = _read_source_rows(source_paths)
    normalized_rows = [_normalize_row(row) for row in rows]
    validation = _validate_rows(normalized_rows)
    coverage = _coverage_by_team(normalized_rows)
    teams_below = [team for team, item in coverage.items() if item["ratio"] < p3_ingest.GBM_COVERAGE_THRESHOLD]
    ok = not read_errors and not validation["errors"] and not validation["unmatched_players"]
    if ok and not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(normalized_rows)
    return {
        "ok": ok,
        "result": "PASS" if ok else "FAIL",
        "p3_mode": p3_ingest.P3_MODE,
        "requires_xg_xa": p3_ingest.REQUIRES_XG_XA,
        "xg_xa_optional": p3_ingest.XG_XA_OPTIONAL,
        "light_required_fields": p3_ingest.LIGHT_REQUIRED_FIELDS,
        "reason": None if ok else "source_csv_validation_failed",
        "source_files": [str(path) for path in source_paths],
        "would_write_db": False,
        "would_write_csv": bool(ok and not dry_run),
        "rows": len(normalized_rows),
        "teams": len(coverage),
        "coverage_by_team": coverage,
        "teams_below_70_percent": teams_below,
        "unmatched_players": validation["unmatched_players"],
        "errors": read_errors + validation["errors"],
        "fake_or_example_rows_detected": validation["fake_or_example_rows_detected"],
        "candidate_w_gbm": p3_ingest.GBM_GRAY_WEIGHT if ok and not teams_below else 0,
        "production_w_gbm": p3_ingest.PRODUCTION_W_GBM,
        "output": str(out),
    }


def print_report(report: dict[str, Any]) -> None:
    print("P3 Real Performance CSV Build Report")
    for key in (
        "result",
        "p3_mode",
        "requires_xg_xa",
        "xg_xa_optional",
        "light_required_fields",
        "reason",
        "source_files",
        "output",
        "rows",
        "teams",
        "teams_below_70_percent",
        "unmatched_players",
        "fake_or_example_rows_detected",
        "candidate_w_gbm",
        "production_w_gbm",
        "would_write_csv",
        "would_write_db",
    ):
        print(f"- {key}: {report.get(key)}")
    if report.get("errors"):
        print(f"- errors: {report['errors']}")


def _source_paths(source_file: Path, raw_dir: Path) -> list[Path]:
    paths: list[Path] = []
    if source_file.exists():
        paths.append(source_file)
    if raw_dir.exists():
        paths.extend(sorted(raw_dir.glob("*.csv")))
    return paths


def _read_source_rows(paths: list[Path]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    required = set(OUTPUT_COLUMNS)
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(required - columns)
            if missing:
                errors.extend(f"{path.name}: missing column {column}" for column in missing)
                continue
            rows.extend(dict(row) for row in reader)
    return rows, errors


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    return {column: str(row.get(column) or "").strip() for column in OUTPUT_COLUMNS}


def _validate_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    roster_keys = p3_ingest._official_roster_keys(DATA_DIR)
    errors: list[str] = []
    unmatched_players: list[str] = []
    fake_or_example = False
    for index, row in enumerate(rows, start=2):
        if any("EXAMPLE_ONLY_DO_NOT_USE" in value for value in row.values()):
            fake_or_example = True
            errors.append(f"row {index}: example/template row cannot be used")
        for column in p3_ingest.PERFORMANCE_REQUIRED_VALUES:
            if not row.get(column):
                errors.append(f"row {index}: missing required {column}")
        confidence = row.get("confidence", "").lower()
        if confidence and confidence not in p3_ingest.REAL_CONFIDENCE_VALUES:
            errors.append(f"row {index}: confidence must be high, medium, or low")
        player_key = p3_ingest._real_player_key(row)
        if player_key and player_key not in roster_keys:
            unmatched_players.append(f"{row.get('team')}::{row.get('player_name')}")
        notes = row.get("notes", "").lower()
        for column in p3_ingest.PERFORMANCE_REQUIRED_NUMERIC_COLUMNS:
            parsed = p3_ingest._parse_number(row.get(column))
            if parsed is None:
                errors.append(f"row {index}: invalid or missing numeric {column}")
            elif parsed < 0:
                errors.append(f"row {index}: {column} must be >= 0")
        for column in p3_ingest.PERFORMANCE_OPTIONAL_NUMERIC_COLUMNS:
            value = row.get(column, "")
            if not value:
                if "unavailable" not in notes:
                    errors.append(f"row {index}: blank {column} requires notes to include unavailable")
                continue
            parsed = p3_ingest._parse_number(value)
            if parsed is None:
                errors.append(f"row {index}: invalid numeric {column}")
            elif parsed < 0:
                errors.append(f"row {index}: {column} must be >= 0")
    return {
        "errors": errors,
        "unmatched_players": sorted(set(unmatched_players)),
        "fake_or_example_rows_detected": fake_or_example,
    }


def _coverage_by_team(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    roster_by_team: dict[str, set[str]] = {}
    complete_by_team: dict[str, set[str]] = {}
    for row in p3_ingest._read_rows(DATA_DIR / "manual_real_squad.csv"):
        team = p3_ingest._project_team_name(row.get("team", ""))
        key = p3_ingest._real_player_key(row)
        if team and key:
            roster_by_team.setdefault(team, set()).add(key)
    for row in rows:
        team = p3_ingest._project_team_name(row.get("team", ""))
        key = p3_ingest._real_player_key(row)
        if team and key and p3_ingest._has_complete_recent_performance(row):
            complete_by_team.setdefault(team, set()).add(key)
    coverage: dict[str, dict[str, Any]] = {}
    for team in sorted(roster_by_team):
        total = len(roster_by_team[team])
        complete = len(roster_by_team[team] & complete_by_team.get(team, set()))
        coverage[team] = {
            "players": total,
            "complete": complete,
            "ratio": complete / total if total else 0.0,
        }
    return coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build reviewed P3 real performance CSV from authorized local CSV")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-file", type=Path, default=DEFAULT_SOURCE_FILE)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    report = build_real_performance_csv(
        out=args.out,
        source_file=args.source_file,
        raw_dir=args.raw_dir,
        dry_run=args.dry_run,
    )
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
