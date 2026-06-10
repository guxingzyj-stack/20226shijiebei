import pandas as pd

from model.historical_odds import HistoricalOddsMatch, match_validation_game_to_odds, normalize_odds_row


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
    assert normalized.home_team == "Argentina"
    assert normalized.away_team == "France"
    assert normalized.odds == {"3": 2.70, "1": 3.10, "0": 2.90}


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
        HistoricalOddsMatch(pd.Timestamp("2022-12-18"), "Argentina", "France", 2, 2, {"3": 2.0, "1": 3.0, "0": 4.0}, "a"),
        HistoricalOddsMatch(pd.Timestamp("2022-12-18"), "Argentina", "France", 3, 3, {"3": 2.7, "1": 3.1, "0": 2.9}, "b"),
    ]
    matched = match_validation_game_to_odds(game, odds_rows)
    assert matched is not None
    assert matched.source_url == "b"
