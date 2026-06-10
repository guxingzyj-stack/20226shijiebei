import pytest

from model.ev_signals import handicap_three_way_probs, total_goals_probs


def test_handicap_three_way_probs_sum_to_one():
    matrix = [
        [0.10, 0.20],
        [0.30, 0.40],
    ]
    probs = handicap_three_way_probs(matrix, goal_line=0)
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs["3"] == pytest.approx(0.30)
    assert probs["1"] == pytest.approx(0.50)
    assert probs["0"] == pytest.approx(0.20)


def test_total_goals_probs_bucket_seven_plus():
    matrix = [[0.0 for _ in range(11)] for _ in range(11)]
    matrix[0][0] = 0.2
    matrix[3][4] = 0.3
    matrix[5][5] = 0.5
    probs = total_goals_probs(matrix)
    assert probs["0"] == pytest.approx(0.2)
    assert probs["7"] == pytest.approx(0.8)
