from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.external_result_sources import espn_scoreboard_dates_for_kickoff, fetch_espn_events_for_dates, fetch_source_events
from api.ops_log import record_ops_log, sanitize_error
from api.result_source_mapping import normalize_team_name
from api.results_sync import fetch_results_html, parse_results_html


CONFIRM_CODE = "APPLY_EXTERNAL_RESULTS"
JOB_NAME = "external_result_sync"
OVERDUE_MINUTES = 120
TIME_WINDOW_MINUTES = 120


@dataclass(frozen=True)
class ExternalResultPlan:
    match: dict[str, Any]
    action: str
    reason: str
    external_event: dict[str, Any] | None = None
    time_delta_minutes: int | None = None
    source_500_diagnostic: str | None = None
    source_500_status: str | None = None
    candidate_diagnostics: list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        event = self.external_event or {}
        return {
            "match_id": self.match.get("match_id"),
            "match_num": self.match.get("match_num"),
            "home_team": self.match.get("home_team"),
            "away_team": self.match.get("away_team"),
            "kickoff_at": _iso(self.match.get("kickoff_at")),
            "status": self.match.get("status"),
            "action": self.action,
            "reason": self.reason,
            "time_delta_minutes": self.time_delta_minutes,
            "external_source": event.get("source"),
            "external_source_url": event.get("source_url"),
            "external_source_date": event.get("external_source_date"),
            "external_event_id": event.get("external_id"),
            "raw_home": event.get("raw_home"),
            "raw_away": event.get("raw_away"),
            "normalized_external_home": event.get("normalized_home"),
            "normalized_external_away": event.get("normalized_away"),
            "external_status": event.get("status"),
            "result_home": event.get("result_home"),
            "result_away": event.get("result_away"),
            "reject_reason": _reject_reason(self.reason),
            "candidate_diagnostics": self.candidate_diagnostics or [],
            "source_500_diagnostic": self.source_500_diagnostic,
            "source_500_status": self.source_500_status,
        }


def dry_run(source: str, match_date: str, now: datetime | None = None) -> dict[str, Any]:
    return plan_external_results(source, match_date, now=now, mode="dry-run")


def apply_results(source: str, match_date: str, confirm: str | None, now: datetime | None = None) -> dict[str, Any]:
    if confirm != CONFIRM_CODE:
        raise ValueError(f"confirm code required: {CONFIRM_CODE}")
    report = plan_external_results(source, match_date, now=now, mode="confirm")
    updates = [item for item in report["matches"] if item["action"] == "update"]
    started_at = datetime.now(timezone.utc)
    updated_count = 0
    try:
        with connect() as conn, conn.cursor() as cur:
            for item in updates:
                cur.execute(
                    """
                    UPDATE matches
                    SET status = 'finished',
                        result_home = %s,
                        result_away = %s,
                        updated_at = %s
                    WHERE match_id = %s
                      AND status IN ('closed', 'scheduled')
                      AND result_home IS NULL
                      AND result_away IS NULL
                      AND kickoff_at <= %s
                    """,
                    (
                        item["result_home"],
                        item["result_away"],
                        datetime.now(timezone.utc),
                        item["match_id"],
                        (now or datetime.now(timezone.utc)) - timedelta(minutes=OVERDUE_MINUTES),
                    ),
                )
                updated_count += cur.rowcount
        report["updated_count"] = updated_count
        report["mode"] = "confirm"
        record_ops_log(JOB_NAME, "ok", started_at, summary=_ops_summary(report), error=None)
        return report
    except Exception as exc:
        record_ops_log(JOB_NAME, "error", started_at, summary={"source": source, "date": match_date}, error=sanitize_error(exc))
        raise


