from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import sanitize_error
from api.scheduler_health import scheduler_freshness


OVERDUE_HOURS = 3


def generate_report() -> dict[str, Any]:
    try:
        matches = overdue_matches()
        latest_sync = latest_results_sync()
        freshness = scheduler_freshness()
    except Exception as exc:
        return {
            "ok": False,
            "error": sanitize_error(exc),
            "overdue_count": None,
            "matches": [],
        }
    return {
        "ok": True,
        "overdue_count": len(matches),
        "latest_results_sync_at": _iso(latest_sync.get("started_at") if latest_sync else None),
        "latest_results_sync_status": latest_sync.get("status") if latest_sync else None,
        "matches": [
            {
                **row,
                "latest_results_sync_at": _iso(latest_sync.get("started_at") if latest_sync else None),
                "suggested_action": _suggested_action(row, latest_sync, freshness),
            }
            for row in matches
        ],
    }


def health_summary(limit: int = 10) -> dict[str, Any]:
    try:
        latest_sync = latest_results_sync()
        summary = latest_sync.get("summary") if latest_sync else {}
        if not isinstance(summary, dict):
            summary = {}
        matches = overdue_matches(limit=limit)
        return {
            "latest_results_sync_at": _iso(latest_sync.get("started_at") if latest_sync else None),
            "latest_results_sync_status": latest_sync.get("status") if latest_sync else None,
            "latest_results_sync_source": summary.get("source_name"),
            "latest_results_sync_finished_updated": summary.get("finished_updated"),
            "latest_results_sync_skipped": summary.get("skipped"),
            "latest_results_sync_skipped_reasons": summary.get("skipped_reasons") or {},
            "result_overdue_closed_count": len(matches),
            "result_overdue_closed_matches": [
                {
                    "match_id": row.get("match_id"),
                    "match_num": row.get("match_num"),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "kickoff_at": _iso(row.get("kickoff_at")),
                    "suggested_action": _suggested_action(row, latest_sync, scheduler_freshness()),
                }
                for row in matches
            ],
        }
    except Exception:
        return {
            "latest_results_sync_at": None,
            "latest_results_sync_status": None,
            "latest_results_sync_source": None,
            "latest_results_sync_finished_updated": None,
            "latest_results_sync_skipped": None,
            "latest_results_sync_skipped_reasons": {},
            "result_overdue_closed_count": None,
            "result_overdue_closed_matches": [],
        }


def overdue_matches(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status, result_home, result_away
            FROM matches
            WHERE status IN ('closed', 'scheduled')
              AND result_home IS NULL
              AND result_away IS NULL
              AND kickoff_at < now() - interval '3 hours'
            ORDER BY kickoff_at, match_id
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def latest_results_sync() -> dict[str, Any] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT job_name, status, started_at, finished_at, summary, error
            FROM ops_log
            WHERE job_name = 'results_sync'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return dict(row) if row else None


def print_report(report: dict[str, Any]) -> None:
    print("Result Overdue Report")
    print("")
    print(f"- ok: {report.get('ok')}")
    if report.get("error"):
        print(f"- error: {report.get('error')}")
    print(f"- overdue_count: {report.get('overdue_count')}")
    print(f"- latest_results_sync_at: {report.get('latest_results_sync_at')}")
    print(f"- latest_results_sync_status: {report.get('latest_results_sync_status')}")
    print("- matches:")
    for row in report.get("matches") or []:
        print(
            "  - "
            f"match_id: {row.get('match_id')}, "
            f"match_num: {row.get('match_num')}, "
            f"home_team: {row.get('home_team')}, "
            f"away_team: {row.get('away_team')}, "
            f"kickoff_at: {row.get('kickoff_at')}, "
            f"status: {row.get('status')}, "
            f"result_home: {row.get('result_home')}, "
            f"result_away: {row.get('result_away')}, "
            f"latest_results_sync_at: {row.get('latest_results_sync_at')}, "
            f"suggested_action: {row.get('suggested_action')}"
        )


def _suggested_action(row: dict[str, Any], latest_sync: dict[str, Any] | None, freshness: dict[str, Any]) -> str:
    if freshness.get("scheduler_stale") is True or latest_sync is None:
        return "RUN_RESULTS_SYNC"
    if latest_sync.get("status") == "error":
        return "RUN_RESULTS_SYNC"
    return "NEEDS_VERIFIED_FALLBACK"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="read-only overdue result report")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
