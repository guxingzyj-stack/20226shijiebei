from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import re
from typing import Any
import unicodedata

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import sanitize_error
from api.result_overdue_report import overdue_matches
from api.results_sync import fetch_results_html, parse_results_html
from api.sources import qiumibao


DATE_WINDOW_HOURS = 4
INVISIBLE_SPACE_RE = re.compile(r"[\s\u00a0\u1680\u180e\u2000-\u200f\u2028\u2029\u202f\u205f\u2060\u3000\ufeff]+")


def compare_match(match_id: str) -> dict[str, Any]:
    local = _local_match(match_id)
    if local is None:
        return _empty_report(match_id, "MAPPING_MISSING", "local_match_not_found")
    date = _date_for_match(local)
    sources = {
        "500_trade_jczq": _source_500(match_id),
        "qiumibao_score": _source_qiumibao_score(local, date),
        "fifa_match_centre": _source_fifa_placeholder(),
    }
    sources["qiumibao_events"] = _source_qiumibao_events(local, date, sources["qiumibao_score"])
    comparison = _compare(local, sources)
    return {
        "mode": "dry-run",
        "writes_db": False,
        "match_id": match_id,
        "home_team": local.get("home_team"),
        "away_team": local.get("away_team"),
        "kickoff_at": _iso(local.get("kickoff_at")),
        "local_db": _local_summary(local),
        "sources": sources,
        "comparison": comparison,
    }


def compare_all_overdue() -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "writes_db": False,
        "matches": [compare_match(str(row["match_id"])) for row in overdue_matches(limit=20)],
    }


def compare_recent_finished(limit: int = 10) -> dict[str, Any]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
            ORDER BY kickoff_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    return {
        "mode": "dry-run",
        "writes_db": False,
        "matches": [compare_match(str(row["match_id"])) for row in rows],
    }


def print_report(report: dict[str, Any]) -> None:
    print("Result Source Compare Report")
    print("")
    print(f"mode: {report.get('mode')}")
    print(f"writes_db: {report.get('writes_db')}")
    if "matches" in report:
        print(f"matches_count: {len(report.get('matches') or [])}")
        for item in report.get("matches") or []:
            _print_one(item)
    else:
        _print_one(report)


def _print_one(report: dict[str, Any]) -> None:
    print("")
    print(f"match_id: {report.get('match_id')}")
    print(f"home_team: {report.get('home_team')}")
    print(f"away_team: {report.get('away_team')}")
    print(f"kickoff_at: {report.get('kickoff_at')}")
    print("")
    print("local_db:")
    for key, value in (report.get("local_db") or {}).items():
        print(f"  {key}: {value}")
    print("")
    print("sources:")
    for name, source in (report.get("sources") or {}).items():
        print(f"  {name}:")
        for key, value in source.items():
            if key == "events":
                print(f"    events_count: {len(value or [])}")
            else:
                print(f"    {key}: {value}")
    print("")
    print("comparison:")
    for key, value in (report.get("comparison") or {}).items():
        print(f"  {key}: {value}")


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


def _source_500(match_id: str) -> dict[str, Any]:
    try:
        parsed = parse_results_html(fetch_results_html())
        found = next((item for item in parsed if item.match_id == match_id), None)
        if found is None:
            return _source_missing("source_not_found")
        return {
            "seen": True,
            "status": found.status,
            "score": _score(found.result_home, found.result_away),
            "ht_score": _score(found.ht_home, found.ht_away),
            "confidence": "low" if found.status != "finished" or found.result_home is None else "medium",
            "mapping_status": "mapped",
            "parser_error": None,
        }
    except Exception as exc:
        return _source_error(exc)


def _source_qiumibao_score(local: dict[str, Any], date: str | None) -> dict[str, Any]:
    report = qiumibao.score_source_report(date=date)
    if not report["source_fetch_ok"]:
        return {
            "seen": False,
            "status": "parser_error",
            "score": None,
            "ht_score": None,
            "confidence": "unknown",
            "mapping_status": "unknown",
            "parser_error": report["parser_error"],
        }
    match = _map_source_match(local, report["matches"])
    if match is None:
        return _source_missing("mapping_missing")
    return {
        "seen": True,
        "status": match["status"],
        "score": _score(match.get("result_home"), match.get("result_away")),
        "ht_score": _score(match.get("ht_home"), match.get("ht_away")),
        "confidence": "medium_high" if match["status"] == "finished" and match.get("result_home") is not None else "medium",
        "external_id": match.get("external_id"),
        "mapping_status": "mapped" if match.get("external_id") else "mapped_without_external_id",
        "parser_error": None,
    }


