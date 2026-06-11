from __future__ import annotations

import argparse
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.scheduler_health import SCHEDULER_STALE_THRESHOLD_MINUTES, scheduler_freshness

REPAIR_CONFIRM_TOKEN = "REPAIR_FINISHED_NULL"


def generate_report(match_id: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        finished_missing = _rows(
            conn,
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND (result_home IS NULL OR result_away IS NULL)
              AND (%s::text IS NULL OR match_id = %s)
            ORDER BY kickoff_at NULLS LAST, match_id
            LIMIT 20
            """,
            (match_id, match_id),
        )
        scheduled_with_result = _rows(
            conn,
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE status NOT IN ('finished', 'completed')
              AND (result_home IS NOT NULL OR result_away IS NOT NULL)
              AND (%s::text IS NULL OR match_id = %s)
            ORDER BY kickoff_at NULLS LAST, match_id
            LIMIT 20
            """,
            (match_id, match_id),
        )
        ready_for_settlement = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
              AND (%s::text IS NULL OR match_id = %s)
            """,
            (match_id, match_id),
        )
        not_ready_finished_like = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND (result_home IS NULL OR result_away IS NULL)
              AND (%s::text IS NULL OR match_id = %s)
            """,
            (match_id, match_id),
        )
    freshness = scheduler_freshness()
    scheduler_stale = freshness.get("scheduler_stale") is True
    result = "PASS"
    if finished_missing or scheduled_with_result or scheduler_stale:
        result = "WARN"
    return {
        "finished_but_missing_result": {"count": len(finished_missing), "matches": finished_missing},
        "scheduled_or_closed_but_has_result": {"count": len(scheduled_with_result), "matches": scheduled_with_result},
        "settlement_readiness": {
            "ready_for_settlement_count": ready_for_settlement,
            "not_ready_finished_like_count": not_ready_finished_like,
        },
        "scheduler_freshness": {
            "latest_ops_log_at": freshness.get("latest_ops_log_at"),
            "latest_results_sync_at": freshness.get("latest_results_sync_at"),
            "latest_settlement_runner_at": freshness.get("latest_settlement_runner_at"),
            "latest_ops_log_age_minutes": freshness.get("latest_ops_log_age_minutes"),
            "scheduler_stale": freshness.get("scheduler_stale"),
            "threshold_minutes": SCHEDULER_STALE_THRESHOLD_MINUTES,
        },
        "result": result,
    }


def print_report(report: dict[str, Any]) -> None:
    print("Result Consistency Report")
    print("")
    print("1. Finished but missing result")
    _print_match_section(report["finished_but_missing_result"])
    print("")
    print("2. Scheduled/closed but has result")
    _print_match_section(report["scheduled_or_closed_but_has_result"])
    print("")
    print("3. Settlement readiness")
    for key, value in report["settlement_readiness"].items():
        print(f"- {key}: {value}")
    print("")
    print("4. Scheduler freshness")
    for key, value in report["scheduler_freshness"].items():
        print(f"- {key}: {value}")
    print("")
    print("5. Result")
    print(f"- {report['result']}")


def repair_finished_null(dry_run: bool = True, confirm: str | None = None) -> dict[str, Any]:
    if not dry_run and confirm != REPAIR_CONFIRM_TOKEN:
        return {
            "mode": "run",
            "ok": False,
            "error": f"--confirm {REPAIR_CONFIRM_TOKEN} is required",
            "matches": [],
            "would_update_count": 0,
            "updated_count": 0,
        }
    with connect() as conn:
        targets = _repair_targets(conn)
        if dry_run:
            return {
                "mode": "dry-run",
                "ok": True,
                "matches": targets,
                "would_update_count": len(targets),
                "updated_count": 0,
            }
        with conn.transaction():
            updated = _update_finished_null_to_closed(conn)
        return {
            "mode": "run",
            "ok": True,
            "matches": targets,
            "would_update_count": len(targets),
            "updated_count": len(updated),
            "updated_match_ids": updated,
        }


def print_repair_report(report: dict[str, Any]) -> None:
    print("Repair Finished Null Report")
    print(f"- mode: {report['mode']}")
    print(f"- ok: {report['ok']}")
    if report.get("error"):
        print(f"- error: {report['error']}")
    print("- matches:")
    for row in report.get("matches", []):
        print(
            "  - "
            f"match_id: {row.get('match_id')}, "
            f"match_num: {row.get('match_num')}, "
            f"home_team: {row.get('home_team')}, "
            f"away_team: {row.get('away_team')}, "
            f"kickoff_at: {row.get('kickoff_at')}, "
            f"status: {row.get('status')}, "
            f"result_home: {row.get('result_home')}, "
            f"result_away: {row.get('result_away')}"
        )
    print(f"- would_update_count: {report['would_update_count']}")
    print(f"- updated_count: {report['updated_count']}")


def _print_match_section(section: dict[str, Any]) -> None:
    print(f"- count: {section['count']}")
    print("- matches:")
    for row in section["matches"]:
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
            f"ht_home: {row.get('ht_home')}, "
            f"ht_away: {row.get('ht_away')}"
        )


def _rows(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def _scalar(conn, sql: str, params: tuple[Any, ...]) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def _repair_targets(conn) -> list[dict[str, Any]]:
    return _rows(
        conn,
        """
        SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
               result_home, result_away, ht_home, ht_away
        FROM matches
        WHERE status IN ('finished', 'completed')
          AND result_home IS NULL
          AND result_away IS NULL
        ORDER BY kickoff_at NULLS LAST, match_id
        """,
        (),
    )


def _update_finished_null_to_closed(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE matches
            SET status = 'closed',
                updated_at = now()
            WHERE status IN ('finished', 'completed')
              AND result_home IS NULL
              AND result_away IS NULL
            RETURNING match_id
            """
        )
        return [str(row[0]) for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="read-only result consistency diagnostics")
    subparsers = parser.add_subparsers(dest="command")
    repair_parser = subparsers.add_parser("repair-finished-null")
    repair_parser.add_argument("--dry-run", action="store_true")
    repair_parser.add_argument("--confirm")
    parser.add_argument("--match-id")
    args = parser.parse_args(argv)
    if args.command == "repair-finished-null":
        repair = repair_finished_null(dry_run=bool(args.dry_run), confirm=args.confirm)
        print_repair_report(repair)
        return 0 if repair["ok"] else 2
    report = generate_report(match_id=args.match_id)
    print_report(report)
    return 0 if report["result"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
