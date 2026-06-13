from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
from urllib.request import Request, urlopen

from api.ops_log import sanitize_error


SCORE_BASE = "https://bifen4pc.qiumibao.com/json"
EVENT_BASE = "https://dc4pc.qiumibao.com/dc/matchs/data"
USER_AGENT = "Mozilla/5.0"
CLASSIFICATION_FIELD_CANDIDATES = (
    "sport_type",
    "sport",
    "category",
    "league",
    "competition",
    "match_type",
    "type",
    "ball_type",
    "tournament",
    "name",
    "cn",
    "title",
)
FOOTBALL_TERMS = ("football", "soccer", "足球", "zuqiu", "world cup", "世界杯")
NON_FOOTBALL_TERMS = ("basketball", "篮球", "nba", "tennis", "网球", "volleyball", "排球")
NON_FOOTBALL_PERIOD_TERMS = ("节", "局", "盘")


@dataclass(frozen=True)
class SourceMatch:
    source_name: str
    external_id: str | None
    home_team: str | None
    away_team: str | None
    kickoff_at: str | None
    start_time_raw: str | None
    start_time_utc: str | None
    status: str
    result_home: int | None = None
    result_away: int | None = None
    ht_home: int | None = None
    ht_away: int | None = None
    raw_status: str | None = None
    code: str | None = None
    left_id: str | None = None
    right_id: str | None = None
    period_cn: str | None = None
    score_msg_full: str | None = None
    score_msg_list: list[str] | None = None
    sport_filter_status: str = "unknown_sport"
    sport_filter_reason: str | None = None
    classification_fields: dict[str, Any] | None = None
    raw_keys: list[str] | None = None


@dataclass(frozen=True)
class SourceEvent:
    minute: str | int | None
    event_type: str | None
    team: str | None
    player: str | None
    score_after_event: str | None = None


def fetch_score_json(date: str | None = None, timeout: int = 15) -> dict[str, Any]:
    return _fetch_json(score_url(date), timeout=timeout)


def score_url(date: str | None = None) -> str:
    suffix = f"/{date}/v2/list.htm" if date else "/v2/list.htm"
    return f"{SCORE_BASE}{suffix}"


def fetch_event_json(date: str, match_id: str, timeout: int = 15) -> dict[str, Any]:
    return _fetch_json(f"{EVENT_BASE}/{date}/match_event_{match_id}.htm", timeout=timeout)


def score_source_report(date: str | None = None, fetcher=fetch_score_json) -> dict[str, Any]:
    try:
        payload = fetcher(date)
        matches = normalize_score_payload(payload)
        return {
            "source_name": "qiumibao_score",
            "source_fetch_ok": True,
            "parser_error": None,
            "matches": [match.__dict__ for match in matches],
        }
    except Exception as exc:
        return {
            "source_name": "qiumibao_score",
            "source_fetch_ok": False,
            "parser_error": sanitize_error(exc),
            "matches": [],
        }


def raw_score_source_report(date: str | None = None, fetcher=fetch_score_json) -> dict[str, Any]:
    try:
        payload = fetcher(date)
        rows = _extract_rows(payload) or []
        raw_rows = [row for row in rows if isinstance(row, dict)]
        return {
            "source_name": "qiumibao_score_raw",
            "source_fetch_ok": True,
            "parser_error": None,
            "source_url": score_url(date),
            "date": date,
            "rows_seen": len(raw_rows),
            "raw_rows": raw_rows,
            "classification_field_candidates": inspect_classification_fields(raw_rows),
        }
    except Exception as exc:
        return {
            "source_name": "qiumibao_score_raw",
            "source_fetch_ok": False,
            "parser_error": sanitize_error(exc),
            "source_url": score_url(date),
            "date": date,
            "rows_seen": 0,
            "raw_rows": [],
            "classification_field_candidates": inspect_classification_fields([]),
        }


def events_source_report(date: str, match_id: str, fetcher=fetch_event_json) -> dict[str, Any]:
    try:
        payload = fetcher(date, match_id)
        events = normalize_event_payload(payload)
        return {
            "source_name": "qiumibao_events",
            "source_fetch_ok": True,
            "parser_error": None,
            "events": [event.__dict__ for event in events],
        }
    except Exception as exc:
        return {
            "source_name": "qiumibao_events",
            "source_fetch_ok": False,
            "parser_error": sanitize_error(exc),
            "events": [],
        }


