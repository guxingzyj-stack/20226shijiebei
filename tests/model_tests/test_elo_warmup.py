import pandas as pd

from model.fit_dc import model_version_params, prepare_training_frame
from model.history import ELO_START_DATE, TRAINING_START_DATE
from model.fit_dc import DCParams


def test_prepare_training_frame_uses_2000_warmup_but_trains_from_2015():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2001-01-01"),
                "home_team": "Argentina",
                "away_team": "Haiti",
                "home_score": 3,
                "away_score": 0,
                "tournament": "Friendly",
                "neutral": True,
            },
            {
                "date": pd.Timestamp("2016-01-01"),
                "home_team": "Argentina",
                "away_team": "Haiti",
                "home_score": 2,
                "away_score": 0,
                "tournament": "Friendly",
                "neutral": True,
            },
        ]
    )

    training, ratings = prepare_training_frame(matches)

    assert len(training) == 1
    assert training.iloc[0]["date"] == pd.Timestamp("2016-01-01")
    assert training.iloc[0]["elo_home_pre"] > 1500
    assert training.iloc[0]["elo_away_pre"] < 1500
    assert ratings["Argentina"] > training.iloc[0]["elo_home_pre"]


def test_model_version_params_records_warmup_and_training_dates():
    params = model_version_params(DCParams(c=0.2, k=0.3, H=80, rho=-0.03), blend_weight=0.5)

    assert params["elo_start_date"] == ELO_START_DATE
    assert params["training_start_date"] == TRAINING_START_DATE
