from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import os

from api.db import connect
from api.ops_log import recent_ops_log


def generate_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    scheduler_enabled = os.getenv("ENABLE_API_SCHEDULER", "false").strip().lower() in {"1", "true", "yes", "on"}
    report: dict[str, Any] = {
        "ENABLE_API_SCHEDULER": os.getenv("ENABLE_API_SCHEDULER", "false"),
        "BETTING_ENABLED": os.getenv("BETTING_ENABLED", "false"),
        "latest results_sync ops_log": _latest_log("results_sync"),
        "latest settlement_runner ops_log": _latest_log("settlement_runner"),
        "latest odds_snapshots fetched_at": _latest_odds_fetched_at(),
        "open_bets_count": _open_bets_count(),
    }
    report["result"] = _result(report, scheduler_enabled, now)
    return report


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("Scheduler Observe Report")
    for key in (
        "ENABLE_API_SCHEDULER",
        "BETTING_ENABLED",
        "latest results_sync ops_log",
        "latest settlement_runner ops_log",
        "latest odds_snapshots fetched_at",
        "open_bets_count",
        "result",
    ):
        print(f"- {key}: {report[key]}")


def main() -> int:
    report = generate_report()
    print_report(report)
    return 0 if report["result"] in {"PASS", "WAIT"} else 1


def _latest_log(job_name: str) -> Any:
    try:
        rows = recent_ops_log(job_name, limit=1)
        return rows[0] if rows else None
    except Exception as exc:
        return f"NOT_CHECKED: {type(exc).__name__}"


def _latest_odds_fetched_at() -> Any:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT max(fetched_at) FROM odds_snapshots")
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else None
    except Exception as exc:
        return f"NOT_CHECKED: {type(exc).__name__}"


def _open_bets_count() -> Any:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bets WHERE status = 'open'")
            return int(cur.fetchone()[0])
    except Exception as exc:
        return f"NOT_CHECKED: {type(exc).__name__}"


def _result(report: dict[str, Any], scheduler_enabled: bool, now: datetime) -> str:
    if any(isinstance(value, str) and value.startswith("NOT_CHECKED") for value in report.values()):
        return "FAIL"
    if not scheduler_enabled:
        return "PASS"
    results_log = report["latest results_sync ops_log"]
    settlement_log = report["latest settlement_runner ops_log"]
    if not results_log or not settlement_log:
        return "WAIT"
    if results_log.get("status") == "error" or settlement_log.get("status") == "error":
        return "FAIL"
    if _older_than(results_log.get("started_at"), now, 75) or _older_than(settlement_log.get("started_at"), now, 45):
        return "FAIL"
    return "PASS"


def _older_than(value: Any, now: datetime, minutes: int) -> bool:
    if not value:
        return True
    if isinstance(value, datetime):
        started_at = value
    else:
        started_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at < now - timedelta(minutes=minutes)


if __name__ == "__main__":
    raise SystemExit(main())
