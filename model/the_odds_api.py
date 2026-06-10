from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any
import os

import pandas as pd
import requests

from model.historical_odds import HistoricalOddsMatch, canonical_team


API_BASE_URL = "https://api.the-odds-api.com/v4"
MISSING_API_KEY_MESSAGE = "THE_ODDS_API_KEY is required for the_odds_api historical backtest"
BOOKMAKER_PRIORITY = ("bet365", "pinnacle", "williamhill", "unibet")
VALIDATION_ODDS_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "validation_odds" / "the_odds_api_2022_world_cup_h2h.csv"
)
VALIDATION_ODDS_COLUMNS = [
    "competition",
    "date",
    "kickoff_time",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "snapshot_time",
    "bookmaker_strategy",
    "home_odds",
    "draw_odds",
    "away_odds",
    "source_name",
    "source_url_or_key",
    "notes",
]


@dataclass(frozen=True)
class FetchValidationOddsReport:
    cache_file: Path
    sport_key: str | None
    rows: int
    matched_matches: int
    unmatched_matches: int
    unmatched_reasons: dict[str, int]
    bookmaker_strategy: str
    snapshots_tried: list[str]
    quota_usage_estimate: int


def get_api_key() -> str:
    api_key = os.getenv("THE_ODDS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(MISSING_API_KEY_MESSAGE)
    return api_key


def list_historical_sports(api_key: str, as_of_date: str) -> list[dict]:
    del as_of_date
    response = requests.get(
        f"{API_BASE_URL}/sports/",
        params={"apiKey": api_key, "all": "true"},
        timeout=30,
    )
    _raise_for_status_without_secret(response)
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("unexpected sports response from The Odds API")
    return [sport for sport in payload if _is_soccer_sport(sport)]


def find_world_cup_sport_keys(api_key: str) -> list[str]:
    sports = list_historical_sports(api_key, as_of_date="2022-11-20T00:00:00Z")
    candidates = []
    for sport in sports:
        haystack = " ".join(
            str(sport.get(key, "")) for key in ("key", "group", "title", "description")
        ).lower()
        if "world" in haystack and "cup" in haystack and not sport.get("has_outrights"):
            candidates.append(str(sport["key"]))
    return candidates


def fetch_historical_h2h_snapshot(
    api_key: str,
    sport_key: str,
    snapshot_time_iso: str,
    regions: str = "uk",
    markets: str = "h2h",
    odds_format: str = "decimal",
) -> dict:
    response = requests.get(
        f"{API_BASE_URL}/historical/sports/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
            "date": snapshot_time_iso,
        },
        timeout=30,
    )
    _raise_for_status_without_secret(response)
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("unexpected historical odds response from The Odds API")
    return payload


def extract_h2h_matches(snapshot_json: dict) -> list[HistoricalOddsMatch]:
    snapshot_time = str(snapshot_json.get("timestamp") or snapshot_json.get("snapshot_time") or "")
    events = snapshot_json.get("data", snapshot_json)
    if not isinstance(events, list):
        raise ValueError("The Odds API historical snapshot missing data list")

    matches: list[HistoricalOddsMatch] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        home = event.get("home_team")
        away = event.get("away_team")
        commence_time = event.get("commence_time")
        if not home or not away or not commence_time:
            continue
        bookmaker_odds = _bookmaker_h2h_odds(event, str(home), str(away))
        if not bookmaker_odds:
            continue
        odds = {
            "3": float(median([entry["3"] for entry in bookmaker_odds])),
            "1": float(median([entry["1"] for entry in bookmaker_odds])),
            "0": float(median([entry["0"] for entry in bookmaker_odds])),
        }
        bookmaker_keys = [entry["bookmaker"] for entry in bookmaker_odds]
        strategy = _bookmaker_strategy(bookmaker_keys)
        sport_key = event.get("sport_key") or snapshot_json.get("sport_key") or "unknown_sport"
        event_id = event.get("id") or "unknown_event"
        matches.append(
            HistoricalOddsMatch(
                competition="The Odds API historical h2h",
                date=pd.to_datetime(commence_time, utc=True).normalize().tz_localize(None),
                home_team=canonical_team(str(home)),
                away_team=canonical_team(str(away)),
                home_score=None,
                away_score=None,
                odds=odds,
                source_url=f"the_odds_api:{sport_key}:{event_id}",
                bookmaker=strategy,
                closing_or_opening=f"snapshot:{snapshot_time or 'unknown'}",
            )
        )
    return matches


