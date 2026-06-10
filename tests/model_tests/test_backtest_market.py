import pandas as pd

from model.backtest import backtest_with_market_odds, choose_blend_weight
from model.fit_dc import DCParams, prepare_training_frame
from model.historical_odds import HistoricalOddsMatch


def test_choose_blend_weight_uses_real_market_probs():
    dc = [{"3": 0.9, "1": 0.05, "0": 0.05}]
    market = [{"3": 0.1, "1": 0.1, "0": 0.8}]
    best_w, _ = choose_blend_weight(dc, market, ["0"])
    assert best_w < 1.0


def test_backtest_with_market_odds_matches_sample_game():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2022-12-18"),
                "home_team": "Argentina",
                "away_team": "France",
                "home_score": 3,
                "away_score": 3,
                "tournament": "FIFA World Cup",
                "neutral": True,
            }
        ]
    )
    enriched, _ = prepare_training_frame(matches)
    odds = [
        HistoricalOddsMatch(
            competition="FIFA World Cup",
            date=pd.Timestamp("2022-12-18"),
            home_team="Argentina",
            away_team="France",
            home_score=3,
            away_score=3,
            odds={"3": 2.70, "1": 3.10, "0": 2.90},
            source_url="test",
            bookmaker="TestBook",
            closing_or_opening="closing",
        )
    ]
    report = backtest_with_market_odds(enriched, DCParams(c=0.2, k=1.0, H=80, rho=-0.05), odds)
    assert report.matched_odds_matches == 1
    assert report.market_rps is not None
    assert report.dc_rps is not None
    assert report.blended_rps is not None
    assert report.best_w_dc is not None


def test_backtest_with_zero_matches_is_explicit_failure_report():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2022-12-18"),
                "home_team": "Argentina",
                "away_team": "France",
                "home_score": 3,
                "away_score": 3,
                "tournament": "FIFA World Cup",
                "neutral": True,
            }
        ]
    )
    enriched, _ = prepare_training_frame(matches)
    report = backtest_with_market_odds(enriched, DCParams(c=0.2, k=1.0, H=80, rho=-0.05), [])
    assert report.matched_odds_matches == 0
    assert report.status == "insufficient_historical_odds"
    assert report.market_rps is None