def plan_external_results(source: str, match_date: str, now: datetime | None = None, mode: str = "dry-run") -> dict[str, Any]:
    effective_now = now or datetime.now(timezone.utc)
    local_matches = load_local_candidates(match_date, effective_now)
    if source == "espn":
        scoreboard_dates = _espn_scoreboard_dates_for_matches(local_matches, match_date)
        source_report = fetch_espn_events_for_dates(scoreboard_dates)
    else:
        source_report = fetch_source_events(source, match_date)
    current_500 = current_500_match_ids()
    plans = [
        _plan_one(local, source_report["events"], current_500, effective_now, require_500_absence=source != "espn")
        for local in local_matches
    ]
    update_count = sum(1 for plan in plans if plan.action == "update")
    return {
        "mode": mode,
        "writes_db": mode == "confirm",
        "source": source,
        "date": match_date,
        "source_fetch_ok": source_report["source_fetch_ok"],
        "source_url": source_report["source_url"],
        "events_seen": source_report["events_seen"],
        "parser_error": source_report.get("parser_error"),
        "scoreboard_dates": source_report.get("scoreboard_dates", []),
        "local_candidates": len(local_matches),
        "would_update_count": update_count,
        "updated_count": 0,
        "matches": [plan.as_dict() for plan in plans],
        "ok": bool(source_report["source_fetch_ok"]) and source_report.get("parser_error") is None,
    }


