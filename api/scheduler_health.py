from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from api.db import connect


SCHEDULER_STALE_THRESHOLD_MINUTES = 90


def scheduler_freshness(threshold_minutes: int = SCHEDULER_STALE_THRESHOLD_MINUTES) -> dict[str, Any]:
    try:
        with connect() as conn:
            latest_any = _latest_ops_log(conn)
            latest_results = _latest_ops_log(conn, "results_sync")
            latest_settlement = _latest_ops_log(conn, "settlement_runner")
    except Exception:
        return {
            "scheduler_last_seen": None,
            "scheduler_last_seen_age_minutes": None,
            "scheduler_stale": None,
            "latest_ops_log_at": None,
            "latest_results_sync_at": None,
            "latest_settlement_runner_at": None,
            "latest_ops_log_age_minutes": None,
            "threshold_minutes": threshold_minutes,
        }
    age = _age_minutes(latest_any.get("started_at") if latest_any else None)
    stale = age is None or age > threshold_minutes
    return {
        "scheduler_last_seen": _iso(latest_any.get("started_at") if latest_any else None),
        "scheduler_last_seen_age_minutes": age,
        "scheduler_stale": stale,
        "latest_ops_log_at": _iso(latest_any.get("started_at") if latest_any else None),
        "latest_results_sync_at": _iso(latest_results.get("started_at") if latest_results else None),
        "latest_settlement_runner_at": _iso(latest_settlement.get("started_at") if latest_settlement else None),
        "latest_ops_log_age_minutes": age,
        "threshold_minutes": threshold_minutes,
    }


def _latest_ops_log(conn, job_name: str | None = None) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        if job_name:
            cur.execute(
                """
                SELECT job_name, status, started_at, finished_at, summary, error
                FROM ops_log
                WHERE job_name = %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (job_name,),
            )
        else:
            cur.execute(
                """
                SELECT job_name, status, started_at, finished_at, summary, error
                FROM ops_log
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        row = cur.fetchone()
        return dict(row) if row else None


def _age_minutes(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() // 60)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()

