from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
import unicodedata


DATE_WINDOW_HOURS = 4
INVISIBLE_SPACE_RE = re.compile(r"[\s\u00a0\u1680\u180e\u2000-\u200f\u2028\u2029\u202f\u205f\u2060\u3000\ufeff]+")

MATCHED = "matched"
SOURCE_FETCH_ERROR = "source_fetch_error"
SOURCE_EMPTY = "source_empty"
SOURCE_AVAILABLE_BUT_MATCH_NOT_IN_WINDOW = "source_available_but_match_not_in_window"
PARSER_MISSING_TEAM_FIELDS = "parser_missing_team_fields"
TEAM_NAME_MISMATCH = "team_name_mismatch"
KICKOFF_TIME_MISMATCH = "kickoff_time_mismatch"
AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
MAPPING_MISSING = "mapping_missing"
FIFA_MAPPING_MISSING = "fifa_mapping_missing"


TEAM_ALIASES_RAW = {
    "加拿大": "加拿大",
    "canada": "加拿大",
    "波黑": "波黑",
    "bosnia": "波黑",
    "bosniaherzegovina": "波黑",
    "bosniaandherzegovina": "波黑",
    "bih": "波黑",
    "墨西哥": "墨西哥",
    "mexico": "墨西哥",
    "南非": "南非",
    "southafrica": "南非",
    "韩国": "韩国",
    "korea": "韩国",
    "korearepublic": "韩国",
    "southkorea": "韩国",
    "republicofkorea": "韩国",
    "捷克": "捷克",
    "czechia": "捷克",
    "czechrepublic": "捷克",
    "美国": "美国",
    "usa": "美国",
    "us": "美国",
    "unitedstates": "美国",
    "unitedstatesofamerica": "美国",
    "巴拉圭": "巴拉圭",
    "paraguay": "巴拉圭",
    "沙特阿拉伯": "沙特阿拉伯",
    "沙特": "沙特阿拉伯",
    "saudiarabia": "沙特阿拉伯",
    "科特迪瓦": "科特迪瓦",
    "ivorycoast": "科特迪瓦",
    "cotedivoire": "科特迪瓦",
    "刚果金": "刚果(金)",
    "刚果(金)": "刚果(金)",
    "drcongo": "刚果(金)",
    "congodr": "刚果(金)",
    "democraticrepublicofcongo": "刚果(金)",
}

TEAM_ALIASES_RAW.update(
    {
        "\u7f8e\u56fd": "\u7f8e\u56fd",
        "\u5df4\u62c9\u572d": "\u5df4\u62c9\u572d",
        "\u52a0\u62ff\u5927": "\u52a0\u62ff\u5927",
        "\u6ce2\u9ed1": "\u6ce2\u9ed1",
        "\u97e9\u56fd": "\u97e9\u56fd",
        "\u6377\u514b": "\u6377\u514b",
        "\u58a8\u897f\u54e5": "\u58a8\u897f\u54e5",
        "\u5357\u975e": "\u5357\u975e",
        "\u5361\u5854\u5c14": "\u5361\u5854\u5c14",
        "\u745e\u58eb": "\u745e\u58eb",
        "\u5df4\u897f": "\u5df4\u897f",
        "\u6469\u6d1b\u54e5": "\u6469\u6d1b\u54e5",
        "\u6d77\u5730": "\u6d77\u5730",
        "\u82cf\u683c\u5170": "\u82cf\u683c\u5170",
        "\u6fb3\u5927\u5229\u4e9a": "\u6fb3\u5927\u5229\u4e9a",
        "\u571f\u8033\u5176": "\u571f\u8033\u5176",
        "\u5fb7\u56fd": "\u5fb7\u56fd",
        "\u5e93\u62c9\u7d22": "\u5e93\u62c9\u7d22",
        "\u521a\u679c\uff08\u91d1\uff09": "\u521a\u679c(\u91d1)",
        "\u521a\u679c(\u91d1)": "\u521a\u679c(\u91d1)",
        "brazil": "\u5df4\u897f",
        "morocco": "\u6469\u6d1b\u54e5",
        "germany": "\u5fb7\u56fd",
        "scotland": "\u82cf\u683c\u5170",
        "turkey": "\u571f\u8033\u5176",
        "australia": "\u6fb3\u5927\u5229\u4e9a",
        "qatar": "\u5361\u5854\u5c14",
        "switzerland": "\u745e\u58eb",
        "haiti": "\u6d77\u5730",
        "curacao": "\u5e93\u62c9\u7d22",
    }
)


def _team_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = INVISIBLE_SPACE_RE.sub("", text)
    text = "".join(text.split()).lower()
    text = text.replace("（", "(").replace("）", ")")
    return text


TEAM_ALIASES = {_team_key(key): value for key, value in TEAM_ALIASES_RAW.items()}


@dataclass(frozen=True)
class MappingCandidate:
    external_id: str | None
    raw_home_team: str | None
    raw_away_team: str | None
    normalized_home_team: str
    normalized_away_team: str
    kickoff_at: str | None
    status: str | None
    score: str | None
    match_score: float
    mapping_status: str
    time_delta_minutes: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def normalize_team_name(value: Any) -> str:
    compact = _team_key(value)
    return TEAM_ALIASES.get(compact, compact)


