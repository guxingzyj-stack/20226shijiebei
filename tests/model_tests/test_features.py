from model.features import build_match_features, build_team_feature_snapshot


def test_team_feature_snapshot_handles_missing_players():
    snapshot = build_team_feature_snapshot("Nowhere", {}, [], [], [])

    assert snapshot["team"] == "Nowhere"
    assert snapshot["elo"] == 1500.0
    assert snapshot["missing_squad_value_total"] is True
    assert snapshot["core_minutes_share"] == 0.0


def test_match_features_use_diffs_and_missing_flags():
    home = build_team_feature_snapshot(
        "A",
        {"A": 1600},
        [{"player_key": "a1", "team": "A", "birth_date": "2000-01-01", "market_value": 100}],
        [{"player_key": "a1", "minutes": 900, "xg": 5, "xa": 4}],
        [{"player_key": "a1", "team": "A", "status": "out"}],
    )
    away = build_team_feature_snapshot("B", {"B": 1500}, [], [], [])

    features = build_match_features("A", "B", home, away)

    assert features["elo_diff"] == 100
    assert features["squad_value_log_diff"] > 0
    assert features["injured_core_count_diff"] == 1
    assert features["is_home"] == 1
    assert features["away_missing_squad_value_total"] is True
