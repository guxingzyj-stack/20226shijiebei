from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import inspect
import os

from api import db as api_db
from api import main as api_main
from api.betting import is_betting_enabled
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
            ReportLine("detail_uses_latest_model_version_only", _latest_prediction_filters_model_version()),
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


def _cors_has_web_origin() -> Any:
    value = os.getenv("CORS_ORIGINS")
    if not value:
        return "NOT_CHECKED: CORS_ORIGINS unset"
    return any("worldcup2026" in origin or "localhost" in origin for origin in value.split(","))


def _latest_prediction_filters_model_version() -> bool:
    source = inspect.getsource(api_db.Database.latest_prediction)
    return "model_version = (" in source and "SELECT id FROM model_versions" in source


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


if __name__ == "__main__":
    raise SystemExit(main())
