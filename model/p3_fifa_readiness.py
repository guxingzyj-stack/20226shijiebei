from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


P3_MODE = "fifa_matchdata"
WAIT = "WAIT"
SHADOW = "SHADOW"
CANDIDATE = "CANDIDATE"
ACTIVE_READY = "ACTIVE_READY"
PRODUCTION_W_P3 = 0
CANDIDATE_W_P3 = 0.05

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "p3"
FIFA_SAMPLE_FILE = "real_performance_fifa_match_sample.csv"
FIFA_UNMATCHED_FILE = "real_performance_unmatched_fifa.csv"
FIFA_REPORT_FILE = ROOT / "docs" / "P3_FIFA_MATCH_DATA_REPORT.md"

MATCH_COLUMNS = ("match_id", "fifa_match_id", "match_url", "source_match_id")
TEAM_COLUMNS = ("team", "team_name", "national_team", "squad_team")
PLAYER_COLUMNS = ("player", "player_name", "name")
MINUTES_COLUMNS = ("minutes", "minutes_played", "minutes_recent")
GOALS_COLUMNS = ("goals", "goals_recent")
ASSISTS_COLUMNS = ("assists", "assists_recent")


def generate_report(
    data_dir: str | Path | None = None,
    *,
    result_consistency_pass: bool = True,
    ops_health_status: str | None = "OK",
    consecutive_matchdays_ok: bool = False,
    p1c_prime_ready: bool = False,
    p3_feature_eval_not_degrade: bool = False,
    user_approved: bool = False,
) -> dict[str, Any]:
    data_path = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    sample_path = data_path / FIFA_SAMPLE_FILE
    unmatched_path = data_path / FIFA_UNMATCHED_FILE

    stats = _read_sample_stats(sample_path)
    blockers = _blockers(
        sample_exists=sample_path.exists(),
        matches_with_fifa_data=stats["matches_with_fifa_data"],
        teams_with_fifa_data=stats["teams_with_fifa_data"],
        player_rows_validated=stats["player_rows_validated"],
        result_consistency_pass=result_consistency_pass,
        ops_health_status=ops_health_status,
        consecutive_matchdays_ok=consecutive_matchdays_ok,
        p1c_prime_ready=p1c_prime_ready,
        p3_feature_eval_not_degrade=p3_feature_eval_not_degrade,
        user_approved=user_approved,
    )
    status = _status(
        matches_with_fifa_data=stats["matches_with_fifa_data"],
        teams_with_fifa_data=stats["teams_with_fifa_data"],
        player_rows_validated=stats["player_rows_validated"],
        result_consistency_pass=result_consistency_pass,
        ops_health_status=ops_health_status,
        consecutive_matchdays_ok=consecutive_matchdays_ok,
        p1c_prime_ready=p1c_prime_ready,
        p3_feature_eval_not_degrade=p3_feature_eval_not_degrade,
        user_approved=user_approved,
    )
    return {
        "p3_mode": P3_MODE,
        "p3_status": status,
        "matches_with_fifa_data": stats["matches_with_fifa_data"],
        "teams_with_fifa_data": stats["teams_with_fifa_data"],
        "player_rows_validated": stats["player_rows_validated"],
        "coverage_by_team": stats["coverage_by_team"],
        "sample_file_exists": sample_path.exists(),
        "unmatched_file_exists": unmatched_path.exists(),
        "matchdata_report_exists": FIFA_REPORT_FILE.exists(),
        "p3_features_generated": status in {SHADOW, CANDIDATE, ACTIVE_READY},
        "candidate_w_p3": CANDIDATE_W_P3 if status in {CANDIDATE, ACTIVE_READY} else 0,
        "production_w_p3": PRODUCTION_W_P3,
        "production_w_gbm": 0,
        "requires_user_approval_before_production_use": status in {CANDIDATE, ACTIVE_READY},
        "production_weight_changed": False,
        "not_club_recent_form": True,
        "blockers": blockers,
    }


def health_summary() -> dict[str, Any]:
    try:
        report = generate_report()
        return {
            "p3_mode": report["p3_mode"],
            "p3_status": report["p3_status"],
            "p3_candidate_w": report["candidate_w_p3"],
            "p3_production_w": report["production_w_p3"],
            "p3_blockers": report["blockers"][:5],
        }
    except Exception:
        return {
            "p3_mode": P3_MODE,
            "p3_status": WAIT,
            "p3_candidate_w": 0,
            "p3_production_w": 0,
            "p3_blockers": ["p3_fifa_readiness_unavailable"],
        }


