from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.request import Request, urlopen

from api.ops_log import sanitize_error


SCORE_BASE = "https://bifen4pc.qiumibao.com/json"
EVENT_BASE = "https://dc4pc.qiumibao.com/dc/matchs/data"
USER_AGENT = "Mozilla/5.0"


@dataclass(frozen=True)
class SourceMatch:
    source_name: str
    external_id: str | None
    home_team: str | None
    away_team: str | None
    kickoff_at: str | None
    status: str
    result_home: int | None = None
    result_away: int | None = None
    ht_home: int | None = None
    ht_away: int | None = None
    raw_status: str | None = None


@dataclass(frozen=True)
class SourceEvent:
    minute: str | int | None
    event_type: str | None
    team: str | None
    player: str | None
    score_after_event: str | None = None


def fetch_score_json(date: str | None = None, timeout: int = 15) -> dict[str, Any]:
    suffix = f"/{date}/v2/list.htm" if date else "/v2/list.htm"
    return _fetch_json(f"{SCORE_BASE}{suffix}", timeout=timeout)


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
    home_team = _first(row, "home_team", "home", "team1", "left_name") or _first(left, "name", "team_name", "name_cn")
    away_team = _first(row, "away_team", "away", "team2", "right_name") or _first(right, "name", "team_name", "name_cn")
    status = normalize_status(_first(row, "state", "status", "status_cn") or "")
    home_score = _parse_int(_first(row, "home_score", "score1", "left_score") or _first(left, "score"))
    away_score = _parse_int(_first(row, "away_score", "score2", "right_score") or _first(right, "score"))
    if status not in {"live", "finished"}:
        home_score = None
        away_score = None
    if not external_id and not home_team and not away_team:
        return None
    return SourceMatch(
        source_name="qiumibao_score",
        external_id=str(external_id) if external_id is not None else None,
        home_team=str(home_team).strip() if home_team else None,
        away_team=str(away_team).strip() if away_team else None,
        kickoff_at=str(_first(row, "time", "match_time", "start_time", "date") or "").strip() or None,
        status=status,
        result_home=home_score,
        result_away=away_score,
        ht_home=_parse_int(_first(row, "ht_home", "half_home", "half_score1")),
        ht_away=_parse_int(_first(row, "ht_away", "half_away", "half_score2")),
        raw_status=str(_first(row, "state", "status", "status_cn") or ""),
    )


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


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
