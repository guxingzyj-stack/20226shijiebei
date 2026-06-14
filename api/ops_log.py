from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.db import connect


SECRET_MARKERS = ("DATABASE_URL", "JWT_SECRET", "TOKEN", "PASSWORD", "SECRET", "KEY")


def sanitize_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for marker in SECRET_MARKERS:
        text = text.replace(marker, "[redacted]")
    return text[:500]


def make_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    return value


def record_ops_log(
    job_name: str,
    status: str,
    started_at: datetime,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    safe_summary = make_json_safe(summary or {})
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops_log (job_name, status, started_at, finished_at, summary, error)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (job_name, status, started_at, datetime.now(timezone.utc), Jsonb(safe_summary), error),
            )
    except Exception as exc:
        print({"event": "ops_log_write_failed", "job_name": job_name, "status": status, "error": sanitize_error(exc)})


def recent_ops_log(job_name: str, limit: int = 3) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT job_name, status, started_at, finished_at, summary, error
            FROM ops_log
            WHERE job_name = %s
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (job_name, limit),
        )
        return [dict(row) for row in cur.fetchall()]
