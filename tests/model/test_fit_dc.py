import pandas as pd

from model.fit_dc import fit_dixon_coles, prepare_training_frame


def test_fit_dixon_coles_on_small_sample():
    rows = []
    for i in range(12):
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                "home_team": "A" if i % 2 == 0 else "B",
                "away_team": "B" if i % 2 == 0 else "A",
                "home_score": 1 + (i % 3 == 0),
                "away_score": i % 2,
                "tournament": "Friendly",
                "neutral": True,
            }
        )
    enriched, _ = prepare_training_frame(pd.DataFrame(rows))
    params = fit_dixon_coles(enriched)
    assert -0.2 <= params.rho <= 0.2
    assert params.max_goals == 10
