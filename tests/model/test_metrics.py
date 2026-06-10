import pytest

from model.metrics import rps_three_way


def test_perfect_home_win_prediction():
    assert rps_three_way(1, 0, 0, "3") == 0


def test_completely_wrong_home_prediction_when_away_wins():
    assert rps_three_way(1, 0, 0, "0") == 1


def test_uniform_prediction_fixed_value_for_any_outcome():
    assert rps_three_way(1 / 3, 1 / 3, 1 / 3, "3") == pytest.approx(5 / 18)
    assert rps_three_way(1 / 3, 1 / 3, 1 / 3, "1") == pytest.approx(1 / 9)
    assert rps_three_way(1 / 3, 1 / 3, 1 / 3, "0") == pytest.approx(5 / 18)


def test_invalid_outcome():
    with pytest.raises(ValueError):
        rps_three_way(1 / 3, 1 / 3, 1 / 3, "x")