def fetch_validation_odds_cache(
    validation_matches: pd.DataFrame,
    api_key: str | None = None,
    sport_key: str | None = None,
    cache_path: Path = VALIDATION_ODDS_CACHE_PATH,
    regions: str = "uk",
) -> FetchValidationOddsReport:
    api_key = api_key or get_api_key()
    candidates = [sport_key] if sport_key else find_world_cup_sport_keys(api_key)
    selected_key = next((key for key in candidates if key), None)
    if selected_key is None:
        return _write_empty_cache_report(cache_path, "no_supported_world_cup_sport_key")

    rows: list[dict[str, Any]] = []
    unmatched_reasons: dict[str, int] = {}
    snapshots_tried = ["kickoff-2h", "kickoff-6h", "kickoff-24h"]
    target_frame = validation_matches[
        (validation_matches["date"].dt.year == 2022) & (validation_matches["tournament"] == "FIFA World Cup")
    ].copy()

    for match in target_frame.itertuples(index=False):
        matched = None
        api_error = False
        kickoff = _kickoff_time_for_match(match)
        for hours_before in (2, 6, 24):
            snapshot_time = kickoff - timedelta(hours=hours_before)
            snapshot_iso = _to_iso_z(snapshot_time)
            try:
                snapshot = fetch_historical_h2h_snapshot(api_key, selected_key, snapshot_iso, regions=regions)
            except requests.HTTPError:
                api_error = True
                continue
            candidates_for_snapshot = extract_h2h_matches(snapshot)
            matched = _match_snapshot_event(match, candidates_for_snapshot)
            if matched is not None:
                rows.append(_cache_row_from_match(match, kickoff, snapshot_iso, selected_key, matched))
                break
        if matched is None:
            reason = "api_error" if api_error else "no_event_same_day"
            unmatched_reasons[reason] = unmatched_reasons.get(reason, 0) + 1

    _write_cache_rows(cache_path, rows)
    return FetchValidationOddsReport(
        cache_file=cache_path,
        sport_key=selected_key,
        rows=len(rows),
        matched_matches=len(rows),
        unmatched_matches=len(target_frame) - len(rows),
        unmatched_reasons=unmatched_reasons,
        bookmaker_strategy="median_of_available_h2h_bookmakers",
        snapshots_tried=snapshots_tried,
        quota_usage_estimate=len(target_frame) * len(snapshots_tried) * 10,
    )


def _is_soccer_sport(sport: dict) -> bool:
    haystack = " ".join(str(sport.get(key, "")) for key in ("key", "group", "title", "description")).lower()
    return "soccer" in haystack or str(sport.get("group", "")).lower() == "soccer"


