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
MANUAL_VALIDATION_ODDS_PATH = Path(__file__).resolve().parents[1] / "data" / "validation_odds" / "manual_validation_odds.csv"
MANUAL_VALIDATION_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "validation_odds" / "manual_validation_odds_template.csv"
)
THE_ODDS_API_VALIDATION_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "validation_odds" / "the_odds_api_2022_world_cup_h2h.csv"
)
MANUAL_COLUMNS = [
    "competition",
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "home_odds",
    "draw_odds",
    "away_odds",
    "bookmaker",
    "source_url",
    "closing_or_opening",
    "notes",
]
THE_ODDS_API_COLUMNS = [
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


TEAM_ALIASES.update(
    {
        "USA": "United States",
        "United States": "United States",
        "Korea Republic": "South Korea",
        "Iran": "Iran",
        "IR Iran": "Iran",
        "Czech Republic": "Czech Republic",
        "Czechia": "Czech Republic",
        "Turkey": "Turkey",
        "Turkiye": "Turkey",
        "Türkiye": "Turkey",
    }
)


@dataclass(frozen=True)
class HistoricalOddsMatch:
    competition: str
    date: pd.Timestamp
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    odds: dict[str, float]
    source_url: str
    bookmaker: str
    closing_or_opening: str


@dataclass(frozen=True)
class HistoricalOddsValidationReport:
    rows: int
    valid_rows: int
    invalid_rows: int
    missing_required_fields: dict[str, int]
    invalid_odds_rows: int


def load_historical_odds_sources(
    urls: list[str] | None = None,
    cache_dir: Path | None = None,
    manual_path: Path | str | None = None,
) -> list[HistoricalOddsMatch]:
    rows = load_football_data_odds(urls=urls, cache_dir=cache_dir)
    path = Path(manual_path) if manual_path is not None else MANUAL_VALIDATION_ODDS_PATH
    if path.exists():
        rows.extend(load_manual_validation_odds(path))
    return rows


def load_football_data_odds(
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


def load_manual_validation_odds(path: str | Path) -> list[HistoricalOddsMatch]:
    frame = pd.read_csv(path)
    missing_columns = [column for column in MANUAL_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"manual validation odds missing columns: {missing_columns}")
    rows: list[HistoricalOddsMatch] = []
    for _, row in frame.iterrows():
        normalized = normalize_odds_row(row.to_dict(), source_url=str(row.get("source_url") or path))
        if normalized is not None:
            rows.append(normalized)
    return rows


def load_the_odds_api_validation_odds(path: str | Path = THE_ODDS_API_VALIDATION_PATH) -> list[HistoricalOddsMatch]:
    path = Path(path)
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    missing_columns = [column for column in THE_ODDS_API_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"The Odds API validation odds missing columns: {missing_columns}")
    rows: list[HistoricalOddsMatch] = []
    for _, row in frame.iterrows():
        normalized = normalize_odds_row(row.to_dict(), source_url=str(row.get("source_url_or_key") or path))
        if normalized is not None:
            rows.append(normalized)
    return rows


def validate_historical_odds_rows(rows: list[HistoricalOddsMatch]) -> HistoricalOddsValidationReport:
    missing_required_fields = {field: 0 for field in ("competition", "date", "home_team", "away_team", "source_url", "bookmaker")}
    invalid_odds_rows = 0
    valid_rows = 0
    for row in rows:
        missing = False
        for field in missing_required_fields:
            if not getattr(row, field):
                missing_required_fields[field] += 1
                missing = True
        if any(value <= 0 for value in row.odds.values()):
            invalid_odds_rows += 1
            missing = True
        if not missing:
            valid_rows += 1
    return HistoricalOddsValidationReport(
        rows=len(rows),
        valid_rows=valid_rows,
        invalid_rows=len(rows) - valid_rows,
        missing_required_fields={key: value for key, value in missing_required_fields.items() if value},
        invalid_odds_rows=invalid_odds_rows,
    )


def normalize_odds_row(row: dict[str, Any], source_url: str = "") -> HistoricalOddsMatch | None:
    home = _first(row, "Home", "HomeTeam", "home_team")
    away = _first(row, "Away", "AwayTeam", "away_team")
    date_value = _first(row, "Date", "date")
    home_score = _first(row, "HG", "FTHG", "home_score")
    away_score = _first(row, "AG", "FTAG", "away_score")
    competition = _first(row, "competition", "Competition", "Div")
    bookmaker = _first(row, "bookmaker", "Bookmaker", "bookmaker_strategy", "source_name")
    closing_or_opening = _first(row, "closing_or_opening", "odds_type", "snapshot_time")
    source = _first(row, "source_url", "source", "SourceURL", "source_url_or_key") or source_url
    if home is None or away is None or date_value is None:
        return None
    odds = _extract_three_way_odds(row)
    if odds is None:
        return None
    return HistoricalOddsMatch(
        competition=str(competition or _competition_from_source(source_url)),
        date=_parse_date(date_value),
        home_team=canonical_team(str(home)),
        away_team=canonical_team(str(away)),
        home_score=int(home_score) if pd.notna(home_score) else None,
        away_score=int(away_score) if pd.notna(away_score) else None,
        odds=odds,
        source_url=str(source or source_url),
        bookmaker=str(bookmaker or _bookmaker_from_odds_keys(row) or "unknown"),
        closing_or_opening=str(closing_or_opening or "unknown"),
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
        ("home_odds", "draw_odds", "away_odds"),
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


def _competition_from_source(source_url: str) -> str:
    if "2223/WC" in source_url:
        return "football-data 2022/23 WC file"
    if "2324/EC" in source_url:
        return "football-data 2023/24 EC file"
    return "unknown"


def _bookmaker_from_odds_keys(row: dict[str, Any]) -> str | None:
    if all(key in row for key in ("B365H", "B365D", "B365A")):
        return "Bet365"
    if all(key in row for key in ("PSH", "PSD", "PSA")):
        return "Pinnacle"
    if all(key in row for key in ("AvgH", "AvgD", "AvgA")):
        return "market_average"
    return None
