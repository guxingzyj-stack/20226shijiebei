from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.result_overdue_report import overdue_matches
from api.result_source_mapping import normalize_team_name
from api.sources import qiumibao, zhibo8


DATE_WINDOW_HOURS = 4


@dataclass(frozen=True)
class WorldCupLiveMatch:
    source_name: str
    source_fetch_ok: bool
    zhibo8_match_ref: str | None = None
    zhibo8_url: str | None = None
    zhibo8_home_team: str | None = None
    zhibo8_away_team: str | None = None
    zhibo8_kickoff_at: str | None = None
    qiumibao_match_id: str | None = None
    qiumibao_left_id: str | None = None
    qiumibao_right_id: str | None = None
    qiumibao_status: str | None = None
    qiumibao_period_cn: str | None = None
    qiumibao_score_home: int | None = None
    qiumibao_score_away: int | None = None
    qiumibao_half_score_home: int | None = None
    qiumibao_half_score_away: int | None = None
    home_team: str | None = None
    away_team: str | None = None
    normalized_home_team: str = ""
    normalized_away_team: str = ""
    kickoff_at: str | None = None
    status: str | None = None
    score: str | None = None
    half_score: str | None = None
    minute: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    mapping_status: str = "mapping_missing"
    mapping_reason: str | None = None
    parser_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def fetch_worldcup_live_report(fetch_zhibo8=zhibo8.homepage_source_report, fetch_qiumibao=qiumibao.score_source_report, fetch_events=qiumibao.events_source_report) -> dict[str, Any]:
    zhibo8_report = fetch_zhibo8()
    qiumibao_report = fetch_qiumibao(date=None)
    matches = build_worldcup_live_matches(
        zhibo8_report.get("matches") or [],
        qiumibao_report.get("matches") or [],
        fetch_events=fetch_events,
    )
    return {
        "mode": "dry-run",
        "writes_db": False,
        "source_fetch_ok": bool(zhibo8_report.get("source_fetch_ok")) and bool(qiumibao_report.get("source_fetch_ok")),
        "zhibo8_fetch_ok": bool(zhibo8_report.get("source_fetch_ok")),
        "qiumibao_fetch_ok": bool(qiumibao_report.get("source_fetch_ok")),
        "zhibo8_parser_error": zhibo8_report.get("parser_error"),
        "qiumibao_parser_error": qiumibao_report.get("parser_error"),
        "zhibo8_matches_seen": len(zhibo8_report.get("matches") or []),
        "qiumibao_matches_seen": len(qiumibao_report.get("matches") or []),
        "merged_matches_count": len(matches),
        "mapping_status_summary": _status_counts(match.mapping_status for match in matches),
        "conflicts_count": 0,
        "matches": [match.as_dict() for match in matches],
    }


def build_worldcup_live_matches(
    zhibo8_matches: list[dict[str, Any]],
    qiumibao_matches: list[dict[str, Any]],
    fetch_events=qiumibao.events_source_report,
    include_events: bool = False,
) -> list[WorldCupLiveMatch]:
    by_external_id = {str(row.get("external_id")): row for row in qiumibao_matches if row.get("external_id") is not None}
    used: set[str] = set()
    live_matches: list[WorldCupLiveMatch] = []
    for schedule in zhibo8_matches:
        qrow, status, reason = _match_qiumibao(schedule, qiumibao_matches, by_external_id)
        if qrow and qrow.get("external_id") is not None:
            used.add(str(qrow["external_id"]))
        events = _events_for_match(schedule, qrow, fetch_events, include_events)
        live_matches.append(_merge_match(schedule, qrow, status, reason, events))
    for qrow in qiumibao_matches:
        external_id = str(qrow.get("external_id")) if qrow.get("external_id") is not None else None
        if external_id and external_id in used:
            continue
        if qrow.get("home_team") or qrow.get("away_team"):
            events = _events_for_match(None, qrow, fetch_events, include_events)
            live_matches.append(_merge_match(None, qrow, "live_source_only", "qiumibao row had no zhibo8 schedule match", events))
    return live_matches


