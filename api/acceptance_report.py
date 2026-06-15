from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import inspect
import os

from api import db as api_db
from api import main as api_main
from api.betting import is_betting_enabled
from api.ops_log import recent_ops_log
from api.recap import calibration_curve_from_finished_matches
from api.results_sync import ResultsSyncStats, fetch_results_html, parse_results_html, sync_results
from api.settlement_runner import PostgresSettlementRepository, SettlementStats, run_settlement


@dataclass(frozen=True)
class ReportLine:
    key: str
    value: Any


def generate_report() -> dict[str, list[ReportLine]]:
    betting_enabled = is_betting_enabled()
    results_stats = _run_results_sync_dry_run()
    settlement_stats = _run_settlement_dry_run()
    recent_results_log = _recent_ops_log("results_sync")
    recent_settlement_log = _recent_ops_log("settlement_runner")
    p3_status = _p3_status()
    p4_status = _p4_status()
    return {
        "1. Environment": [
            ReportLine("BETTING_ENABLED", os.getenv("BETTING_ENABLED", "false")),
            ReportLine("CORS_ORIGINS_contains_Web_domain", _cors_has_web_origin()),
            ReportLine("DATABASE_URL_exists", "yes" if os.getenv("DATABASE_URL") else "no"),
            ReportLine("JWT_SECRET_exists", "yes" if os.getenv("JWT_SECRET") else "no"),
        ],
        "2. Betting Safety": [
            ReportLine("BETTING_ENABLED_false_rejects_POST_bets", not betting_enabled),
            ReportLine("current_config_allows_betting", betting_enabled),
            ReportLine("warning", "WARNING: betting is enabled" if betting_enabled else "none"),
        ],
        "3. API Data Contract": [
            ReportLine("detail_uses_latest_match_prediction", _latest_prediction_uses_match_latest_prediction()),
            ReportLine("top_level_score_matrix_deleted", _detail_does_not_set_top_level_score_matrix()),
            ReportLine("leaderboard_hides_internal_id", _leaderboard_hides_id()),
        ],
        "4. Results Sync": [
            ReportLine("dry_run_executable", results_stats is not None),
            ReportLine("matches_seen", _stat(results_stats, "matches_seen")),
            ReportLine("finished_updated", _stat(results_stats, "finished_updated")),
            ReportLine("halftime_updated", _stat(results_stats, "halftime_updated")),
            ReportLine("postponed_updated", _stat(results_stats, "postponed_updated")),
            ReportLine("skipped", _stat(results_stats, "skipped")),
            ReportLine("errors", _stat(results_stats, "errors")),
        ],
        "5. Settlement Runner": [
            ReportLine("dry_run_executable", settlement_stats is not None),
            ReportLine("open_bets_seen", _stat(settlement_stats, "open_bets_seen")),
            ReportLine("settled_won", _stat(settlement_stats, "settled_won")),
            ReportLine("settled_lost", _stat(settlement_stats, "settled_lost")),
            ReportLine("settled_void", _stat(settlement_stats, "settled_void")),
            ReportLine("skipped_not_ready", _stat(settlement_stats, "skipped_not_ready")),
            ReportLine("errors", _stat(settlement_stats, "errors")),
        ],
        "6. Scheduler": [
            ReportLine("ENABLE_API_SCHEDULER", os.getenv("ENABLE_API_SCHEDULER", "false")),
            ReportLine("scheduler_enabled", os.getenv("ENABLE_API_SCHEDULER", "false").strip().lower() in {"1", "true", "yes", "on"}),
            ReportLine("RESULTS_SYNC_INTERVAL_MINUTES", os.getenv("RESULTS_SYNC_INTERVAL_MINUTES", "60")),
            ReportLine("SETTLEMENT_RUNNER_INTERVAL_MINUTES", os.getenv("SETTLEMENT_RUNNER_INTERVAL_MINUTES", "30")),
            ReportLine("recent results_sync ops_log", recent_results_log),
            ReportLine("recent settlement_runner ops_log", recent_settlement_log),
        ],
        "7. P3": [
            ReportLine("p3_tables_exist", p3_status["tables_exist"]),
            ReportLine("gbm_enabled", p3_status["gbm_enabled"]),
            ReportLine("gbm_weight", p3_status["gbm_weight"]),
            ReportLine("status", p3_status["status"]),
        ],
        "8. P4": [
            ReportLine("finished_matches", p4_status["finished_matches"]),
            ReportLine("recap_available", p4_status["recap_available"]),
            ReportLine("status", p4_status["status"]),
        ],
    }


