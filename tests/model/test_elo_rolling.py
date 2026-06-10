import pandas as pd

from model.elo import add_rolling_elo_columns


def test_add_rolling_elo_columns_updates_ratings():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01"),
                "home_team": "A",
                "away_team": "B",
                "home_score": 1,
                "away_score": 0,
                "tournament": "Friendly",
                "neutral": True,
            },
            {
                "date": pd.Timestamp("2024-01-02"),
                "home_team": "A",
                "away_team": "C",
                "home_score": 0,
                "away_score": 0,
                "tournament": "Friendly",
                "neutral": True,
            },
        ]
    )
    enriched, ratings = add_rolling_elo_columns(matches)
    assert enriched.loc[0, "elo_home_pre"] == 1500
    assert enriched.loc[1, "elo_home_pre"] > 1500
    assert ratings["A"] > 1500
    assert ratings["B"] < 1500