def compare_local_recent_finished(limit: int = 10) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = _recent_finished_locals(limit)
    comparisons = [_compare_local_to_live(local, live_report["matches"]) for local in locals_]
    return _comparison_report(live_report, comparisons)


def compare_local_all_overdue() -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = [_local_match(str(row["match_id"])) for row in overdue_matches(limit=20)]
    comparisons = [_compare_local_to_live(local, live_report["matches"]) for local in locals_ if local]
    report = _comparison_report(live_report, comparisons)
    report["overdue_count"] = len(locals_)
    return report


def compare_local_match(match_id: str) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    local = _local_match(match_id)
    comparisons = [_compare_local_to_live(local, live_report["matches"])] if local else []
    return _comparison_report(live_report, comparisons)


def _merge_match(schedule: dict[str, Any] | None, qrow: dict[str, Any] | None, mapping_status: str, mapping_reason: str, events: list[dict[str, Any]]) -> WorldCupLiveMatch:
    home = (schedule or {}).get("home_team") or (qrow or {}).get("home_team")
    away = (schedule or {}).get("away_team") or (qrow or {}).get("away_team")
    kickoff = (schedule or {}).get("kickoff_at") or (qrow or {}).get("kickoff_at")
    q_home = (qrow or {}).get("result_home")
    q_away = (qrow or {}).get("result_away")
    score = _score(q_home, q_away)
    ht_score = _score((qrow or {}).get("ht_home"), (qrow or {}).get("ht_away"))
    return WorldCupLiveMatch(
        source_name="zhibo8+qiumibao",
        source_fetch_ok=True,
        zhibo8_match_ref=(schedule or {}).get("zhibo8_match_ref"),
        zhibo8_url=(schedule or {}).get("zhibo8_url"),
        zhibo8_home_team=(schedule or {}).get("home_team"),
        zhibo8_away_team=(schedule or {}).get("away_team"),
        zhibo8_kickoff_at=(schedule or {}).get("kickoff_at"),
        qiumibao_match_id=(qrow or {}).get("external_id"),
        qiumibao_left_id=(qrow or {}).get("left_id"),
        qiumibao_right_id=(qrow or {}).get("right_id"),
        qiumibao_status=(qrow or {}).get("status"),
        qiumibao_period_cn=(qrow or {}).get("period_cn"),
        qiumibao_score_home=q_home,
        qiumibao_score_away=q_away,
        qiumibao_half_score_home=(qrow or {}).get("ht_home"),
        qiumibao_half_score_away=(qrow or {}).get("ht_away"),
        home_team=home,
        away_team=away,
        normalized_home_team=normalize_team_name(home),
        normalized_away_team=normalize_team_name(away),
        kickoff_at=kickoff,
        status=(qrow or {}).get("status") or (schedule or {}).get("status_text"),
        score=score,
        half_score=ht_score,
        minute="FT" if (qrow or {}).get("status") == "finished" else None,
        events=events,
        mapping_status=mapping_status,
        mapping_reason=mapping_reason,
        parser_error=(schedule or {}).get("parser_error") or (qrow or {}).get("parser_error"),
    )


def _match_qiumibao(schedule: dict[str, Any], qrows: list[dict[str, Any]], by_external_id: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str, str]:
    ref = str(schedule.get("zhibo8_match_ref") or "")
    if ref and ref in by_external_id:
        return by_external_id[ref], "matched", "zhibo8 saishi id matched qiumibao score id"
    kickoff = _as_datetime(schedule.get("kickoff_at"))
    if kickoff is None:
        return None, "mapping_missing", "zhibo8 kickoff missing"
    candidates = [
        row
        for row in qrows
        if _as_datetime(row.get("kickoff_at")) is not None and abs((_as_datetime(row.get("kickoff_at")) - kickoff).total_seconds()) <= 30 * 60
    ]
    if len(candidates) == 1:
        return candidates[0], "matched", "unique qiumibao row in 30 minute kickoff window"
    if len(candidates) > 1:
        return None, "ambiguous_candidates", "multiple qiumibao rows in kickoff window"
    return None, "mapping_missing", "no qiumibao row matched zhibo8 ref or kickoff window"