def load_local_candidates(match_date: str, now: datetime) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status, result_home, result_away
            FROM matches
            WHERE kickoff_at::date = %s::date
              AND kickoff_at <= %s
            ORDER BY kickoff_at
            """,
            (match_date, now - timedelta(minutes=OVERDUE_MINUTES)),
        )
        return [dict(row) for row in cur.fetchall()]


def current_500_match_ids() -> dict[str, str]:
    try:
        parsed = parse_results_html(fetch_results_html())
    except Exception:
        return {"__source_error__": "source_500_fetch_error"}
    return {item.match_id: item.status for item in parsed}


def print_report(report: dict[str, Any]) -> None:
    print("External Result Sync Report")
    for key in ("mode", "writes_db", "source", "date", "source_fetch_ok", "source_url", "scoreboard_dates", "events_seen", "parser_error", "local_candidates", "would_update_count", "updated_count", "ok"):
        print(f"- {key}: {report.get(key)}")
    print("matches:")
    for item in report.get("matches", []):
        print(f"- match_id: {item.get('match_id')}")
        print(f"  match_num: {item.get('match_num')}")
        print(f"  local: {item.get('home_team')} vs {item.get('away_team')}")
        print(f"  kickoff_at: {item.get('kickoff_at')}")
        print(f"  action: {item.get('action')}")
        print(f"  reason: {item.get('reason')}")
        print(f"  external: {item.get('raw_home')} vs {item.get('raw_away')}")
        print(f"  normalized_external: {item.get('normalized_external_home')} vs {item.get('normalized_external_away')}")
        print(f"  external_status: {item.get('external_status')}")
        print(f"  external_source_date: {item.get('external_source_date')}")
        print(f"  score: {item.get('result_home')}-{item.get('result_away')}")
        print(f"  time_delta_minutes: {item.get('time_delta_minutes')}")
        print(f"  reject_reason: {item.get('reject_reason')}")
        for candidate in (item.get("candidate_diagnostics") or [])[:5]:
            print("  candidate:")
            print(f"    raw_home: {candidate.get('raw_home')}")
            print(f"    raw_away: {candidate.get('raw_away')}")
            print(f"    normalized_home: {candidate.get('normalized_home')}")
            print(f"    normalized_away: {candidate.get('normalized_away')}")
            print(f"    external_status: {candidate.get('external_status')}")
            print(f"    is_final: {candidate.get('is_final')}")
            print(f"    score: {candidate.get('score')}")
            print(f"    time_delta_minutes: {candidate.get('time_delta_minutes')}")
            print(f"    reject_reason: {candidate.get('reject_reason')}")
        print(f"  source_500_diagnostic: {item.get('source_500_diagnostic')}")
        print(f"  source_500_status: {item.get('source_500_status')}")
        print(f"  source_url: {item.get('external_source_url')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dry-run or apply structured external result fallback")
    parser.add_argument("--source", choices=("thesportsdb", "fifa", "espn"), required=True)
    parser.add_argument("--date", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm")
    args = parser.parse_args(argv)

    try:
        report = dry_run(args.source, args.date) if args.dry_run else apply_results(args.source, args.date, args.confirm)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    return 0 if report["ok"] else 1


def _plan_one(
    local: dict[str, Any],
    events: list[dict[str, Any]],
    current_500: dict[str, str],
    now: datetime,
    require_500_absence: bool = True,
) -> ExternalResultPlan:
    source_500_diagnostic, source_500_status = _source_500_diagnostic(local, current_500)
    if local.get("result_home") is not None or local.get("result_away") is not None:
        return ExternalResultPlan(local, "skip", "skipped_existing_result", source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)
    if str(local.get("status")) not in {"closed", "scheduled"}:
        return ExternalResultPlan(local, "skip", "local_status_not_eligible", source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)
    if require_500_absence and "__source_error__" in current_500:
        return ExternalResultPlan(local, "skip", "source_500_fetch_error", source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)
    if require_500_absence and str(local.get("match_id")) in current_500:
        return ExternalResultPlan(local, "skip", "source_500_still_present", source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)
    if not _local_is_eligible(local, now):
        return ExternalResultPlan(local, "skip", "local_not_eligible", source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)

    local_home = normalize_team_name(local.get("home_team"))
    local_away = normalize_team_name(local.get("away_team"))
    same_order = [
        event for event in events
        if event.get("normalized_home") == local_home and event.get("normalized_away") == local_away
    ]
    reversed_order = [
        event for event in events
        if event.get("normalized_home") == local_away and event.get("normalized_away") == local_home
    ]
    if reversed_order and not same_order:
        return ExternalResultPlan(local, "skip", "external_result_reversed_team_order", reversed_order[0], source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)
    if not same_order:
        return ExternalResultPlan(
            local,
            "skip",
            "external_result_no_candidate",
            source_500_diagnostic=source_500_diagnostic,
            source_500_status=source_500_status,
            candidate_diagnostics=_candidate_diagnostics(local, events),
        )

    timed = [(event, _time_delta_minutes(local.get("kickoff_at"), event.get("kickoff_at"))) for event in same_order]
    timed = [(event, delta) for event, delta in timed if delta is not None and delta <= TIME_WINDOW_MINUTES]
    if not timed:
        return ExternalResultPlan(
            local,
            "skip",
            "external_result_time_mismatch",
            same_order[0],
            source_500_diagnostic=source_500_diagnostic,
            source_500_status=source_500_status,
            candidate_diagnostics=_candidate_diagnostics(local, same_order),
        )
    if len(timed) > 1:
        return ExternalResultPlan(
            local,
            "skip",
            "external_result_ambiguous",
            timed[0][0],
            timed[0][1],
            source_500_diagnostic=source_500_diagnostic,
            source_500_status=source_500_status,
            candidate_diagnostics=_candidate_diagnostics(local, [event for event, _delta in timed]),
        )

    event, delta = timed[0]
    if event.get("status") != "finished":
        return ExternalResultPlan(
            local,
            "skip",
            "external_result_status_not_final",
            event,
            delta,
            source_500_diagnostic=source_500_diagnostic,
            source_500_status=source_500_status,
            candidate_diagnostics=_candidate_diagnostics(local, [event]),
        )
    if event.get("result_home") is None or event.get("result_away") is None:
        return ExternalResultPlan(
            local,
            "skip",
            "external_result_score_missing",
            event,
            delta,
            source_500_diagnostic=source_500_diagnostic,
            source_500_status=source_500_status,
            candidate_diagnostics=_candidate_diagnostics(local, [event]),
        )
    return ExternalResultPlan(local, "update", "external_result_matched", event, delta, source_500_diagnostic=source_500_diagnostic, source_500_status=source_500_status)


def _source_500_diagnostic(local: dict[str, Any], current_500: dict[str, str]) -> tuple[str, str | None]:
    if "__source_error__" in current_500:
        return str(current_500["__source_error__"]), None
    status = current_500.get(str(local.get("match_id")))
    if status is not None:
        return "source_500_still_present", status
    return "source_500_not_present", None


def _local_is_eligible(local: dict[str, Any], now: datetime) -> bool:
    kickoff = _as_datetime(local.get("kickoff_at"))
    return (
        str(local.get("status")) in {"closed", "scheduled"}
        and local.get("result_home") is None
        and local.get("result_away") is None
        and kickoff is not None
        and kickoff <= now - timedelta(minutes=OVERDUE_MINUTES)
    )


def _candidate_diagnostics(local: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    local_home = normalize_team_name(local.get("home_team"))
    local_away = normalize_team_name(local.get("away_team"))
    diagnostics = []
    for event in events[:10]:
        normalized_home = event.get("normalized_home")
        normalized_away = event.get("normalized_away")
        delta = _time_delta_minutes(local.get("kickoff_at"), event.get("kickoff_at"))
        score = _score_text(event.get("result_home"), event.get("result_away"))
        diagnostics.append(
            {
                "raw_home": event.get("raw_home"),
                "raw_away": event.get("raw_away"),
                "normalized_home": normalized_home,
                "normalized_away": normalized_away,
                "external_status": event.get("status"),
                "is_final": event.get("status") == "finished",
                "score": score,
                "time_delta_minutes": delta,
                "reject_reason": _candidate_reject_reason(local_home, local_away, event, delta),
            }
        )
    return diagnostics


def _candidate_reject_reason(local_home: str, local_away: str, event: dict[str, Any], delta: int | None) -> str | None:
    external_home = event.get("normalized_home")
    external_away = event.get("normalized_away")
    if external_home == local_away and external_away == local_home:
        return "reversed_team_order"
    if external_home != local_home or external_away != local_away:
        return "team_not_matched"
    if delta is None or delta > TIME_WINDOW_MINUTES:
        return "time_delta_too_large"
    if event.get("status") != "finished":
        return "status_not_final"
    if event.get("result_home") is None or event.get("result_away") is None:
        return "score_missing"
    return None


def _score_text(home: Any, away: Any) -> str | None:
    if home is None or away is None:
        return None
    return f"{home}-{away}"


def _reject_reason(reason: str) -> str | None:
    return {
        "external_result_no_candidate": "team_not_matched",
        "external_result_status_not_final": "status_not_final",
        "external_result_score_missing": "score_missing",
        "external_result_time_mismatch": "time_delta_too_large",
        "external_result_ambiguous": "ambiguous_candidate",
        "external_result_reversed_team_order": "reversed_team_order",
    }.get(reason)


def _ops_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": report["source"],
        "date": report["date"],
        "source_type": "external_structured_result",
        "scoreboard_dates": report.get("scoreboard_dates", []),
        "would_update_count": report["would_update_count"],
        "updated_count": report["updated_count"],
        "matched": [
            {
                "match_id": item["match_id"],
                "home_team": item["home_team"],
                "away_team": item["away_team"],
                "result_home": item["result_home"],
                "result_away": item["result_away"],
                "external_source_name": item["external_source"],
                "external_source_url": item["external_source_url"],
                "external_event_id": item["external_event_id"],
                "external_source_date": item.get("external_source_date"),
                "matched_by": ["team_name", "kickoff_time", "final_status"],
                "verified_mode": "structured_source",
            }
            for item in report["matches"]
            if item["action"] == "update"
        ],
    }


def _espn_scoreboard_dates_for_matches(matches: list[dict[str, Any]], fallback_date: str) -> list[str]:
    dates: list[str] = []
    for match in matches:
        kickoff = _as_datetime(match.get("kickoff_at"))
        if kickoff is None:
            continue
        for item in espn_scoreboard_dates_for_kickoff(kickoff):
            if item not in dates:
                dates.append(item)
    fallback = fallback_date.replace("-", "")
    if fallback not in dates:
        dates.append(fallback)
    return dates


def _time_delta_minutes(left: Any, right: Any) -> int | None:
    left_dt = _as_datetime(left)
    right_dt = _as_datetime(right)
    if left_dt is None or right_dt is None:
        return None
    return int(abs((left_dt - right_dt).total_seconds()) // 60)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> str | None:
    dt = _as_datetime(value)
    return dt.isoformat() if dt else (str(value) if value is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