def _source_qiumibao_events(local: dict[str, Any], date: str | None, qiumibao_score_source: dict[str, Any] | None = None) -> dict[str, Any]:
    external_id = str((qiumibao_score_source or {}).get("external_id") or "").strip()
    if not date or not external_id:
        return {
            "seen": False,
            "status": "mapping_missing",
            "minute": None,
            "score_from_events": None,
            "confidence": "unknown",
            "mapping_status": "missing",
            "events": [],
        }
    report = qiumibao.events_source_report(date, external_id)
    if not report["source_fetch_ok"]:
        return {
            "seen": False,
            "status": "parser_error",
            "minute": None,
            "score_from_events": None,
            "confidence": "unknown",
            "mapping_status": "mapped",
            "external_id": external_id,
            "events": [],
            "parser_error": report["parser_error"],
        }
    goals = [event for event in report["events"] if "球" in str(event.get("event_type") or "")]
    return {
        "seen": bool(report["events"]),
        "status": "unknown",
        "minute": "FT" if _is_finished(local) else None,
        "score_from_events": None,
        "confidence": "medium" if report["events"] else "unknown",
        "mapping_status": "mapped",
        "external_id": external_id,
        "events": report["events"],
        "goals_count": len(goals),
    }


def _source_fifa_placeholder() -> dict[str, Any]:
    return {
        "seen": False,
        "mapping_status": "missing",
        "score": None,
        "confidence": "unknown",
        "suggested_next_step": "build_mapping",
    }


