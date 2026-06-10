import pytest

from model.elo import expected_score, goal_diff_multiplier, match_k_factor, update_elo_pair


def test_expected_score_equal_neutral_is_half():
    assert expected_score(1500, 1500, home_advantage_units=0.0, is_home_advantage=False) == pytest.approx(0.5)


def test_expected_score_400_point_gap():
    assert expected_score(1900, 1500, home_advantage_units=0.0, is_home_advantage=False) == pytest.approx(0.909, abs=0.001)


def test_goal_diff_multiplier():
    assert goal_diff_multiplier(1) == 1
    assert goal_diff_multiplier(2) == 1.5
    assert goal_diff_multiplier(3) == pytest.approx((11 + 3) / 8)


def test_k_factor_and_update_are_symmetric():
    assert match_k_factor("世界杯") == 35
    assert match_k_factor("qualifier") == 30
    assert match_k_factor("friendly") == 20
    new_home, new_away = update_elo_pair(1500, 1500, 2, 1, "世界杯")
    assert new_home > 1500
    assert new_away < 1500
    assert new_home - 1500 == pytest.approx(1500 - new_away)