def score_from_events(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        score = str(event.get("score_after_event") or "").strip()
        if score and "-" in score:
            return score
    return None


def normalize_score_payload(payload: dict[str, Any]) -> list[SourceMatch]:
    rows = _extract_rows(payload)
    if rows is None:
        raise ValueError("parser_error: missing list rows")
    matches: list[SourceMatch] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = normalize_match(row)
        if match is not None:
            matches.append(match)
    return matches


def normalize_match(row: dict[str, Any]) -> SourceMatch | None:
    external_id = _first(row, "id", "match_id", "saishi_id")
    left = row.get("left") if isinstance(row.get("left"), dict) else {}
    right = row.get("right") if isinstance(row.get("right"), dict) else {}
    period_cn = _first(row, "period_cn", "period", "status_cn")
    score_msg_list = _score_messages(row)
    score_msg_full = " ".join(score_msg_list) if score_msg_list else None
    home_team = _first_path(
        row,
        "home_team",
        "home",
        "h",
        "homeName",
        "home_name",
        "home_team_name",
        "hteam",
        "hn",
        "team1",
        "left_name",
        "left.name",
        "left.team_name",
        "left.name_cn",
        "home.name",
        "teams.home.name",
    ) or _first(left, "name", "team_name", "name_cn", "short_name")
    away_team = _first_path(
        row,
        "away_team",
        "away",
        "a",
        "awayName",
        "away_name",
        "away_team_name",
        "ateam",
        "an",
        "team2",
        "right_name",
        "right.name",
        "right.team_name",
        "right.name_cn",
        "away.name",
        "teams.away.name",
    ) or _first(right, "name", "team_name", "name_cn", "short_name")
    home_team = _team_value(home_team)
    away_team = _team_value(away_team)
    status = normalize_status(_first(row, "state", "status", "status_cn", "period_cn") or "")
    home_score = _parse_int(_first(row, "home_score", "score1", "left_score") or _first(left, "score"))
    away_score = _parse_int(_first(row, "away_score", "score2", "right_score") or _first(right, "score"))
    half_score = _parse_half_score(score_msg_full or "")
    ht_home = _parse_int(_first(row, "ht_home", "half_home", "half_score1"))
    ht_away = _parse_int(_first(row, "ht_away", "half_away", "half_score2"))
    if half_score and ht_home is None and ht_away is None:
        ht_home, ht_away = half_score
    if status not in {"live", "finished"}:
        home_score = None
        away_score = None
    if not external_id and not home_team and not away_team:
        return None
    sport_filter = qiumibao_sport_filter(row, normalized_home_score=home_score, normalized_away_score=away_score)
    kickoff_value = _first(row, "time", "match_time", "start_time", "date")
    kickoff_at = _normalize_kickoff(kickoff_value)
    start_time_value = _first(row, "start_time", "time", "match_time")
    return SourceMatch(
        source_name="qiumibao_score",
        external_id=str(external_id) if external_id is not None else None,
        home_team=str(home_team).strip() if home_team else None,
        away_team=str(away_team).strip() if away_team else None,
        kickoff_at=kickoff_at,
        start_time_raw=str(start_time_value) if start_time_value is not None else None,
        start_time_utc=kickoff_at,
        status=status,
        result_home=home_score,
        result_away=away_score,
        ht_home=ht_home,
        ht_away=ht_away,
        raw_status=str(_first(row, "state", "status", "status_cn", "period_cn") or ""),
        code=str(_first(row, "code", "league_code") or "") or None,
        left_id=str(_first(left, "id", "team_id", "tid") or "") or None,
        right_id=str(_first(right, "id", "team_id", "tid") or "") or None,
        period_cn=str(period_cn) if period_cn else None,
        score_msg_full=score_msg_full,
        score_msg_list=score_msg_list or None,
        sport_filter_status=sport_filter["sport_filter_status"],
        sport_filter_reason=sport_filter["reason"],
        classification_fields=sport_filter["classification_fields"],
        raw_keys=sorted(str(key) for key in row.keys()),
    )


def is_qiumibao_football_row(row: dict[str, Any]) -> bool:
    return qiumibao_sport_filter(row)["sport_filter_status"] in {"classified_football", "football_like"}


def qiumibao_sport_filter(
    row: dict[str, Any],
    normalized_home_score: int | None = None,
    normalized_away_score: int | None = None,
) -> dict[str, Any]:
    classification = _classification_values(row)
    text_values = [str(value).strip().lower() for value in classification.values() if value is not None and str(value).strip()]
    if any(_contains_any(value, FOOTBALL_TERMS) for value in text_values):
        return _sport_filter_result("classified_football", "classification field says football", classification, row)
    if any(_contains_any(value, NON_FOOTBALL_TERMS) for value in text_values):
        return _sport_filter_result("classified_non_football", "classification field says non-football", classification, row)
    if text_values:
        return _sport_filter_result("unknown_sport", "classification fields exist but sport is unclear", classification, row)

    period = str(_first(row, "period_cn", "period", "status_cn", "state") or "")
    if any(term in period for term in NON_FOOTBALL_PERIOD_TERMS):
        return _sport_filter_result("non_football_like", "period looks like another sport", classification, row)

    home_score = normalized_home_score
    away_score = normalized_away_score
    if home_score is None:
        left = row.get("left") if isinstance(row.get("left"), dict) else {}
        home_score = _parse_int(_first(row, "home_score", "score1", "left_score") or _first(left, "score"))
    if away_score is None:
        right = row.get("right") if isinstance(row.get("right"), dict) else {}
        away_score = _parse_int(_first(row, "away_score", "score2", "right_score") or _first(right, "score"))
    if home_score is not None and away_score is not None and (home_score > 9 or away_score > 9):
        return _sport_filter_result("non_football_like", "score is too high for football", classification, row)
    return _sport_filter_result("football_like", "structure is compatible with football", classification, row)


def inspect_classification_fields(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for field in CLASSIFICATION_FIELD_CANDIDATES:
        values: list[str] = []
        for row in rows:
            for value in _field_values(row, field):
                text = _short_text(value)
                if text and text not in values:
                    values.append(text)
                if len(values) >= 5:
                    break
            if len(values) >= 5:
                break
        report[field] = {
            "status": "found" if values else "not_found",
            "count": sum(1 for row in rows if _field_values(row, field)),
            "sample_values": values,
        }
    return report


def normalize_status(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"3", "finished", "完赛", "完场", "已结束"}:
        return "finished"
    if text in {"2", "live", "进行中", "中场"}:
        return "live"
    if text in {"4", "postponed", "延期", "推迟", "取消"}:
        return "postponed"
    if text in {"1", "scheduled", "未赛", "未开赛"}:
        return "scheduled"
    if text in {"closed", "停售"}:
        return "closed"
    return "unknown"

def normalize_event_payload(payload: dict[str, Any]) -> list[SourceEvent]:
    rows = payload.get("data")
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("events") or rows.get("data")
    if not isinstance(rows, list):
        raise ValueError("parser_error: missing event rows")
    events: list[SourceEvent] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("is_hide"):
            continue
        event_type = _first(row, "event_code_cn", "type", "event_type")
        player = _first(row, "player_name_cn", "player", "player_name")
        if not event_type and not player:
            continue
        events.append(
            SourceEvent(
                minute=_first(row, "time", "minute"),
                event_type=str(event_type) if event_type else None,
                team=str(_first(row, "team", "team_name", "sl_team_name") or "") or None,
                player=str(player) if player else None,
                score_after_event=str(_first(row, "score", "score_after_event") or "") or None,
            )
        )
    return events


def _fetch_json(url: str, timeout: int) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.zhibo8.cc/"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8"))


