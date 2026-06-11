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


def test_team_feature_snapshot_uses_explicit_age_when_birth_date_missing():
    snapshot = build_team_feature_snapshot(
        "A",
        {},
        [{"player_key": "a1", "team": "A", "age": "26", "market_value": ""}],
        [],
        [],
    )

    assert snapshot["avg_age"] == 26
    assert snapshot["missing_avg_age"] is False


def test_team_feature_snapshot_uses_official_profile_fields():
    snapshot = build_team_feature_snapshot(
        "A",
        {},
        [
            {
                "player_key": "a1",
                "team": "A",
                "age": "26",
                "height_cm": "180",
                "caps": "50",
                "national_team_goals": "10",
            },
            {
                "player_key": "a2",
                "team": "A",
                "age": "30",
                "height_cm": "190",
                "caps": "20",
                "national_team_goals": "2",
            },
        ],
        [],
        [],
    )

    assert snapshot["avg_height_cm"] == 185
    assert snapshot["squad_caps_total"] == 70
    assert snapshot["squad_goals_total"] == 12
    assert snapshot["missing_avg_height_cm"] is False
    assert snapshot["missing_squad_caps_total"] is False
    assert snapshot["missing_squad_goals_total"] is False


def test_match_features_include_official_profile_diffs():
    home = build_team_feature_snapshot(
        "A",
        {},
        [{"player_key": "a1", "team": "A", "height_cm": "190", "caps": "100", "national_team_goals": "30"}],
        [],
        [],
    )
    away = build_team_feature_snapshot(
        "B",
        {},
        [{"player_key": "b1", "team": "B", "height_cm": "180", "caps": "40", "national_team_goals": "5"}],
        [],
        [],
    )

    features = build_match_features("A", "B", home, away)

    assert features["avg_height_cm_diff"] == 10
    assert features["squad_caps_total_diff"] == 60
    assert features["squad_goals_total_diff"] == 25