def ops_summary() -> dict[str, Any]:
    report = generate_report()
    return {
        "p3_fifa_status": report["p3_status"],
        "p3_fifa_matches_with_data": report["matches_with_fifa_data"],
        "p3_fifa_teams_with_data": report["teams_with_fifa_data"],
        "p3_fifa_candidate_w": report["candidate_w_p3"],
        "p3_fifa_production_w": report["production_w_p3"],
    }


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("P3 FIFA Readiness Report")
    print("")
    for key in (
        "p3_mode",
        "p3_status",
        "matches_with_fifa_data",
        "teams_with_fifa_data",
        "player_rows_validated",
        "coverage_by_team",
        "candidate_w_p3",
        "production_w_p3",
        "production_w_gbm",
        "requires_user_approval_before_production_use",
        "production_weight_changed",
        "blockers",
    ):
        print(f"- {key}: {_safe(report.get(key))}")


def _status(
    *,
    matches_with_fifa_data: int,
    teams_with_fifa_data: int,
    player_rows_validated: int,
    result_consistency_pass: bool,
    ops_health_status: str | None,
    consecutive_matchdays_ok: bool,
    p1c_prime_ready: bool,
    p3_feature_eval_not_degrade: bool,
    user_approved: bool,
) -> str:
    if matches_with_fifa_data <= 0 or player_rows_validated <= 0:
        return WAIT
    if (
        matches_with_fifa_data >= 32
        and teams_with_fifa_data >= 32
        and result_consistency_pass
        and str(ops_health_status or "").upper() != "FAIL"
        and consecutive_matchdays_ok
        and p1c_prime_ready
        and p3_feature_eval_not_degrade
        and user_approved
    ):
        return ACTIVE_READY
    if (
        matches_with_fifa_data >= 16
        and teams_with_fifa_data >= 16
        and result_consistency_pass
        and str(ops_health_status or "").upper() != "FAIL"
    ):
        return CANDIDATE
    return SHADOW


def _blockers(
    *,
    sample_exists: bool,
    matches_with_fifa_data: int,
    teams_with_fifa_data: int,
    player_rows_validated: int,
    result_consistency_pass: bool,
    ops_health_status: str | None,
    consecutive_matchdays_ok: bool,
    p1c_prime_ready: bool,
    p3_feature_eval_not_degrade: bool,
    user_approved: bool,
) -> list[str]:
    blockers: list[str] = []
    if not sample_exists:
        blockers.append("missing_fifa_matchdata")
    elif matches_with_fifa_data <= 0 or player_rows_validated <= 0:
        blockers.append("no_valid_fifa_player_rows")
    if 0 < matches_with_fifa_data < 16 or 0 < teams_with_fifa_data < 16:
        blockers.append("insufficient_fifa_matchdata_samples")
    if not result_consistency_pass:
        blockers.append("result_consistency_not_pass")
    if str(ops_health_status or "").upper() == "FAIL":
        blockers.append("ops_health_fail")
    if matches_with_fifa_data >= 32 and teams_with_fifa_data >= 32:
        if not consecutive_matchdays_ok:
            blockers.append("need_two_matchdays_auto_parse_ok")
        if not p1c_prime_ready:
            blockers.append("p1c_prime_not_ready")
        if not p3_feature_eval_not_degrade:
            blockers.append("p3_feature_eval_not_pass")
        if not user_approved:
            blockers.append("user_approval_required")
    return blockers


def _read_sample_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"matches_with_fifa_data": 0, "teams_with_fifa_data": 0, "player_rows_validated": 0, "coverage_by_team": {}}
    matches: set[str] = set()
    teams: set[str] = set()
    coverage: dict[str, int] = {}
    rows_validated = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            match_id = _first(row, MATCH_COLUMNS)
            team = _first(row, TEAM_COLUMNS)
            player = _first(row, PLAYER_COLUMNS)
            minutes = _first(row, MINUTES_COLUMNS)
            goals = _first(row, GOALS_COLUMNS)
            assists = _first(row, ASSISTS_COLUMNS)
            if match_id:
                matches.add(match_id)
            if team:
                teams.add(team)
            if match_id and team and player and _is_number(minutes) and _is_number(goals) and _is_number(assists):
                rows_validated += 1
                coverage[team] = coverage.get(team, 0) + 1
    return {
        "matches_with_fifa_data": len(matches),
        "teams_with_fifa_data": len(teams),
        "player_rows_validated": rows_validated,
        "coverage_by_team": dict(sorted(coverage.items())),
    }


def _first(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = str(row.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _is_number(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _safe(value: Any) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 FIFA MatchData readiness report")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
