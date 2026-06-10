import pandas as pd

from model.historical_odds import (
    HistoricalOddsMatch,
    load_manual_validation_odds,
    match_validation_game_to_odds,
    normalize_odds_row,
    validate_historical_odds_rows,
)


def test_normalize_football_data_odds_row():
    row = {
        "Date": "18/12/2022",
        "HomeTeam": "Argentina",
        "AwayTeam": "France",
        "FTHG": 3,
        "FTAG": 3,
        "B365H": 2.70,
        "B365D": 3.10,
        "B365A": 2.90,
    }
    normalized = normalize_odds_row(row, "fixture.csv")
    assert normalized is not None
    assert normalized.competition == "unknown"
    assert normalized.home_team == "Argentina"
    assert normalized.away_team == "France"
    assert normalized.odds == {"3": 2.70, "1": 3.10, "0": 2.90}
    assert normalized.bookmaker == "Bet365"


def test_match_validation_game_to_odds_prefers_score_match():
    game = type(
        "Game",
        (),
        {
            "date": pd.Timestamp("2022-12-18"),
            "home_team": "Argentina",
            "away_team": "France",
            "home_score": 3,
            "away_score": 3,
        },
    )()
    odds_rows = [
        HistoricalOddsMatch("FIFA World Cup", pd.Timestamp("2022-12-18"), "Argentina", "France", 2, 2, {"3": 2.0, "1": 3.0, "0": 4.0}, "a", "test", "closing"),
        HistoricalOddsMatch("FIFA World Cup", pd.Timestamp("2022-12-18"), "Argentina", "France", 3, 3, {"3": 2.7, "1": 3.1, "0": 2.9}, "b", "test", "closing"),
    ]
    matched = match_validation_game_to_odds(game, odds_rows)
    assert matched is not None
    assert matched.source_url == "b"


def test_load_manual_validation_odds_schema(tmp_path):
    path = tmp_path / "manual.csv"
    path.write_text(
        "competition,date,home_team,away_team,home_score,away_score,home_odds,draw_odds,away_odds,bookmaker,source_url,closing_or_opening,notes\n"
        "FIFA World Cup,2022-12-18,Argentina,France,3,3,2.70,3.10,2.90,TestBook,https://example.test,closing,fixture\n",
        encoding="utf-8",
    )
    rows = load_manual_validation_odds(path)
    assert len(rows) == 1
    assert rows[0].competition == "FIFA World Cup"
    assert rows[0].bookmaker == "TestBook"


def test_validate_historical_odds_rows_reports_completeness():
    rows = [
        HistoricalOddsMatch(
            "FIFA World Cup",
            pd.Timestamp("2022-12-18"),
            "Argentina",
            "France",
            3,
            3,
            {"3": 2.7, "1": 3.1, "0": 2.9},
            "https://example.test",
            "TestBook",
            "closing",
        )
    ]
    report = validate_historical_odds_rows(rows)
    assert report.valid_rows == 1
    assert report.invalid_rows == 0