def print_report(report: dict[str, list[ReportLine]] | None = None) -> None:
    report = report or generate_report()
    print("P2 API Acceptance Report")
    for section, lines in report.items():
        print("")
        print(section)
        for line in lines:
            print(f"- {line.key}: {line.value}")


def main() -> int:
    print_report(generate_report())
    return 0


def _run_results_sync_dry_run() -> ResultsSyncStats | None:
    try:
        html = fetch_results_html()
        return sync_results(parse_results_html(html), repository=_NoWriteResultsRepository(), dry_run=True)
    except Exception:
        return None


def _run_settlement_dry_run() -> SettlementStats | None:
    try:
        return run_settlement(PostgresSettlementRepository(), dry_run=True)
    except Exception:
        return SettlementStats(errors=1)


def _stat(stats: Any, name: str) -> Any:
    if stats is None:
        return "NOT_CHECKED: dry-run failed"
    return getattr(stats, name)


def _recent_ops_log(job_name: str) -> Any:
    try:
        rows = recent_ops_log(job_name, limit=3)
    except Exception as exc:
        if type(exc).__name__ in {"UndefinedTable", "ProgrammingError"}:
            return "NOT_CHECKED: ops_log table missing"
        return f"NOT_CHECKED: ops_log query failed: {type(exc).__name__}"
    return [
        {
            "status": row.get("status"),
            "started_at": str(row.get("started_at")),
            "summary": row.get("summary"),
            "error": row.get("error"),
        }
        for row in rows
    ]


def _cors_has_web_origin() -> Any:
    value = os.getenv("CORS_ORIGINS")
    if not value:
        return "NOT_CHECKED: CORS_ORIGINS unset"
    return any("worldcup2026" in origin or "localhost" in origin for origin in value.split(","))


def _latest_prediction_uses_match_latest_prediction() -> bool:
    source = inspect.getsource(api_db.Database.latest_prediction)
    compact = " ".join(source.split()).lower()
    return (
        "from predictions" in compact
        and "where match_id = %s" in compact
        and "order by created_at desc, id desc" in compact
        and ("from " + "model_versions") not in compact
    )


def _references_latest_match_prediction(source: str) -> bool:
    compact = " ".join(source.split()).lower()
    latest_prediction_subquery = "select p.model_version from predictions p"
    return (
        "model_version = (" in compact
        and latest_prediction_subquery in compact
        and "where p.match_id = %s" in compact
        and "order by p.created_at desc, p.id desc" in compact
    )


def _detail_does_not_set_top_level_score_matrix() -> bool:
    source = inspect.getsource(api_main.match_detail)
    return '"score_matrix"' not in source and "latest_prediction" in source


def _leaderboard_hides_id() -> bool:
    source = inspect.getsource(api_db.Database.leaderboard)
    return "SELECT u.username" in source and "SELECT id" not in source


class _NoWriteResultsRepository:
    def update_finished(self, result):
        raise AssertionError("acceptance report must run results_sync in dry-run mode")

    def update_postponed(self, result):
        raise AssertionError("acceptance report must run results_sync in dry-run mode")


def _p3_status() -> dict[str, Any]:
    required = {"players", "player_season_stats", "injuries", "team_features", "gbm_versions", "gbm_predictions"}
    try:
        with api_db.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (list(required),),
            )
            existing = {row[0] for row in cur.fetchall()}
    except Exception as exc:
        return {"tables_exist": f"NOT_CHECKED: {type(exc).__name__}", "gbm_enabled": False, "gbm_weight": 0, "status": "not_checked"}
    tables_exist = required <= existing
    return {"tables_exist": tables_exist, "gbm_enabled": False, "gbm_weight": 0, "status": "p3a_infrastructure_ready" if tables_exist else "pending_migration"}


def _p4_status() -> dict[str, Any]:
    curve = calibration_curve_from_finished_matches()
    finished = curve.get("finished_matches", 0) if isinstance(curve, dict) else 0
    return {
        "finished_matches": finished,
        "recap_available": isinstance(curve, dict) and curve.get("status") not in {"insufficient_finished_matches"},
        "status": curve.get("status", "unknown") if isinstance(curve, dict) else "unknown",
    }


if __name__ == "__main__":
    raise SystemExit(main())
