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
LOCAL_MAPPING_WINDOW_HOURS = 4
AMBIGUOUS_SCORE_DELTA = 0.05


@dataclass(frozen=True)
class WorldCupLiveMatch:
    source_name: str
    source_fetch_ok: bool
    zhibo8_match_ref: str | None = None
    zhibo8_url: str | None = None
    zhibo8_text_url: str | None = None
    zhibo8_score_url: str | None = None
    zhibo8_animation_url: str | None = None
    zhibo8_raw_links: list[str] | None = None
    possible_qiumibao_ids: list[str] | None = None
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
    qiumibao_link_status: str = "qiumibao_unlinked"
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


@dataclass(frozen=True)
class LocalLiveCandidate:
    local_match_id: str | None
    live_home_team: str | None
    live_away_team: str | None
    live_kickoff_at: str | None
    live_status: str | None
    live_score: str | None
    live_half_score: str | None
    zhibo8_match_ref: str | None
    qiumibao_match_id: str | None
    qiumibao_left_id: str | None
    qiumibao_right_id: str | None
    possible_qiumibao_ids: list[str] | None
    qiumibao_link_status: str
    next_step: str | None
    normalized_live_home_team: str
    normalized_live_away_team: str
    home_team_match: bool
    away_team_match: bool
    time_delta_minutes: int | None
    match_score: float
    confidence: str
    mapping_status: str
    mapping_reason: str

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


def map_local_recent(limit: int = 12) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = _recent_local_matches(limit)
    return _mapping_report(live_report, locals_)


def map_local_upcoming(limit: int = 24) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = _upcoming_local_matches(limit)
    return _mapping_report(live_report, locals_)


def map_local_recent_finished(limit: int = 10) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = _recent_finished_locals(limit)
    return _mapping_report(live_report, locals_)


def map_local_all_overdue() -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    locals_ = [_local_match(str(row["match_id"])) for row in overdue_matches(limit=20)]
    report = _mapping_report(live_report, [local for local in locals_ if local])
    report["overdue_count"] = len(locals_)
    return report


def map_local_match(match_id: str) -> dict[str, Any]:
    live_report = fetch_worldcup_live_report()
    local = _local_match(match_id)
    return _mapping_report(live_report, [local] if local else [])


def score_live_to_local_match(live_match: dict[str, Any] | WorldCupLiveMatch, local_match: dict[str, Any]) -> LocalLiveCandidate:
    live = live_match.as_dict() if isinstance(live_match, WorldCupLiveMatch) else live_match
    local_home = normalize_team_name(local_match.get("home_team"))
    local_away = normalize_team_name(local_match.get("away_team"))
    live_home = normalize_team_name(live.get("home_team"))
    live_away = normalize_team_name(live.get("away_team"))
    home_match = bool(local_home and live_home and local_home == live_home)
    away_match = bool(local_away and live_away and local_away == live_away)
    delta = _time_delta_minutes(_as_datetime(local_match.get("kickoff_at")), _as_datetime(live.get("kickoff_at")))
    score = 0.0
    reasons: list[str] = []
    if home_match:
        score += 0.35
        reasons.append("home_team_normalized_match")
    if away_match:
        score += 0.35
        reasons.append("away_team_normalized_match")
    if delta is not None and delta <= 30:
        score += 0.20
        reasons.append("kickoff_within_30_minutes")
    elif delta is not None and delta <= 120:
        score += 0.10
        reasons.append("kickoff_within_120_minutes")
    if _match_num_or_external_ref(local_match, live):
        score += 0.20
        reasons.append("local_match_id_matches_live_external_ref")
    if _match_num_or_code(local_match, live):
        score += 0.10
        reasons.append("match_num_or_code_related")

    if home_match and away_match and delta is not None and delta <= 30:
        status = "matched"
    elif home_match and away_match:
        status = "kickoff_time_mismatch"
    elif delta is not None and delta <= 30:
        status = "team_name_mismatch"
    elif score >= 0.55:
        status = "low_confidence"
    else:
        status = "mapping_missing"
    return LocalLiveCandidate(
        local_match_id=local_match.get("match_id"),
        live_home_team=live.get("home_team"),
        live_away_team=live.get("away_team"),
        live_kickoff_at=live.get("kickoff_at"),
        live_status=live.get("status"),
        live_score=live.get("score"),
        live_half_score=live.get("half_score"),
        zhibo8_match_ref=live.get("zhibo8_match_ref"),
        qiumibao_match_id=live.get("qiumibao_match_id"),
        qiumibao_left_id=live.get("qiumibao_left_id"),
        qiumibao_right_id=live.get("qiumibao_right_id"),
        possible_qiumibao_ids=live.get("possible_qiumibao_ids"),
        qiumibao_link_status=_qiumibao_link_status(live),
        next_step=_next_step(live),
        normalized_live_home_team=live_home,
        normalized_live_away_team=live_away,
        home_team_match=home_match,
        away_team_match=away_match,
        time_delta_minutes=delta,
        match_score=round(min(score, 1.0), 3),
        confidence=_confidence(score, status),
        mapping_status=status,
        mapping_reason=", ".join(reasons) if reasons else "no strong team/time/id signal",
    )


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
        zhibo8_text_url=(schedule or {}).get("zhibo8_text_url"),
        zhibo8_score_url=(schedule or {}).get("zhibo8_score_url"),
        zhibo8_animation_url=(schedule or {}).get("zhibo8_animation_url"),
        zhibo8_raw_links=(schedule or {}).get("zhibo8_raw_links"),
        possible_qiumibao_ids=(schedule or {}).get("possible_qiumibao_ids"),
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
        qiumibao_link_status=_qiumibao_link_status(
            {
                "zhibo8_match_ref": (schedule or {}).get("zhibo8_match_ref"),
                "qiumibao_match_id": (qrow or {}).get("external_id"),
                "possible_qiumibao_ids": (schedule or {}).get("possible_qiumibao_ids"),
            }
        ),
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
    for candidate_id in schedule.get("possible_qiumibao_ids") or []:
        candidate_id = str(candidate_id)
        if candidate_id in by_external_id:
            return by_external_id[candidate_id], "matched", "zhibo8 link id matched qiumibao score id"
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


