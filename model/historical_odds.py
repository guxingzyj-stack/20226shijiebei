from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests


FOOTBALL_DATA_ODDS_URLS = [
    "https://www.football-data.co.uk/mmz4281/2223/WC.csv",
    "https://www.football-data.co.uk/mmz4281/2324/EC.csv",
]

TEAM_ALIASES = {
    "United States": "USA",
    "USA": "United States",
    "South Korea": "South Korea",
    "Korea Republic": "South Korea",
    "Czech Republic": "Czechia",
    "Czechia": "Czech Republic",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Curaçao": "Curaçao",
    "Curacao": "Curaçao",
}


@dataclass(frozen=True)
class HistoricalOddsMatch:
    date: pd.Timestamp
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    odds: dict[str, float]
    source_url: str


def load_historical_odds_sources(
    urls: list[str] | None = None,
    cache_dir: Path | None = None,
) -> list[HistoricalOddsMatch]:
    rows: list[HistoricalOddsMatch] = []
    for url in urls or FOOTBALL_DATA_ODDS_URLS:
        text = _load_url_text(url, cache_dir)
        frame = pd.read_csv(StringIO(text))
        for _, row in frame.iterrows():
            try:
                normalized = normalize_odds_row(row.to_dict(), url)
            except (KeyError, ValueError, TypeError):
                continue
            if normalized is not None:
                rows.append(normalized)
    return rows


def normalize_odds_row(row: dict[str, Any], source_url: str = "") -> HistoricalOddsMatch | None:
    home = _first(row, "Home", "HomeTeam", "home_team")
    away = _first(row, "Away", "AwayTeam", "away_team")
    date_value = _first(row, "Date", "date")
    home_score = _first(row, "HG", "FTHG", "home_score")
    away_score = _first(row, "AG", "FTAG", "away_score")
    if home is None or away is None or date_value is None:
        return None
    odds = _extract_three_way_odds(row)
    if odds is None:
        return None
    return HistoricalOddsMatch(
        date=_parse_date(date_value),
        home_team=canonical_team(str(home)),
        away_team=canonical_team(str(away)),
        home_score=int(home_score) if pd.notna(home_score) else None,
        away_score=int(away_score) if pd.notna(away_score) else None,
        odds=odds,
        source_url=source_url,
    )


def match_validation_game_to_odds(game: Any, odds_rows: list[HistoricalOddsMatch]) -> HistoricalOddsMatch | None:
    game_date = pd.Timestamp(game.date).normalize()
    home = canonical_team(str(game.home_team))
    away = canonical_team(str(game.away_team))
    home_score = int(game.home_score)
    away_score = int(game.away_score)
    candidates: list[tuple[int, HistoricalOddsMatch]] = []
    for odds in odds_rows:
        date_delta = abs((odds.date.normalize() - game_date).days)
        if date_delta > 2:
            continue
        if odds.home_team != home or odds.away_team != away:
            continue
        score_bonus = 0 if odds.home_score == home_score and odds.away_score == away_score else 10
        candidates.append((date_delta + score_bonus, odds))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def canonical_team(name: str) -> str:
    stripped = name.strip()
    return TEAM_ALIASES.get(stripped, stripped)


def _extract_three_way_odds(row: dict[str, Any]) -> dict[str, float] | None:
    field_sets = [
        ("B365H", "B365D", "B365A"),
        ("PSH", "PSD", "PSA"),
        ("AvgH", "AvgD", "AvgA"),
        ("MaxH", "MaxD", "MaxA"),
        ("H", "D", "A"),
    ]
    for home_key, draw_key, away_key in field_sets:
        if home_key in row and draw_key in row and away_key in row:
            values = [row[home_key], row[draw_key], row[away_key]]
            if all(pd.notna(value) and float(value) > 0 for value in values):
                return {"3": float(values[0]), "1": float(values[1]), "0": float(values[2])}
    return None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and pd.notna(row[key]):
            return row[key]
    return None


def _parse_date(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, dayfirst=True, errors="raise").normalize()


def _load_url_text(url: str, cache_dir: Path | None) -> str:
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / (url.rsplit("/", 1)[-1] or "odds.csv")
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    text = response.text
    if cache_dir:
        path.write_text(text, encoding="utf-8")
    return text