def analyze_external_mapping(local: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    local_summary = local_match_summary(local)
    if not rows:
        return {
            "mapping_status": SOURCE_EMPTY,
            "reason": "source returned no matches",
            "external_id": None,
            "confidence": "none",
            "candidate_count": 0,
            "local_match": local_summary,
            "candidates": [],
        }
    if _all_rows_missing_team_fields(rows):
        return {
            "mapping_status": PARSER_MISSING_TEAM_FIELDS,
            "reason": "external rows were parsed, but no home/away team fields were found",
            "external_id": None,
            "confidence": "none",
            "candidate_count": len(rows),
            "local_match": local_summary,
            "candidates": [_candidate(local, row).as_dict() for row in rows[:10]],
        }

    candidates = [_candidate(local, row) for row in rows]
    candidates.sort(key=lambda item: item.match_score, reverse=True)
    matched = [candidate for candidate in candidates if candidate.mapping_status == MATCHED]
    if len(matched) == 1:
        best = matched[0]
        return {
            "mapping_status": MATCHED,
            "reason": "team names and kickoff window matched",
            "external_id": best.external_id,
            "confidence": "high" if best.match_score >= 0.95 else "medium",
            "candidate_count": len(candidates),
            "local_match": local_summary,
            "candidates": [candidate.as_dict() for candidate in candidates[:10]],
        }
    if len(matched) > 1:
        return _unmatched_result(AMBIGUOUS_CANDIDATES, "multiple safe candidates matched", local_summary, candidates)
    if any(candidate.mapping_status == KICKOFF_TIME_MISMATCH for candidate in candidates):
        return _unmatched_result(KICKOFF_TIME_MISMATCH, "team names matched but kickoff window did not", local_summary, candidates)
    if any(candidate.mapping_status == TEAM_NAME_MISMATCH for candidate in candidates):
        return _unmatched_result(TEAM_NAME_MISMATCH, "kickoff window matched but team names did not", local_summary, candidates)
    return _unmatched_result(
        SOURCE_AVAILABLE_BUT_MATCH_NOT_IN_WINDOW,
        "source was available but target match was not in returned window",
        local_summary,
        candidates,
    )


def local_match_summary(local: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": local.get("match_id"),
        "raw_home_team": local.get("home_team"),
        "raw_away_team": local.get("away_team"),
        "normalized_home_team": normalize_team_name(local.get("home_team")),
        "normalized_away_team": normalize_team_name(local.get("away_team")),
        "kickoff_at": _iso(local.get("kickoff_at")),
    }


def fifa_mapping_placeholder(local: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "mapping_status": FIFA_MAPPING_MISSING,
        "reason": "FIFA Match Centre needs a stable local match_id to FIFA match id/url mapping",
        "external_id": None,
        "confidence": "none",
        "candidate_count": 0,
        "local_match": local_match_summary(local) if local else None,
        "candidates": [],
        "suggested_next_step": "build_fifa_match_id_mapping",
    }


def _candidate(local: dict[str, Any], row: dict[str, Any]) -> MappingCandidate:
    local_home = normalize_team_name(local.get("home_team"))
    local_away = normalize_team_name(local.get("away_team"))
    external_home = normalize_team_name(row.get("home_team"))
    external_away = normalize_team_name(row.get("away_team"))
    teams_match = local_home == external_home and local_away == external_away
    local_time = _as_datetime(local.get("kickoff_at"))
    external_time = _as_datetime(row.get("kickoff_at"))
    delta_minutes = _time_delta_minutes(local_time, external_time)
    time_match = delta_minutes is not None and delta_minutes <= DATE_WINDOW_HOURS * 60
    if teams_match and time_match:
        status = MATCHED
        score = 1.0
    elif teams_match:
        status = KICKOFF_TIME_MISMATCH
        score = 0.72
    elif time_match:
        status = TEAM_NAME_MISMATCH
        score = 0.55
    else:
        status = SOURCE_AVAILABLE_BUT_MATCH_NOT_IN_WINDOW
        score = 0.15
    if delta_minutes is not None:
        score -= min(delta_minutes / (DATE_WINDOW_HOURS * 60), 1.0) * 0.02
    return MappingCandidate(
        external_id=str(row.get("external_id")) if row.get("external_id") is not None else None,
        raw_home_team=row.get("home_team"),
        raw_away_team=row.get("away_team"),
        normalized_home_team=external_home,
        normalized_away_team=external_away,
        kickoff_at=_iso(row.get("kickoff_at")),
        status=row.get("status"),
        score=_score(row.get("result_home"), row.get("result_away")),
        match_score=round(max(score, 0), 3),
        mapping_status=status,
        time_delta_minutes=delta_minutes,
    )


def _all_rows_missing_team_fields(rows: list[dict[str, Any]]) -> bool:
    return all(not row.get("home_team") and not row.get("away_team") for row in rows)


def _unmatched_result(status: str, reason: str, local_summary: dict[str, Any], candidates: list[MappingCandidate]) -> dict[str, Any]:
    return {
        "mapping_status": status,
        "reason": reason,
        "external_id": None,
        "confidence": "none",
        "candidate_count": len(candidates),
        "local_match": local_summary,
        "candidates": [candidate.as_dict() for candidate in candidates[:10]],
    }


def _score(home: Any, away: Any) -> str | None:
    if home is None or away is None:
        return None
    return f"{home}-{away}"


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


def _time_delta_minutes(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    return int(abs((left - right).total_seconds()) // 60)