def _extract_rows(payload: dict[str, Any]) -> list[Any] | None:
    if isinstance(payload.get("list"), list):
        return payload["list"]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("list", "matches", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    if isinstance(data, list):
        return data
    if isinstance(payload.get("matches"), list):
        return payload["matches"]
    return None


def _first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return None


def _classification_values(row: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in CLASSIFICATION_FIELD_CANDIDATES:
        found = _field_values(row, field)
        if found:
            values[field] = found[0] if len(found) == 1 else found
    return values


def _field_values(row: dict[str, Any], field: str) -> list[Any]:
    values: list[Any] = []
    direct = row.get(field)
    if direct is not None and direct != "":
        values.append(direct)
    for side in ("left", "right"):
        child = row.get(side)
        if isinstance(child, dict):
            value = child.get(field)
            if value is not None and value != "":
                values.append(value)
    return values


def _sport_filter_result(status: str, reason: str, classification: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sport_filter_status": status,
        "reason": reason,
        "classification_fields": classification,
        "raw_keys": sorted(str(key) for key in row.keys()),
    }


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _short_text(value: Any, limit: int = 80) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _first_path(row: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = _path(row, path)
        if value is not None and value != "":
            return value
    return None


def _path(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _normalize_kickoff(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            number = number // 1000
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    return text


def _team_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _first(value, "name", "team_name", "name_cn", "short_name")
    return value


def _score_messages(row: dict[str, Any]) -> list[str]:
    value = row.get("score_msg")
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    values: list[str] = []
    for name in ("score_msg_1", "score_msg_2", "score_msg_3", "score_msg_4"):
        item = row.get(name)
        if item is not None and str(item).strip():
            values.append(str(item).strip())
    return values


def _parse_half_score(value: str) -> tuple[int, int] | None:
    import re

    text = str(value or "")
    found = re.search(r"(?:半场|半|HT|ht)[^\d]*(\d+)\s*[-:：]\s*(\d+)", text)
    if not found:
        return None
    return int(found.group(1)), int(found.group(2))


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