def _map_one_local(local: dict[str, Any], live_matches: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [score_live_to_local_match(live, local) for live in live_matches]
    candidates.sort(key=lambda item: item.match_score, reverse=True)
    local_summary = _local_mapping_summary(local)
    if not candidates:
        return _mapping_row(local_summary, None, [], "source_window_missing", "live source returned no rows")
    best = candidates[0]
    if len(candidates) > 1 and best.match_score >= 0.50 and abs(best.match_score - candidates[1].match_score) <= AMBIGUOUS_SCORE_DELTA:
        status = "ambiguous_candidates"
        reason = "multiple candidates have close scores"
        chosen = None
    elif best.mapping_status == "matched" and best.match_score >= 0.80:
        status = "matched"
        reason = best.mapping_reason
        chosen = best
    elif best.mapping_status in {"team_name_mismatch", "kickoff_time_mismatch", "low_confidence"}:
        status = best.mapping_status
        reason = best.mapping_reason
        chosen = best
    else:
        status = "mapping_missing"
        reason = "no live match matched local team/time/id signals"
        chosen = None
    comparison = _comparison_from_candidate(local, chosen, status)
    return _mapping_row(local_summary, chosen, candidates[:10], status, reason, comparison)


def _mapping_row(
    local_summary: dict[str, Any],
    best: LocalLiveCandidate | None,
    candidates: list[LocalLiveCandidate],
    status: str,
    reason: str,
    comparison_status: str | None = None,
) -> dict[str, Any]:
    return {
        "local_match": local_summary,
        "best_candidate": best.as_dict() if best else None,
        "candidates": [candidate.as_dict() for candidate in candidates],
        "mapping_status": status,
        "confidence": best.confidence if best else "none",
        "reason": reason,
        "comparison_status": comparison_status or ("AMBIGUOUS_CANDIDATES" if status == "ambiguous_candidates" else "MAPPING_MISSING"),
        "qiumibao_link_status": best.qiumibao_link_status if best else "qiumibao_unlinked",
        "next_step": best.next_step if best else None,
    }


def _comparison_from_candidate(local: dict[str, Any], candidate: LocalLiveCandidate | None, mapping_status: str) -> str:
    local_score = _score(local.get("result_home"), local.get("result_away"))
    if mapping_status == "ambiguous_candidates":
        return "AMBIGUOUS_CANDIDATES"
    if not candidate or mapping_status not in {"matched", "low_confidence"}:
        return "LOCAL_DB_ONLY" if local_score else "MAPPING_MISSING"
    live_score = candidate.live_score
    if local_score and live_score and local_score == live_score:
        return "OK_MATCH"
    if local_score and not live_score:
        return "LOCAL_DB_ONLY"
    if local_score and live_score and local_score != live_score:
        return "CONFLICT_NEEDS_REVIEW"
    if not local_score and candidate.live_status == "finished" and live_score:
        return "NEEDS_VERIFIED_FALLBACK"
    if candidate.live_status != "finished":
        return "WAIT_SOURCE"
    return "LIVE_SOURCE_ONLY"


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


def _mapping_report(live_report: dict[str, Any], locals_: list[dict[str, Any]]) -> dict[str, Any]:
    mappings = [_map_one_local(local, live_report["matches"]) for local in locals_]
    return {
        "mode": "dry-run",
        "writes_db": False,
        "source_fetch_ok": live_report["source_fetch_ok"],
        "zhibo8_matches_seen": live_report["zhibo8_matches_seen"],
        "qiumibao_matches_seen": live_report["qiumibao_matches_seen"],
        "merged_matches_count": live_report["merged_matches_count"],
        "mapping_status_summary": _status_counts(row["mapping_status"] for row in mappings),
        "comparison_status_summary": _status_counts(row["comparison_status"] for row in mappings),
        "conflicts_count": sum(1 for row in mappings if row["comparison_status"] == "CONFLICT_NEEDS_REVIEW"),
        "overdue_count": 0,
        "local_matches_seen": len(locals_),
        "mappings": mappings,
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


def _recent_local_matches(limit: int) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE kickoff_at >= now() - interval '48 hours'
              AND kickoff_at <= now() + interval '72 hours'
            ORDER BY kickoff_at
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _upcoming_local_matches(limit: int) -> list[dict[str, Any]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE status IN ('scheduled', 'closed')
              AND result_home IS NULL
              AND result_away IS NULL
            ORDER BY kickoff_at
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def _local_match(match_id: str) -> dict[str, Any] | None:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                   result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE match_id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _local_mapping_summary(local: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": local.get("match_id"),
        "match_num": local.get("match_num"),
        "league": local.get("league"),
        "raw_home_team": local.get("home_team"),
        "raw_away_team": local.get("away_team"),
        "normalized_home_team": normalize_team_name(local.get("home_team")),
        "normalized_away_team": normalize_team_name(local.get("away_team")),
        "kickoff_at": _iso(local.get("kickoff_at")),
        "status": local.get("status"),
        "result": _score(local.get("result_home"), local.get("result_away")),
    }


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


def _time_delta_minutes(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    return int(abs((left - right).total_seconds()) // 60)


def _match_num_or_external_ref(local: dict[str, Any], live: dict[str, Any]) -> bool:
    local_ref = _local_numeric_ref(local)
    if not local_ref:
        return False
    return local_ref in {str(live.get("zhibo8_match_ref") or ""), str(live.get("qiumibao_match_id") or "")}


def _match_num_or_code(local: dict[str, Any], live: dict[str, Any]) -> bool:
    match_num = str(local.get("match_num") or "").replace(" ", "")
    code = str(live.get("code") or live.get("qiumibao_code") or "").replace(" ", "")
    return bool(match_num and code and match_num == code)


def _local_numeric_ref(local: dict[str, Any]) -> str | None:
    match_id = str(local.get("match_id") or "")
    if match_id.startswith("500-"):
        return match_id.split("-", 1)[1]
    return None


def _confidence(score: float, status: str) -> str:
    if status == "matched" and score >= 0.90:
        return "high"
    if score >= 0.75:
        return "medium"
    if score >= 0.50:
        return "low"
    return "none"


def _qiumibao_link_status(live: dict[str, Any]) -> str:
    if live.get("qiumibao_match_id"):
        return "qiumibao_linked"
    if live.get("zhibo8_match_ref"):
        return "zhibo8_matched_but_qiumibao_unlinked"
    if live.get("possible_qiumibao_ids"):
        return "possible_qiumibao_ids_unresolved"
    return "qiumibao_unlinked"


def _next_step(live: dict[str, Any]) -> str | None:
    status = _qiumibao_link_status(live)
    if status == "zhibo8_matched_but_qiumibao_unlinked":
        return "EXTRACT_QIUMIBAO_ID_FROM_ZHIBO8_LINKS"
    if status == "possible_qiumibao_ids_unresolved":
        return "COMPARE_ZHIBO8_LINK_IDS_WITH_QIUMIBAO_SCORE_IDS"
    return None


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
