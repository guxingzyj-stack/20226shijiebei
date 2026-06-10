from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import requests

from sources.common import MatchOdds, OddsEntry, SourceError, clean_float, is_world_cup_league, parse_datetime


SOURCE_NAME = "sporttery"
BASE = "https://webapi.sporttery.cn/gateway/jc/football"
ENDPOINTS = {
    "getMatchCalculatorV1": f"{BASE}/getMatchCalculatorV1.qry",
    "getMatchListV1": f"{BASE}/getMatchListV1.qry",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.sporttery.cn/",
    "Accept": "application/json, text/plain, */*",
}
POOL_CODES = ("had", "hhad", "crs", "ttg", "hafu")


def fetch_all(session: requests.Session | None = None) -> list[MatchOdds]:
    session = session or requests.Session()
    merged: dict[str, MatchOdds] = {}
    last_error: Exception | None = None
    for pool_code in POOL_CODES:
        try:
            rows = fetch_pool(session, pool_code)
        except Exception as exc:
            last_error = exc
            continue
        for row in rows:
            existing = merged.get(row.match_id)
            if existing:
                existing.odds.extend(row.odds)
            else:
                merged[row.match_id] = row
        time.sleep(2)
    if not merged and last_error:
        raise SourceError(str(last_error)) from last_error
    return list(merged.values())


def fetch_pool(session: requests.Session, pool_code: str) -> list[MatchOdds]:
    params = {"poolCode": pool_code, "channel": "c"}
    response = session.get(ENDPOINTS["getMatchCalculatorV1"], params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return parse_payload(payload, pool_code)


def probe(session: requests.Session | None = None) -> tuple[str, int, str, list[MatchOdds]]:
    session = session or requests.Session()
    url = f"{ENDPOINTS['getMatchCalculatorV1']}?poolCode=hhad,had&channel=c"
    response = session.get(url, headers=HEADERS, timeout=15)
    prefix = response.text[:500]
    if not response.ok:
        return url, response.status_code, prefix, []
    matches = parse_payload(response.json(), None)
    return url, response.status_code, prefix, matches


def parse_payload(payload: Any, requested_pool: str | None) -> list[MatchOdds]:
    records = _find_match_records(payload)
    parsed: list[MatchOdds] = []
    for item in records:
        league = _first(item, "leagueName", "league", "matchLeagueName", "l_cn", "leagueAbbName")
        if not is_world_cup_league(league):
            continue
        match_id = str(_first(item, "matchId", "id", "matchNumStr", "matchNum", "serialNo") or "").strip()
        home = _first(item, "homeTeamName", "homeTeam", "h_cn", "homeName")
        away = _first(item, "awayTeamName", "awayTeam", "a_cn", "awayName")
        kickoff = parse_datetime(_first(item, "matchDate", "matchTime", "kickoffTime", "date"))
        if not match_id or not home or not away or kickoff is None:
            continue
        odds_entries = _parse_odds_entries(item, requested_pool)
        if not odds_entries:
            continue
        parsed.append(
            MatchOdds(
                match_id=match_id,
                match_num=str(_first(item, "matchNumStr", "matchNum", "serialNo") or match_id),
                league="世界杯",
                home_team=str(home),
                away_team=str(away),
                kickoff_at=kickoff,
                status=_status(item),
                odds=odds_entries,
            )
        )
    return parsed


def _find_match_records(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            keys = set(value.keys())
            if keys & {"homeTeamName", "homeTeam", "h_cn"} and keys & {"awayTeamName", "awayTeam", "a_cn"}:
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return found


def _parse_odds_entries(item: dict[str, Any], requested_pool: str | None) -> list[OddsEntry]:
    entries: list[OddsEntry] = []
    for play_type in ("had", "hhad", "crs", "ttg", "hafu"):
        node = _first(item, play_type, play_type.upper(), f"{play_type}Odds")
        odds = _extract_odds_dict(node)
        if odds:
            entries.append(OddsEntry(play_type=play_type, odds=odds, goal_line=_goal_line(item, node, play_type)))
    if not entries and requested_pool:
        odds = _extract_odds_dict(item)
        if odds:
            entries.append(OddsEntry(play_type=requested_pool, odds=odds, goal_line=_goal_line(item, item, requested_pool)))
    return entries


def _extract_odds_dict(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, dict):
            candidate = _first(raw, "odds", "sp", "value")
        else:
            candidate = raw
        odd = clean_float(candidate)
        if odd is not None:
            result[str(key)] = odd
    return result


def _goal_line(item: dict[str, Any], node: Any, play_type: str) -> Decimal | None:
    if play_type != "hhad":
        return None
    raw = _first(item, "goalLine", "fixedodds", "letPoint")
    if raw is None and isinstance(node, dict):
        raw = _first(node, "goalLine", "fixedodds", "letPoint")
    try:
        return Decimal(str(raw)) if raw is not None else None
    except Exception:
        return None


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _status(item: dict[str, Any]) -> str:
    raw = str(_first(item, "status", "matchStatus", "state") or "").lower()
    if raw in {"finished", "live", "postponed", "scheduled"}:
        return raw
    return "scheduled"