def _events_for_match(schedule: dict[str, Any] | None, qrow: dict[str, Any] | None, fetch_events, include_events: bool) -> list[dict[str, Any]]:
    if not include_events or not qrow or not qrow.get("external_id"):
        return []
    date = _date_for_live(schedule, qrow)
    if not date:
        return []
    report = fetch_events(date, str(qrow["external_id"]))
    return report.get("events") or [] if report.get("source_fetch_ok") else []


def _compare_local_to_live(local: dict[str, Any], live_matches: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        match
        for match in live_matches
        if normalize_team_name(match.get("home_team")) == normalize_team_name(local.get("home_team"))
        and normalize_team_name(match.get("away_team")) == normalize_team_name(local.get("away_team"))
        and _within_hours(local.get("kickoff_at"), match.get("kickoff_at"), DATE_WINDOW_HOURS)
    ]
    if len(candidates) > 1:
        return _local_result(local, None, "AMBIGUOUS_CANDIDATES", "multiple live matches matched local team/time")
    if not candidates:
        return _local_result(local, None, "MAPPING_MISSING", "no live match matched local team/time")
    live = candidates[0]
    local_score = _score(local.get("result_home"), local.get("result_away"))
    live_score = live.get("score")
    status = str(live.get("status") or "")
    if local_score and live_score and local_score != live_score:
        comparison = "CONFLICT_NEEDS_REVIEW"
    elif local_score and live_score == local_score:
        comparison = "OK_MATCH"
    elif not local_score and status == "finished" and live_score:
        comparison = "NEEDS_VERIFIED_FALLBACK"
    elif not live_score or status != "finished":
        comparison = "WAIT_SOURCE"
    else:
        comparison = "LIVE_SOURCE_ONLY"
    return _local_result(local, live, comparison, None)


def _local_result(local: dict[str, Any], live: dict[str, Any] | None, comparison_status: str, reason: str | None) -> dict[str, Any]:
    return {
        "local_match_id": local.get("match_id"),
        "local_home_team": local.get("home_team"),
        "local_away_team": local.get("away_team"),
        "local_kickoff_at": _iso(local.get("kickoff_at")),
        "live_home_team": (live or {}).get("home_team"),
        "live_away_team": (live or {}).get("away_team"),
        "live_kickoff_at": (live or {}).get("kickoff_at"),
        "qiumibao_match_id": (live or {}).get("qiumibao_match_id"),
        "live_status": (live or {}).get("status"),
        "live_score": (live or {}).get("score"),
        "live_half_score": (live or {}).get("half_score"),
        "minute": (live or {}).get("minute"),
        "events_count": len((live or {}).get("events") or []),
        "mapping_status": (live or {}).get("mapping_status") or comparison_status,
        "comparison_status": comparison_status,
        "suggested_action": comparison_status,
        "reason": reason,
    }


def _comparison_report(live_report: dict[str, Any], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "writes_db": False,
        "source_fetch_ok": live_report["source_fetch_ok"],
        "zhibo8_matches_seen": live_report["zhibo8_matches_seen"],
        "qiumibao_matches_seen": live_report["qiumibao_matches_seen"],
        "merged_matches_count": live_report["merged_matches_count"],
        "mapping_status_summary": live_report["mapping_status_summary"],
        "conflicts_count": sum(1 for row in comparisons if row["comparison_status"] == "CONFLICT_NEEDS_REVIEW"),
        "overdue_count": 0,
        "comparisons": comparisons,
    }


def _recent_finished_locals(limit: int) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
            ORDER BY kickoff_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _local_match(match_id: str) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE match_id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _status_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _score(home: Any, away: Any) -> str | None:
    if home is None or away is None:
        return None
    return f"{home}-{away}"


def _within_hours(left: Any, right: Any, hours: int) -> bool:
    left_dt = _as_datetime(left)
    right_dt = _as_datetime(right)
    if left_dt is None or right_dt is None:
        return False
    return abs((left_dt - right_dt).total_seconds()) <= hours * 3600


def _date_for_live(schedule: dict[str, Any] | None, qrow: dict[str, Any]) -> str | None:
    dt = _as_datetime((schedule or {}).get("kickoff_at") or qrow.get("kickoff_at"))
    return dt.date().isoformat() if dt else None


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
