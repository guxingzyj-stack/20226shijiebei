from __future__ import annotations

from typing import Any
import os

from psycopg.rows import dict_row

from api.db import connect
from api.ops_health_check import latest_ops_health_status
from api.ops_log import recent_ops_log
from api.scheduler_health import scheduler_freshness


def generate_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "database": "fail",
        "matches count": "NOT_CHECKED",
        "odds_snapshots count": "NOT_CHECKED",
        "latest odds fetched_at": "NOT_CHECKED",
        "latest model_version": "NOT_CHECKED",
        "latest prediction count": "NOT_CHECKED",
        "latest ev_signals count": "NOT_CHECKED",
        "betting_enabled": os.getenv("BETTING_ENABLED", "false"),
        "api_scheduler_enabled": os.getenv("ENABLE_API_SCHEDULER", "false"),
        "recent ops_log": "NOT_CHECKED",
        "latest_ops_health_check_at": "NOT_CHECKED",
        "ops_health_status": "NOT_CHECKED",
        "ops_health_blockers": "NOT_CHECKED",
        "latest_ops_log_at": "NOT_CHECKED",
        "latest_results_sync_at": "NOT_CHECKED",
        "latest_settlement_runner_at": "NOT_CHECKED",
        "latest_ops_log_age_minutes": "NOT_CHECKED",
        "scheduler_stale": "NOT_CHECKED",
        "scheduler_stale_threshold_minutes": 90,
        "open_bets_count": "NOT_CHECKED",
        "test_users_count": "NOT_CHECKED",
        "test_matches_count": "NOT_CHECKED",
    }
    try:
        with connect() as conn:
            report["database"] = "ok"
            report["matches count"] = _count(conn, "matches")
            report["odds_snapshots count"] = _count(conn, "odds_snapshots")
            report["latest odds fetched_at"] = _scalar(conn, "SELECT max(fetched_at) FROM odds_snapshots")
            latest_version = _latest_model_version(conn)
            report["latest model_version"] = latest_version
            latest_version_id = latest_version.get("id") if isinstance(latest_version, dict) else None
            report["latest prediction count"] = _version_count(conn, "predictions", latest_version_id)
            report["latest ev_signals count"] = _version_count(conn, "ev_signals", latest_version_id)
            report["recent ops_log"] = {
                "results_sync": _safe_recent_ops_log("results_sync"),
                "settlement_runner": _safe_recent_ops_log("settlement_runner"),
                "ops_health_check": _safe_recent_ops_log("ops_health_check"),
            }
            report.update(latest_ops_health_status())
            report.update(scheduler_freshness())
            report["open_bets_count"] = _scalar(conn, "SELECT count(*) FROM bets WHERE status = 'open'")
            report["test_users_count"] = _scalar(conn, "SELECT count(*) FROM users WHERE username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%'")
            report["test_matches_count"] = _scalar(conn, "SELECT count(*) FROM matches WHERE match_id LIKE 'test-%%'")
    except Exception as exc:
        report["database"] = f"fail: {type(exc).__name__}"
    report["result"] = _result(report)
    return report


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("Health Report")
    for key in (
        "database",
        "matches count",
        "odds_snapshots count",
        "latest odds fetched_at",
        "latest model_version",
        "latest prediction count",
        "latest ev_signals count",
        "betting_enabled",
        "api_scheduler_enabled",
        "recent ops_log",
        "latest_ops_health_check_at",
        "ops_health_status",
        "ops_health_blockers",
        "latest_ops_log_at",
        "latest_results_sync_at",
        "latest_settlement_runner_at",
        "latest_ops_log_age_minutes",
        "scheduler_stale",
        "scheduler_stale_threshold_minutes",
        "open_bets_count",
        "test_users_count",
        "test_matches_count",
        "result",
    ):
        print(f"- {key}: {report[key]}")


def _count(conn, table: str) -> int:
    if table not in {"matches", "odds_snapshots"}:
        raise ValueError("unsupported count table")
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _scalar(conn, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    return row[0] if row else None


def _latest_model_version(conn) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, name, trained_at FROM model_versions ORDER BY trained_at DESC, id DESC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None


def _version_count(conn, table: str, model_version_id: Any) -> int | str:
    if table not in {"predictions", "ev_signals"}:
        raise ValueError("unsupported version count table")
    if model_version_id is None:
        return "NOT_CHECKED: no latest model_version"
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table} WHERE model_version = %s", (model_version_id,))
        return int(cur.fetchone()[0])


def _safe_recent_ops_log(job_name: str) -> Any:
    try:
        return recent_ops_log(job_name, limit=1)
    except Exception as exc:
        return f"NOT_CHECKED: {type(exc).__name__}"


def _result(report: dict[str, Any]) -> str:
    if not str(report.get("database", "")).startswith("ok"):
        return "FAIL"
    if report.get("odds_snapshots count") in (0, None):
        return "FAIL"
    if report.get("scheduler_stale") is True:
        return "FAIL"
    if _enabled(report.get("betting_enabled")):
        return "WARN"
    if int(report.get("test_users_count") or 0) > 0 or int(report.get("test_matches_count") or 0) > 0:
        return "WARN"
    return "PASS"


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    report = generate_report()
    print_report(report)
    return 0 if report["result"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
