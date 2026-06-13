from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.db import connect
from api.ops_log import record_ops_log, sanitize_error
from api.result_consistency_report import generate_report as generate_consistency_report
from api.result_source_coverage_audit import build_coverage_report, classify_match, summarize_results_sync_ops
from api.scheduler_health import scheduler_freshness


DEFAULT_WINDOW_HOURS = 36
DEFAULT_LOOKBACK_HOURS = 6
DEFAULT_SUMMARY_HOURS = 48
JOB_NAME = "result_ingest_monitor"


def monitor_enabled() -> bool:
    return _enabled(os.getenv("ENABLE_RESULT_INGEST_MONITOR", "false"))


def monitor_interval_minutes() -> int:
    return _env_int("RESULT_INGEST_MONITOR_INTERVAL_MINUTES", 30)


def monitor_window_hours() -> int:
    return _env_int("RESULT_INGEST_MONITOR_WINDOW_HOURS", DEFAULT_WINDOW_HOURS)


def run_once(*, source: str = "500", window_hours: int = DEFAULT_WINDOW_HOURS) -> dict[str, Any]:
    if source != "500":
        raise ValueError("Only source=500 is supported")
    started_at = datetime.now(timezone.utc)
    try:
        with connect() as conn:
            rows = _load_monitor_matches(conn, now=started_at, window_hours=window_hours)
            ops_rows = _latest_results_sync_rows(conn)
            consistency = generate_consistency_report()
            coverage = build_coverage_report(rows, now=started_at, source=source, scope="monitor", ops_rows=ops_rows)
            scheduler = scheduler_freshness()
            records = build_observation_records(
                rows,
                now=started_at,
                results_sync=coverage["results_sync"],
                coverage_summary=coverage["summary"],
                consistency=consistency,
                scheduler=scheduler,
                first_seen_lookup=lambda match_id: _first_result_seen_at(conn, match_id),
            )
            inserted = _insert_observations(conn, records)
        summary = {
            "observed_matches": inserted,
            "window_hours": window_hours,
            "source": source,
            "closed_missing_count": coverage["summary"]["closed_missing_count"],
            "overdue_count": coverage["summary"]["overdue_count"],
            "result_consistency_pass": consistency.get("result") == "PASS",
            "scheduler_stale": scheduler.get("scheduler_stale"),
        }
        record_ops_log(JOB_NAME, "ok", started_at, summary, None)
        return {"ok": True, "mode": "run-once", "writes_business_tables": False, **summary}
    except Exception as exc:
        record_ops_log(JOB_NAME, "error", started_at, {}, sanitize_error(exc))
        raise


