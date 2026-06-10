import pandas as pd
import sys

from model.backtest import MarketBacktestReport, backtest_with_market_odds, choose_blend_weight
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


def test_backtest_with_30_market_matches_outputs_rps_and_weights():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2022-11-20") + pd.Timedelta(days=index),
                "home_team": f"Home {index}",
                "away_team": f"Away {index}",
                "home_score": 1,
                "away_score": 0,
                "tournament": "FIFA World Cup",
                "neutral": True,
            }
            for index in range(30)
        ]
    )
    enriched, _ = prepare_training_frame(matches)
    odds = [
        HistoricalOddsMatch(
            competition="FIFA World Cup",
            date=row.date,
            home_team=row.home_team,
            away_team=row.away_team,
            home_score=row.home_score,
            away_score=row.away_score,
            odds={"3": 2.20, "1": 3.10, "0": 3.40},
            source_url="soccer_fifa_world_cup",
            bookmaker="median_available_bookmakers:test",
            closing_or_opening="snapshot",
        )
        for row in matches.itertuples(index=False)
    ]

    report = backtest_with_market_odds(enriched, DCParams(c=0.2, k=1.0, H=80, rho=-0.05), odds)

    assert report.matched_odds_matches == 30
    assert report.market_rps is not None
    assert report.dc_rps is not None
    assert report.blended_rps is not None
    assert report.best_w_dc is not None
    assert report.best_w_market is not None
    assert report.status == "ok"


def test_cli_backtest_market_exits_nonzero_when_less_than_30(monkeypatch):
    import model.cli as cli

    report = MarketBacktestReport(
        validation_target="2022 World Cup",
        odds_source="the_odds_api",
        sport_key="soccer_fifa_world_cup",
        odds_sources=["cache.csv"],
        total_validation_matches=64,
        matched_odds_matches=29,
        unmatched_matches=35,
        market_rps=0.2,
        dc_rps=0.21,
        blended_rps=0.19,
        best_w_dc=0.3,
        best_w_market=0.7,
        status="insufficient_historical_odds",
        unmatched_reasons={"no_event_same_day": 35},
    )
    monkeypatch.setattr(cli, "load_results", lambda: pd.DataFrame())
    monkeypatch.setattr(cli, "prepare_training_frame", lambda matches: (pd.DataFrame(), None))
    monkeypatch.setattr(cli, "fit_dixon_coles_with_diagnostics", lambda matches: type("Fit", (), {"params": object()})())
    monkeypatch.setattr(cli, "backtest_market_from_source", lambda matches, params, source: report)
    monkeypatch.setattr(sys, "argv", ["model.cli", "backtest-market", "--source", "the_odds_api"])

    assert cli.main() == 1