def _raise_for_status_without_secret(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        url_without_query = response.url.split("?", 1)[0]
        message = f"The Odds API request failed: status={response.status_code} url={url_without_query}"
        raise requests.HTTPError(message, response=response) from exc


def _bookmaker_h2h_odds(event: dict, home_team: str, away_team: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bookmaker in sorted(event.get("bookmakers") or [], key=_bookmaker_sort_key):
        odds = _extract_bookmaker_market(bookmaker, home_team, away_team)
        if odds is not None:
            rows.append({"bookmaker": str(bookmaker.get("key") or bookmaker.get("title") or "unknown"), **odds})
    return rows


def _bookmaker_sort_key(bookmaker: dict) -> tuple[int, str]:
    key = str(bookmaker.get("key") or "").lower()
    priority = BOOKMAKER_PRIORITY.index(key) if key in BOOKMAKER_PRIORITY else len(BOOKMAKER_PRIORITY)
    return priority, key


def _extract_bookmaker_market(bookmaker: dict, home_team: str, away_team: str) -> dict[str, float] | None:
    for market in bookmaker.get("markets") or []:
        if market.get("key") != "h2h":
            continue
        prices: dict[str, float] = {}
        for outcome in market.get("outcomes") or []:
            name = canonical_team(str(outcome.get("name", "")))
            price = outcome.get("price")
            if price is None:
                continue
            if name == canonical_team(home_team):
                prices["3"] = float(price)
            elif name == canonical_team(away_team):
                prices["0"] = float(price)
            elif name.lower() in {"draw", "tie"}:
                prices["1"] = float(price)
        if set(prices) == {"3", "1", "0"} and all(value > 0 for value in prices.values()):
            return prices
    return None


def _bookmaker_strategy(bookmaker_keys: list[str]) -> str:
    if len(bookmaker_keys) == 1:
        return f"single_bookmaker:{bookmaker_keys[0]}"
    preferred = [key for key in bookmaker_keys if key in BOOKMAKER_PRIORITY]
    suffix = ",".join(preferred or bookmaker_keys)
    return f"median_available_bookmakers:{suffix}"


def _match_snapshot_event(match: Any, odds_rows: list[HistoricalOddsMatch]) -> HistoricalOddsMatch | None:
    home = canonical_team(str(match.home_team))
    away = canonical_team(str(match.away_team))
    date = pd.Timestamp(match.date).normalize()
    for odds in odds_rows:
        if odds.date.normalize() != date:
            continue
        if odds.home_team == home and odds.away_team == away:
            return odds
    return None


def _kickoff_time_for_match(match: Any) -> pd.Timestamp:
    kickoff_value = getattr(match, "kickoff_time", None)
    if kickoff_value:
        return pd.to_datetime(kickoff_value, utc=True)
    # The martj42 source has dates but no kick-off time. Keep this visible in
    # the cache notes instead of silently claiming an exact source timestamp.
    return pd.Timestamp(match.date, tz="UTC") + pd.Timedelta(hours=15)


def _to_iso_z(timestamp: pd.Timestamp) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cache_row_from_match(
    match: Any,
    kickoff: pd.Timestamp,
    snapshot_iso: str,
    sport_key: str,
    odds: HistoricalOddsMatch,
) -> dict[str, Any]:
    return {
        "competition": str(match.tournament),
        "date": pd.Timestamp(match.date).date().isoformat(),
        "kickoff_time": _to_iso_z(kickoff),
        "home_team": str(match.home_team),
        "away_team": str(match.away_team),
        "home_score": int(match.home_score),
        "away_score": int(match.away_score),
        "snapshot_time": snapshot_iso,
        "bookmaker_strategy": odds.bookmaker,
        "home_odds": odds.odds["3"],
        "draw_odds": odds.odds["1"],
        "away_odds": odds.odds["0"],
        "source_name": "the_odds_api",
        "source_url_or_key": sport_key,
        "notes": "kickoff_time_estimated_from_date_15:00Z_when_source_has_no_time",
    }


def _write_empty_cache_report(cache_path: Path, reason: str) -> FetchValidationOddsReport:
    _write_cache_rows(cache_path, [])
    return FetchValidationOddsReport(
        cache_file=cache_path,
        sport_key=None,
        rows=0,
        matched_matches=0,
        unmatched_matches=0,
        unmatched_reasons={reason: 1},
        bookmaker_strategy="median_of_available_h2h_bookmakers",
        snapshots_tried=["kickoff-2h", "kickoff-6h", "kickoff-24h"],
        quota_usage_estimate=0,
    )


def _write_cache_rows(cache_path: Path, rows: list[dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=VALIDATION_ODDS_COLUMNS).to_csv(cache_path, index=False)
