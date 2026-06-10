import math

import pytest

from model.dixon_coles import lambdas_from_elo, score_matrix, score_probability, tau, three_way_probs


def test_tau_low_score_cases():
    lam = 1.2
    mu = 1.1
    rho = -0.05
    assert tau(0, 0, lam, mu, rho) == pytest.approx(1 - lam * mu * rho)
    assert tau(0, 1, lam, mu, rho) == pytest.approx(1 + lam * rho)
    assert tau(1, 0, lam, mu, rho) == pytest.approx(1 + mu * rho)
    assert tau(1, 1, lam, mu, rho) == pytest.approx(1 - rho)
    assert tau(2, 1, lam, mu, rho) == 1


def test_score_probability_positive():
    assert score_probability(1, 1, 1.2, 1.1, -0.05) > 0


def test_score_matrix_shape_and_three_way_sum():
    matrix = score_matrix(1.2, 1.1, -0.05, max_goals=10)
    assert len(matrix) == 11
    assert all(len(row) == 11 for row in matrix)
    probs = three_way_probs(matrix)
    assert sum(probs) == pytest.approx(1.0, abs=0.001)


def test_equal_elo_draw_probability_reasonable():
    lambda_home, lambda_away = lambdas_from_elo(1500, 1500, c=math.log(1.25), k=0.25, H=0.0, is_home=False)
    p_home, p_draw, p_away = three_way_probs(score_matrix(lambda_home, lambda_away, rho=-0.05))
    assert 0.20 <= p_draw <= 0.35
    assert p_home == pytest.approx(p_away, abs=0.001)