def _compare(local: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    local_score = _score(local.get("result_home"), local.get("result_away"))
    source_scores_by_name = _external_score_sources(sources)
    source_scores = list(source_scores_by_name.values())
    external_confirming_sources = [
        name for name, score in source_scores_by_name.items() if local_score and score == local_score
    ]
    external_confirmed = bool(external_confirming_sources)
    conflicts = []
    if local_score:
        for name, score in source_scores_by_name.items():
            if score != local_score:
                conflicts.append(f"local_db={local_score} {name}={score}")
    if len(set(source_scores)) > 1:
        conflicts.append(f"source_scores={sorted(set(source_scores))}")
    consensus_score = local_score or (source_scores[0] if len(set(source_scores)) == 1 and source_scores else None)
    consensus_status = "finished" if consensus_score else None
    suggested = "WAIT_SOURCE"
    q_score = sources.get("qiumibao_score", {})
    if conflicts:
        suggested = "CONFLICT_NEEDS_REVIEW"
    elif local_score and external_confirmed:
        suggested = "OK_MATCH"
    elif local_score and not source_scores:
        suggested = "LOCAL_DB_ONLY"
    elif _missing_local_result(local) and q_score.get("status") == "finished" and q_score.get("score"):
        suggested = "NEEDS_VERIFIED_FALLBACK"
    elif q_score.get("status") == "mapping_missing" or q_score.get("status") == "source_not_found":
        suggested = "MAPPING_MISSING"
    mapping_status = {
        "qiumibao_score": _source_mapping_status(sources.get("qiumibao_score")),
        "qiumibao_events": _source_mapping_status(sources.get("qiumibao_events")),
        "fifa_match_centre": _source_mapping_status(sources.get("fifa_match_centre")),
    }
    return {
        "consensus_score": consensus_score,
        "consensus_status": consensus_status,
        "external_confirmed": external_confirmed,
        "external_confirming_sources": external_confirming_sources,
        "mapping_status": mapping_status,
        "conflicts": conflicts,
        "suggested_action": suggested,
        "next_step": _next_step(suggested, mapping_status),
    }


def _external_score_sources(sources: dict[str, dict[str, Any]]) -> dict[str, str]:
    scores: dict[str, str] = {}
    for name in ("qiumibao_score", "500_trade_jczq", "fifa_match_centre"):
        source = sources.get(name) or {}
        score = source.get("score")
        if source.get("seen") is True and score:
            scores[name] = str(score)
    return scores


def _source_mapping_status(source: dict[str, Any] | None) -> str:
    if not source:
        return "missing"
    explicit = source.get("mapping_status")
    if explicit:
        return str(explicit)
    status = source.get("status")
    if status in {"mapping_missing", "source_not_found"}:
        return "missing"
    if source.get("seen") is True:
        return "mapped"
    if status == "parser_error":
        return "unknown"
    return "missing"


def _next_step(suggested_action: str, mapping_status: dict[str, str]) -> str:
    if suggested_action == "OK_MATCH":
        return "NONE"
    if suggested_action == "CONFLICT_NEEDS_REVIEW":
        return "HUMAN_REVIEW"
    if suggested_action == "NEEDS_VERIFIED_FALLBACK":
        return "PREPARE_VERIFIED_FALLBACK"
    if "missing" in {mapping_status.get("qiumibao_score"), mapping_status.get("fifa_match_centre")}:
        return "BUILD_QIUMIBAO_OR_FIFA_MAPPING"
    if suggested_action == "LOCAL_DB_ONLY":
        return "WAIT_EXTERNAL_CONFIRMATION"
    return "WAIT_SOURCE"


def _map_source_match(local: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    local_id = str(local.get("match_id") or "")
    numeric_id = local_id.replace("500-", "")
    for row in rows:
        if str(row.get("external_id") or "") in {local_id, numeric_id}:
            return row
    local_home = _clean_team(local.get("home_team"))
    local_away = _clean_team(local.get("away_team"))
    kickoff = _as_datetime(local.get("kickoff_at"))
    for row in rows:
        if _clean_team(row.get("home_team")) != local_home or _clean_team(row.get("away_team")) != local_away:
            continue
        row_time = _as_datetime(row.get("kickoff_at"))
        if kickoff is None or row_time is None:
            return row
        if abs((kickoff - row_time).total_seconds()) <= DATE_WINDOW_HOURS * 3600:
            return row
    return None


def _empty_report(match_id: str, action: str, reason: str) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "writes_db": False,
        "match_id": match_id,
        "local_db": None,
        "sources": {},
        "comparison": {"consensus_score": None, "consensus_status": None, "conflicts": [reason], "suggested_action": action},
    }


def _source_missing(status: str) -> dict[str, Any]:
    return {
        "seen": False,
        "status": status,
        "score": None,
        "ht_score": None,
        "confidence": "unknown",
        "mapping_status": "missing" if status in {"mapping_missing", "source_not_found"} else "unknown",
        "parser_error": None,
    }


def _source_error(exc: Exception) -> dict[str, Any]:
    return {
        "seen": False,
        "status": "parser_error",
        "score": None,
        "ht_score": None,
        "confidence": "unknown",
        "mapping_status": "unknown",
        "parser_error": sanitize_error(exc),
    }


def _local_summary(local: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": local.get("status"),
        "score": _score(local.get("result_home"), local.get("result_away")),
        "ht_score": _score(local.get("ht_home"), local.get("ht_away")),
    }


def _score(home: Any, away: Any) -> str | None:
    if home is None or away is None:
        return None
    return f"{home}-{away}"


def _date_for_match(local: dict[str, Any]) -> str | None:
    dt = _as_datetime(local.get("kickoff_at"))
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


def _clean_team(value: Any) -> str:
    return normalize_team_name(value)


def normalize_team_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return INVISIBLE_SPACE_RE.sub("", text).strip().lower()


def _missing_local_result(local: dict[str, Any]) -> bool:
    return local.get("result_home") is None or local.get("result_away") is None


def _is_finished(local: dict[str, Any]) -> bool:
    return str(local.get("status") or "").lower() in {"finished", "completed"}


def _iso(value: Any) -> str | None:
    dt = _as_datetime(value)
    return dt.isoformat() if dt else (str(value) if value is not None else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dry-run multi-source result comparison")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--match-id")
    group.add_argument("--all-overdue", action="store_true")
    group.add_argument("--recent-finished", action="store_true")
    args = parser.parse_args(argv)
    if args.match_id:
        report = compare_match(args.match_id)
    elif args.all_overdue:
        report = compare_all_overdue()
    else:
        report = compare_recent_finished()
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
