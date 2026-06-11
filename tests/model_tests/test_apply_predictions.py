from model.apply_predictions import market_three_way_from_snapshots, production_weights_for_match


def test_production_weights_use_market_when_had_exists():
    snapshots = [{"play_type": "had", "odds": {"3": 1.8, "1": 3.2, "0": 4.0}}]
    weights = production_weights_for_match(snapshots, {})
    assert weights["w_dc"] == 0.3
    assert weights["w_market"] == 0.7
    assert weights["production_weight_source"] == "temporary_market_prior_until_historical_backtest_complete"


def test_production_weights_dc_only_when_had_missing():
    snapshots = [{"play_type": "crs", "odds": {"1:0": 7.0}}]
    weights = production_weights_for_match(snapshots, {})
    assert weights["w_dc"] == 0.0
    assert weights["w_market"] == 0.0
    assert weights["production_weight_source"] == "missing_current_market_odds"


def test_production_weights_use_market_when_only_hhad_exists():
    snapshots = [{"play_type": "hhad", "goal_line": -1, "odds": {"3": 2.6, "1": 3.4, "0": 2.1}}]
    weights = production_weights_for_match(snapshots, {})
    assert weights["w_dc"] == 0.3
    assert weights["w_market"] == 0.7
    assert weights["production_weight_source"] == "temporary_market_prior_until_historical_backtest_complete"


def test_market_three_way_prefers_had_snapshot():
    snapshots = [{"play_type": "had", "odds": {"3": 1.8, "1": 3.2, "0": 4.0}}]
    probs = market_three_way_from_snapshots(snapshots)
    assert probs is not None
    assert abs(sum(probs.values()) - 1.0) < 1e-9