def build_observation_records(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    results_sync: dict[str, Any],
    coverage_summary: dict[str, Any],
    consistency: dict[str, Any],
    scheduler: dict[str, Any],
    first_seen_lookup,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        audit = classify_match(row, now=now)
        kickoff_at = _ensure_aware(row["kickoff_at"])
        estimated_fulltime_at = kickoff_at + timedelta(minutes=120)
        first_seen = None
        delay = None
        if audit["result_state"] == "result_present":
            first_seen = first_seen_lookup(str(row["match_id"])) or now
            delay = int((first_seen - estimated_fulltime_at).total_seconds() // 60)
        records.append(
            {
                "observed_at": now,
                "match_id": str(row["match_id"]),
                "match_num": row.get("match_num"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "kickoff_at": kickoff_at,
                "status": str(row.get("status") or "").lower(),
                "result_home": row.get("result_home"),
                "result_away": row.get("result_away"),
                "ht_home": row.get("ht_home"),
                "ht_away": row.get("ht_away"),
                "minutes_since_kickoff": audit["minutes_since_kickoff"],
                "estimated_fulltime_at": estimated_fulltime_at,
                "first_result_seen_at": first_seen,
                "result_ingest_delay_minutes": delay,
                "result_state": audit["result_state"],
                "audit_status": audit["audit_status"],
                "latest_results_sync_at": _parse_datetime(results_sync.get("latest_run_at")),
                "latest_results_sync_status": results_sync.get("status"),
                "latest_results_sync_source": results_sync.get("source"),
                "latest_results_sync_finished_updated": results_sync.get("finished_updated"),
                "latest_results_sync_skipped": results_sync.get("skipped"),
                "latest_results_sync_skipped_reasons": results_sync.get("skipped_reasons") or {},
                "closed_missing_count": coverage_summary.get("closed_missing_count"),
                "overdue_count": coverage_summary.get("overdue_count"),
                "result_consistency_pass": consistency.get("result") == "PASS",
                "scheduler_stale": scheduler.get("scheduler_stale") is True,
                "source_fetch_ok": results_sync.get("source_fetch_ok"),
                "parser_error": results_sync.get("parser_error"),
                "is_test_match": str(row["match_id"]).startswith("test-"),
                "notes": None,
            }
        )
    return records


def summarize_observations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_match: dict[str, dict[str, Any]] = {}
    for row in rows:
        match_id = str(row["match_id"])
        current = latest_by_match.get(match_id)
        if current is None or _ensure_aware(row["observed_at"]) > _ensure_aware(current["observed_at"]):
            latest_by_match[match_id] = row
    latest_rows = list(latest_by_match.values())
    result_present = [row for row in latest_rows if row.get("result_state") == "result_present"]
    missing = [row for row in latest_rows if row.get("result_state") != "result_present"]
    delays = [
        int(row["result_ingest_delay_minutes"])
        for row in result_present
        if row.get("result_ingest_delay_minutes") is not None
    ]
    over_60_missing = [
        row
        for row in missing
        if row.get("minutes_since_kickoff") is not None and int(row["minutes_since_kickoff"]) >= 180
    ]
    over_120_missing = [
        row
        for row in missing
        if row.get("minutes_since_kickoff") is not None and int(row["minutes_since_kickoff"]) >= 240
    ]
    inconsistent = [
        row
        for row in latest_rows
        if row.get("audit_status") in {"FINISHED_NULL_ERROR", "NON_FINISHED_HAS_RESULT_ERROR"}
        or row.get("result_consistency_pass") is False
    ]
    status = conclude_ingest_health(latest_rows)
    return {
        "mode": "dry-run/read-only-summary",
        "writes_business_tables": False,
        "summary": {
            "observations_count": len(rows),
            "observed_matches": len(latest_rows),
            "result_present_matches": len(result_present),
            "missing_result_matches": len(missing),
            "over_60min_missing_count": len(over_60_missing),
            "over_120min_missing_count": len(over_120_missing),
            "median_ingest_delay_minutes": int(statistics.median(delays)) if delays else None,
            "max_ingest_delay_minutes": max(delays) if delays else None,
            "scheduler_stale_seen_count": len([row for row in rows if row.get("scheduler_stale") is True]),
            "result_consistency_failed_count": len([row for row in rows if row.get("result_consistency_pass") is False]),
        },
        "matches": [_summary_match(row) for row in sorted(latest_rows, key=lambda item: str(item.get("kickoff_at")))],
        "result": status,
        "inconsistent_count": len(inconsistent),
    }


def conclude_ingest_health(latest_rows: list[dict[str, Any]]) -> str:
    if any(
        row.get("audit_status") in {"FINISHED_NULL_ERROR", "NON_FINISHED_HAS_RESULT_ERROR"}
        or row.get("result_consistency_pass") is False
        for row in latest_rows
    ):
        return "RESULT_INGEST_INCONSISTENT"
    missing_rows = [row for row in latest_rows if row.get("result_state") != "result_present"]
    if any(int(row.get("minutes_since_kickoff") or 0) >= 240 for row in missing_rows):
        return "RESULT_INGEST_SLOW_NEEDS_ACTION"
    if any(int(row.get("minutes_since_kickoff") or 0) >= 180 for row in missing_rows):
        return "RESULT_INGEST_SLOW_OBSERVE"
    result_delays = [
        int(row["result_ingest_delay_minutes"])
        for row in latest_rows
        if row.get("result_state") == "result_present" and row.get("result_ingest_delay_minutes") is not None
    ]
    if any(delay > 120 for delay in result_delays):
        return "RESULT_INGEST_SLOW_NEEDS_ACTION"
    if any(delay > 60 for delay in result_delays):
        return "RESULT_INGEST_SLOW_OBSERVE"
    return "RESULT_INGEST_HEALTHY"


def summary(*, since_hours: int = DEFAULT_SUMMARY_HOURS, match_id: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        rows = _load_observations(conn, since_hours=since_hours, match_id=match_id)
    return summarize_observations(rows)


def print_run_once_report(report: dict[str, Any]) -> None:
    print("Result Ingest Monitor Run")
    for key in (
        "mode",
        "ok",
        "writes_business_tables",
        "observed_matches",
        "window_hours",
        "source",
        "closed_missing_count",
        "overdue_count",
        "result_consistency_pass",
        "scheduler_stale",
    ):
        print(f"- {key}: {report.get(key)}")


def print_summary_report(report: dict[str, Any]) -> None:
    print("Result Ingest Monitor Summary")
    print("")
    print(f"mode: {report['mode']}")
    print(f"writes_business_tables: {str(report['writes_business_tables']).lower()}")
    print("")
    print("summary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    print("")
    print("matches:")
    for row in report["matches"]:
        print(
            "- "
            f"match_id: {row.get('match_id')}, "
            f"home_team: {row.get('home_team')}, "
            f"away_team: {row.get('away_team')}, "
            f"kickoff_at: {row.get('kickoff_at')}, "
            f"first_result_seen_at: {row.get('first_result_seen_at')}, "
            f"result_ingest_delay_minutes: {row.get('result_ingest_delay_minutes')}, "
            f"latest_status: {row.get('latest_status')}, "
            f"latest_result: {row.get('latest_result')}, "
            f"latest_audit_status: {row.get('latest_audit_status')}"
        )
    print("")
    print(f"result: {report['result']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="result ingest observation monitor")
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--source", default="500")
    parser.add_argument("--window-hours", type=int, default=monitor_window_hours())
    parser.add_argument("--since-hours", type=int, default=DEFAULT_SUMMARY_HOURS)
    parser.add_argument("--match-id")
    args = parser.parse_args(argv)
    if args.run_once == args.summary:
        print("usage: python -m api.result_ingest_monitor [--run-once|--summary]", file=sys.stderr)
        return 2
    if args.run_once:
        report = run_once(source=args.source, window_hours=args.window_hours)
        print_run_once_report(report)
        return 0 if report["ok"] else 1
    report = summary(since_hours=args.since_hours, match_id=args.match_id)
    print_summary_report(report)
    return 0 if report["result"] != "RESULT_INGEST_INCONSISTENT" else 1


def _load_monitor_matches(conn, *, now: datetime, window_hours: int) -> list[dict[str, Any]]:
    start = now - timedelta(hours=DEFAULT_LOOKBACK_HOURS)
    end = now + timedelta(hours=window_hours)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT m.match_id, m.match_num, m.home_team, m.away_team, m.kickoff_at, m.status,
                   m.result_home, m.result_away, m.ht_home, m.ht_away,
                   to_jsonb(m)->>'created_at' AS created_at,
                   to_jsonb(m)->>'updated_at' AS updated_at
            FROM matches m
            WHERE (kickoff_at BETWEEN %s AND %s)
               OR status IN ('closed', 'finished', 'completed')
            ORDER BY kickoff_at, match_id
            """,
            (start, end),
        )
        return [dict(row) for row in cur.fetchall()]


def _latest_results_sync_rows(conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT job_name, status, started_at, finished_at, summary, error
            FROM ops_log
            WHERE job_name = 'results_sync'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _first_result_seen_at(conn, match_id: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT min(observed_at)
            FROM result_ingest_observations
            WHERE match_id = %s
              AND result_state = 'result_present'
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return _ensure_aware(row[0]) if row and row[0] else None


def _insert_observations(conn, records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    with conn.cursor() as cur:
        for record in records:
            cur.execute(
                """
                INSERT INTO result_ingest_observations (
                  observed_at, match_id, match_num, home_team, away_team, kickoff_at,
                  status, result_home, result_away, ht_home, ht_away,
                  minutes_since_kickoff, estimated_fulltime_at, first_result_seen_at,
                  result_ingest_delay_minutes, result_state, audit_status,
                  latest_results_sync_at, latest_results_sync_status,
                  latest_results_sync_source, latest_results_sync_finished_updated,
                  latest_results_sync_skipped, latest_results_sync_skipped_reasons,
                  closed_missing_count, overdue_count, result_consistency_pass,
                  scheduler_stale, source_fetch_ok, parser_error, is_test_match, notes
                )
                VALUES (
                  %(observed_at)s, %(match_id)s, %(match_num)s, %(home_team)s, %(away_team)s, %(kickoff_at)s,
                  %(status)s, %(result_home)s, %(result_away)s, %(ht_home)s, %(ht_away)s,
                  %(minutes_since_kickoff)s, %(estimated_fulltime_at)s, %(first_result_seen_at)s,
                  %(result_ingest_delay_minutes)s, %(result_state)s, %(audit_status)s,
                  %(latest_results_sync_at)s, %(latest_results_sync_status)s,
                  %(latest_results_sync_source)s, %(latest_results_sync_finished_updated)s,
                  %(latest_results_sync_skipped)s, %(latest_results_sync_skipped_reasons)s,
                  %(closed_missing_count)s, %(overdue_count)s, %(result_consistency_pass)s,
                  %(scheduler_stale)s, %(source_fetch_ok)s, %(parser_error)s, %(is_test_match)s, %(notes)s
                )
                """,
                {**record, "latest_results_sync_skipped_reasons": Jsonb(record["latest_results_sync_skipped_reasons"])},
            )
    return len(records)


def _load_observations(conn, *, since_hours: int, match_id: str | None = None) -> list[dict[str, Any]]:
    threshold = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM result_ingest_observations
            WHERE observed_at >= %s
              AND (%s::text IS NULL OR match_id = %s)
            ORDER BY observed_at, match_id
            """,
            (threshold, match_id, match_id),
        )
        return [dict(row) for row in cur.fetchall()]


def _summary_match(row: dict[str, Any]) -> dict[str, Any]:
    latest_result = None
    if row.get("result_home") is not None and row.get("result_away") is not None:
        latest_result = f"{row['result_home']}-{row['result_away']}"
    return {
        "match_id": row.get("match_id"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "kickoff_at": _iso(row.get("kickoff_at")),
        "first_result_seen_at": _iso(row.get("first_result_seen_at")),
        "result_ingest_delay_minutes": row.get("result_ingest_delay_minutes"),
        "latest_status": row.get("status"),
        "latest_result": latest_result,
        "latest_audit_status": row.get("audit_status"),
    }


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    try:
        return _ensure_aware(datetime.fromisoformat(str(value)))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value).isoformat()
    return str(value)


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


if __name__ == "__main__":
    raise SystemExit(main())
