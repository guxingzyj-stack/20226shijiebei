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
                has_missing_before_lookup=lambda match_id: _has_missing_before_result(conn, match_id),
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
    has_missing_before_lookup=None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    has_missing_before_lookup = has_missing_before_lookup or (lambda match_id: False)
    for row in rows:
        audit = classify_match(row, now=now)
        kickoff_at = _ensure_aware(row["kickoff_at"])
        estimated_fulltime_at = kickoff_at + timedelta(minutes=120)
        first_seen = None
        delay = None
        notes = None
        if audit["result_state"] == "result_present":
            match_id = str(row["match_id"])
            if has_missing_before_lookup(match_id):
                first_seen = _result_seen_time_from_row(row, kickoff_at) or first_seen_lookup(match_id) or now
                delay = int((first_seen - estimated_fulltime_at).total_seconds() // 60)
            else:
                notes = "baseline_result_present"
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
                "notes": notes,
            }
        )
    return records


def summarize_observations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    histories = _group_observations_by_match(rows)
    match_summaries = [_summarize_match_history(history) for history in histories.values()]
    latest_rows = [item["latest"] for item in match_summaries]
    result_present = [row for row in latest_rows if row.get("result_state") == "result_present"]
    missing = [row for row in latest_rows if row.get("result_state") != "result_present"]
    true_delay_rows = [item for item in match_summaries if item["true_delay_measured"]]
    baseline_rows = [item for item in match_summaries if item["baseline_result_present"]]
    delay_unknown_rows = [item for item in match_summaries if item["delay_unknown"]]
    delays = [
        int(item["delay_minutes"])
        for item in true_delay_rows
        if item.get("delay_minutes") is not None
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
    status = conclude_ingest_health(match_summaries)
    return {
        "mode": "dry-run/read-only-summary",
        "writes_business_tables": False,
        "summary": {
            "observations_count": len(rows),
            "observed_matches": len(latest_rows),
            "result_present_matches": len(result_present),
            "missing_result_matches": len(missing),
            "baseline_result_present_matches": len(baseline_rows),
            "true_delay_measured_matches": len(true_delay_rows),
            "delay_unknown_matches": len(delay_unknown_rows),
            "over_60min_missing_count": len(over_60_missing),
            "over_120min_missing_count": len(over_120_missing),
            "median_ingest_delay_minutes": int(statistics.median(delays)) if delays else None,
            "max_ingest_delay_minutes": max(delays) if delays else None,
            "delay_precision_note": _delay_precision_note(),
            "delay_precision_minutes": monitor_interval_minutes(),
            "scheduler_stale_seen_count": len([row for row in rows if row.get("scheduler_stale") is True]),
            "result_consistency_failed_count": len([row for row in rows if row.get("result_consistency_pass") is False]),
        },
        "matches": [
            _summary_match(item["latest"], item)
            for item in sorted(match_summaries, key=lambda item: str(item["latest"].get("kickoff_at")))
        ],
        "result": status,
        "inconsistent_count": len(inconsistent),
    }


def conclude_ingest_health(match_summaries: list[dict[str, Any]]) -> str:
    latest_rows = [item["latest"] for item in match_summaries]
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
    true_delays = [
        int(item["delay_minutes"])
        for item in match_summaries
        if item["true_delay_measured"] and item.get("delay_minutes") is not None
    ]
    if any(delay > 120 for delay in true_delays):
        return "RESULT_INGEST_SLOW_NEEDS_ACTION"
    if any(delay > 60 for delay in true_delays):
        return "RESULT_INGEST_SLOW_OBSERVE"
    if match_summaries and all(item["baseline_result_present"] or item["latest"].get("result_state") == "result_present" for item in match_summaries) and not true_delays:
        return "RESULT_INGEST_BASELINE_ONLY"
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


def _has_missing_before_result(conn, match_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM result_ingest_observations
              WHERE match_id = %s
                AND result_state = 'result_missing'
            )
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return bool(row[0]) if row else False


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


def _group_observations_by_match(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["match_id"]), []).append(row)
    for history in grouped.values():
        history.sort(key=lambda item: _ensure_aware(item["observed_at"]))
    return grouped


def _summarize_match_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    first = history[0]
    latest = history[-1]
    baseline_result_present = first.get("result_state") == "result_present"
    first_present_index = next((index for index, row in enumerate(history) if row.get("result_state") == "result_present"), None)
    true_delay_measured = (
        first_present_index is not None
        and any(row.get("result_state") != "result_present" for row in history[:first_present_index])
    )
    delay_minutes = None
    if true_delay_measured and first_present_index is not None:
        present_row = history[first_present_index]
        delay_minutes = _delay_from_observation(present_row)
    delay_unknown = latest.get("result_state") == "result_present" and not true_delay_measured
    return {
        "first": first,
        "latest": latest,
        "baseline_result_present": baseline_result_present,
        "true_delay_measured": true_delay_measured,
        "delay_unknown": delay_unknown,
        "delay_minutes": delay_minutes,
    }


def _delay_from_observation(row: dict[str, Any]) -> int | None:
    if row.get("result_ingest_delay_minutes") is not None:
        return int(row["result_ingest_delay_minutes"])
    seen_at = row.get("first_result_seen_at") or row.get("observed_at")
    estimated = row.get("estimated_fulltime_at")
    if seen_at is None or estimated is None:
        return None
    return int((_ensure_aware(seen_at) - _ensure_aware(estimated)).total_seconds() // 60)


def _summary_match(row: dict[str, Any], history_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    latest_result = None
    if row.get("result_home") is not None and row.get("result_away") is not None:
        latest_result = f"{row['result_home']}-{row['result_away']}"
    history_summary = history_summary or {}
    return {
        "match_id": row.get("match_id"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "kickoff_at": _iso(row.get("kickoff_at")),
        "first_result_seen_at": None if history_summary.get("delay_unknown") else _iso(row.get("first_result_seen_at")),
        "result_ingest_delay_minutes": history_summary.get("delay_minutes"),
        "baseline_result_present": history_summary.get("baseline_result_present"),
        "true_delay_measured": history_summary.get("true_delay_measured"),
        "delay_unknown": history_summary.get("delay_unknown"),
        "latest_status": row.get("status"),
        "latest_result": latest_result,
        "latest_audit_status": row.get("audit_status"),
    }


def _ensure_aware(value: datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _result_seen_time_from_row(row: dict[str, Any], kickoff_at: datetime) -> datetime | None:
    updated_at = _parse_datetime(row.get("updated_at"))
    if updated_at is None:
        return None
    return updated_at if updated_at > kickoff_at else None


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


def _delay_precision_note() -> str:
    return (
        "result_ingest_delay_minutes is estimated relative to kickoff_at + 120min; "
        "it may include stoppage time, final-score confirmation, 500 source update time, "
        "results_sync interval, and monitor observation precision. Observation-derived "
        f"samples have precision +/-{monitor_interval_minutes()} minutes."
    )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


if __name__ == "__main__":
    raise SystemExit(main())
