from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import sys
from typing import Any, Callable

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import recent_ops_log
from api.results_sync import DEFAULT_RESULTS_URL, DEFAULT_SOURCE_NAME, fetch_results_html, parse_results_html


RECENTLY_STARTED_MINUTES = 120
FINISHED_STATUSES = {"finished", "completed"}
OPEN_STATUSES = {"scheduled", "closed"}
HALF_TIME_FIELD_TOKENS = (
    "data-half-score",
    "data-ht-score",
    "half-score",
    "ht-score",
    "half_score",
    "hscore",
    "half",
    "ht",
    "hafu",
    "rqspft",
)


@dataclass(frozen=True)
class MatchAuditRow:
    match_id: str
    match_num: str | None
    home_team: str
    away_team: str
    kickoff_at: datetime
    status: str
    result_home: int | None
    result_away: int | None
    ht_home: int | None
    ht_away: int | None
    created_at: str | None = None
    updated_at: str | None = None


def classify_match(row: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = _ensure_aware(now or datetime.now(timezone.utc))
    kickoff_at = _ensure_aware(row["kickoff_at"])
    status = str(row.get("status") or "").strip().lower()
    result_present = row.get("result_home") is not None and row.get("result_away") is not None
    result_state = "result_present" if result_present else "result_missing"
    minutes_since_kickoff = int((now - kickoff_at).total_seconds() // 60)

    if status in FINISHED_STATUSES and not result_present:
        audit_status = "FINISHED_NULL_ERROR"
    elif status not in FINISHED_STATUSES and result_present:
        audit_status = "NON_FINISHED_HAS_RESULT_ERROR"
    elif result_present:
        audit_status = "OK_RESULT_PRESENT"
    elif kickoff_at > now:
        audit_status = "WAIT_NOT_STARTED"
    elif minutes_since_kickoff < RECENTLY_STARTED_MINUTES:
        audit_status = "WAIT_RECENTLY_STARTED"
    else:
        audit_status = "MISSING_RESULT_OVERDUE"

    return {
        "match_id": row.get("match_id"),
        "match_num": row.get("match_num"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "kickoff_at": kickoff_at.isoformat(),
        "minutes_since_kickoff": minutes_since_kickoff,
        "status": status,
        "result_home": row.get("result_home"),
        "result_away": row.get("result_away"),
        "ht_home": row.get("ht_home"),
        "ht_away": row.get("ht_away"),
        "result_state": result_state,
        "audit_status": audit_status,
        "created_at": _as_iso(row.get("created_at")),
        "updated_at": _as_iso(row.get("updated_at")),
    }


def build_coverage_report(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    source: str = "500",
    scope: str = "recent",
    ops_rows: list[dict[str, Any]] | None = None,
    include_half_time_probe: bool = False,
    html: str | None = None,
) -> dict[str, Any]:
    now = _ensure_aware(now or datetime.now(timezone.utc))
    audited = [classify_match(row, now=now) for row in rows]

    total_matches = len(audited)
    started = [row for row in audited if row["minutes_since_kickoff"] >= 0]
    started_with_result = [row for row in started if row["result_state"] == "result_present"]
    started_missing_result = [row for row in started if row["result_state"] == "result_missing"]
    finished_with_result = [
        row for row in audited if row["status"] in FINISHED_STATUSES and row["result_state"] == "result_present"
    ]
    finished_missing = [
        row for row in audited if row["status"] in FINISHED_STATUSES and row["result_state"] == "result_missing"
    ]
    non_finished_with_result = [
        row for row in audited if row["status"] not in FINISHED_STATUSES and row["result_state"] == "result_present"
    ]
    closed_missing = [
        row
        for row in audited
        if row["status"] in OPEN_STATUSES
        and row["minutes_since_kickoff"] >= 0
        and row["result_state"] == "result_missing"
    ]
    overdue = [row for row in audited if row["audit_status"] == "MISSING_RESULT_OVERDUE"]
    coverage_rate = _safe_rate(len(started_with_result), len(started))

    summary = {
        "total_matches": total_matches,
        "started_matches": len(started),
        "started_with_result": len(started_with_result),
        "started_missing_result": len(started_missing_result),
        "started_result_coverage_rate": coverage_rate,
        "closed_missing_count": len(closed_missing),
        "finished_with_result_count": len(finished_with_result),
        "finished_missing_count": len(finished_missing),
        "non_finished_with_result_count": len(non_finished_with_result),
        "ready_for_settlement_count": len(finished_with_result),
        "overdue_count": len(overdue),
    }

    report: dict[str, Any] = {
        "title": "500 Result Coverage Audit",
        "mode": "dry-run",
        "writes_db": False,
        "source": _source_label(source),
        "scope": scope,
        "generated_at": now.isoformat(),
        "summary": summary,
        "results_sync": summarize_results_sync_ops(ops_rows or []),
        "matches": audited,
        "conclusion": conclude_coverage(summary),
    }
    if include_half_time_probe:
        report["half_time_probe"] = build_half_time_probe(rows, html=html)
    return report


def build_half_time_probe(rows: list[dict[str, Any]], html: str | None = None) -> dict[str, Any]:
    html = html or ""
    source_fetch_ok = bool(html)
    lower_html = html.lower()
    raw_candidates = {
        token: _token_hits(lower_html, token)
        for token in HALF_TIME_FIELD_TOKENS
        if _token_hits(lower_html, token) > 0
    }
    parser_extracts_half_time = False
    parser_error: str | None = None
    if html:
        try:
            parsed = parse_results_html(html)
            parser_extracts_half_time = any(item.ht_home is not None and item.ht_away is not None for item in parsed)
        except Exception as exc:
            parser_error = f"{type(exc).__name__}: {exc}"[:300]

    finished_rows = [
        row
        for row in rows
        if str(row.get("status") or "").lower() in FINISHED_STATUSES
        and row.get("result_home") is not None
        and row.get("result_away") is not None
    ]
    finished_with_ht = [
        row for row in finished_rows if row.get("ht_home") is not None and row.get("ht_away") is not None
    ]
    finished_missing_ht = len(finished_rows) - len(finished_with_ht)
    db_ht_coverage = {
        "finished_matches": len(finished_rows),
        "finished_with_ht": len(finished_with_ht),
        "finished_missing_ht": finished_missing_ht,
        "ht_coverage_rate": _safe_rate(len(finished_with_ht), len(finished_rows)),
    }

    if finished_rows and finished_missing_ht == 0:
        conclusion = "HT_COVERAGE_OK"
    elif source_fetch_ok and raw_candidates and not parser_extracts_half_time and finished_missing_ht > 0:
        conclusion = "HT_SOURCE_AVAILABLE_PARSER_MISSING"
    elif source_fetch_ok and not raw_candidates:
        conclusion = "HT_SOURCE_UNAVAILABLE"
    else:
        conclusion = "HT_COVERAGE_UNKNOWN"

    return {
        "source_fetch_ok": source_fetch_ok,
        "source_url": DEFAULT_RESULTS_URL,
        "raw_field_candidates": raw_candidates,
        "parser_extracts_half_time": parser_extracts_half_time,
        "parser_error": parser_error,
        "db_ht_coverage": db_ht_coverage,
        "conclusion": conclusion,
        "writes_db": False,
    }


def summarize_results_sync_ops(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "latest_run_at": None,
            "source": None,
            "status": "missing_ops_log",
            "finished_updated": None,
            "skipped": None,
            "skipped_reasons": {},
            "source_fetch_ok": None,
            "parser_error": None,
        }
    latest = rows[0]
    summary = latest.get("summary") or {}
    return {
        "latest_run_at": _as_iso(latest.get("started_at")),
        "source": summary.get("source_name") or summary.get("source") or DEFAULT_SOURCE_NAME,
        "status": latest.get("status"),
        "finished_updated": summary.get("finished_updated"),
        "skipped": summary.get("skipped"),
        "skipped_reasons": summary.get("skipped_reasons") or {},
        "source_fetch_ok": summary.get("source_fetch_ok"),
        "parser_error": latest.get("error"),
    }


def conclude_coverage(summary: dict[str, Any]) -> str:
    if summary["finished_missing_count"] or summary["non_finished_with_result_count"]:
        return "500_RESULT_SOURCE_PARTIAL"
    started = summary["started_matches"]
    if started == 0:
        return "500_RESULT_SOURCE_PARTIAL"
    coverage = summary["started_result_coverage_rate"] or 0
    if summary["overdue_count"] == 0 and coverage >= 0.8:
        return "500_RESULT_SOURCE_SUFFICIENT"
    if summary["started_with_result"] > 0:
        return "500_RESULT_SOURCE_PARTIAL"
    return "500_RESULT_SOURCE_INSUFFICIENT"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.source != "500":
        print("Only --source 500 is supported in this audit.", file=sys.stderr)
        return 2

    rows = _load_match_rows()
    now = datetime.now(timezone.utc)
    filtered = _filter_rows(rows, args, now)
    ops_rows = _safe_recent_ops_log()
    html = None
    include_half_time_probe = bool(args.half_time_fields or args.include_half_time_probe)
    if include_half_time_probe:
        html = _safe_fetch_html()

    report = build_coverage_report(
        filtered,
        now=now,
        source=args.source,
        scope=_scope_name(args),
        ops_rows=ops_rows,
        include_half_time_probe=include_half_time_probe,
        html=html,
    )
    _print_report(report, limit=args.limit)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only 500 result coverage audit")
    parser.add_argument("--source", required=True, choices=["500"], help="Result source to audit")
    parser.add_argument("--recent", action="store_true", help="Audit recent window")
    parser.add_argument("--since-hours", type=int, default=None, help="Audit matches since N hours ago")
    parser.add_argument("--all-started", action="store_true", help="Audit every match whose kickoff is in the past")
    parser.add_argument("--closed-missing", action="store_true", help="Only show started scheduled/closed matches missing result")
    parser.add_argument("--finished", action="store_true", help="Only show finished/completed matches")
    parser.add_argument("--half-time-fields", action="store_true", help="Run half-time field audit")
    parser.add_argument("--include-half-time-probe", action="store_true", help="Include half-time probe in a normal report")
    parser.add_argument("--limit", type=int, default=40, help="Maximum match rows to print")
    return parser.parse_args(argv)


def _load_match_rows() -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                m.match_id,
                m.match_num,
                m.home_team,
                m.away_team,
                m.kickoff_at,
                m.status,
                m.result_home,
                m.result_away,
                m.ht_home,
                m.ht_away,
                to_jsonb(m)->>'created_at' AS created_at,
                to_jsonb(m)->>'updated_at' AS updated_at
            FROM matches m
            ORDER BY m.kickoff_at, m.match_id
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _filter_rows(rows: list[dict[str, Any]], args: argparse.Namespace, now: datetime) -> list[dict[str, Any]]:
    if args.finished:
        return [row for row in rows if str(row.get("status") or "").lower() in FINISHED_STATUSES]
    if args.closed_missing:
        return [
            row
            for row in rows
            if str(row.get("status") or "").lower() in OPEN_STATUSES
            and _ensure_aware(row["kickoff_at"]) <= now
            and (row.get("result_home") is None or row.get("result_away") is None)
        ]
    if args.all_started:
        return [row for row in rows if _ensure_aware(row["kickoff_at"]) <= now]
    if args.since_hours is not None:
        threshold_minutes = args.since_hours * 60
        return [
            row
            for row in rows
            if 0 <= int((now - _ensure_aware(row["kickoff_at"])).total_seconds() // 60) <= threshold_minutes
        ]
    # Default to recent: past 48 hours through next 24 hours.
    return [
        row
        for row in rows
        if -24 * 60 <= int((now - _ensure_aware(row["kickoff_at"])).total_seconds() // 60) <= 48 * 60
    ]


def _scope_name(args: argparse.Namespace) -> str:
    if args.finished:
        return "finished"
    if args.closed_missing:
        return "closed-missing"
    if args.all_started:
        return "all-started"
    if args.since_hours is not None:
        return f"since-hours-{args.since_hours}"
    if args.half_time_fields and not args.recent:
        return "half-time-fields"
    return "recent"


def _safe_recent_ops_log() -> list[dict[str, Any]]:
    try:
        return recent_ops_log("results_sync", limit=1)
    except Exception as exc:
        return [{"status": "ops_log_error", "summary": {}, "error": f"{type(exc).__name__}: {exc}"[:300]}]


def _safe_fetch_html(fetcher: Callable[[], str] = fetch_results_html) -> str:
    try:
        return fetcher()
    except Exception:
        return ""


def _print_report(report: dict[str, Any], *, limit: int) -> None:
    print(report["title"])
    print(f"- mode: {report['mode']}")
    print(f"- writes_db: {str(report['writes_db']).lower()}")
    print(f"- source: {report['source']}")
    print(f"- scope: {report['scope']}")
    print("")
    print("summary:")
    for key, value in report["summary"].items():
        print(f"- {key}: {value}")
    print("")
    print("results_sync:")
    for key, value in report["results_sync"].items():
        print(f"- {key}: {value}")
    if "half_time_probe" in report:
        print("")
        print("half_time_probe:")
        probe = report["half_time_probe"]
        print(f"- source_fetch_ok: {probe['source_fetch_ok']}")
        print(f"- source_url: {probe['source_url']}")
        print(f"- raw_field_candidates: {probe['raw_field_candidates']}")
        print(f"- parser_extracts_half_time: {probe['parser_extracts_half_time']}")
        print(f"- parser_error: {probe['parser_error']}")
        print("- db_ht_coverage:")
        for key, value in probe["db_ht_coverage"].items():
            print(f"  - {key}: {value}")
        print(f"- conclusion: {probe['conclusion']}")
        print(f"- writes_db: {str(probe['writes_db']).lower()}")
    print("")
    print("matches:")
    for row in report["matches"][: max(limit, 0)]:
        print(
            "- "
            f"match_id: {row['match_id']}, "
            f"match_num: {row['match_num']}, "
            f"home_team: {row['home_team']}, "
            f"away_team: {row['away_team']}, "
            f"kickoff_at: {row['kickoff_at']}, "
            f"minutes_since_kickoff: {row['minutes_since_kickoff']}, "
            f"status: {row['status']}, "
            f"result_home: {row['result_home']}, "
            f"result_away: {row['result_away']}, "
            f"ht_home: {row['ht_home']}, "
            f"ht_away: {row['ht_away']}, "
            f"result_state: {row['result_state']}, "
            f"audit_status: {row['audit_status']}"
        )
    if len(report["matches"]) > limit:
        print(f"- omitted_matches: {len(report['matches']) - limit}")
    print("")
    print("conclusion:")
    print(f"- {report['conclusion']}")


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value).isoformat()
    return str(value)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _source_label(source: str) -> str:
    if source == "500":
        return DEFAULT_SOURCE_NAME
    return source


def _token_hits(text: str, token: str) -> int:
    if token in {"ht", "half"}:
        return len(re.findall(rf"(?<![a-z0-9_-]){re.escape(token)}(?![a-z0-9_-])", text))
    return text.count(token)


if __name__ == "__main__":
    raise SystemExit(main())
