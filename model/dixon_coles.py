from __future__ import annotations

import math


def tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lambda_home * lambda_away * rho
    if x == 0 and y == 1:
        return 1 + lambda_home * rho
    if x == 1 and y == 0:
        return 1 + lambda_away * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1


def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def score_probability(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    return tau(x, y, lambda_home, lambda_away, rho) * poisson_pmf(x, lambda_home) * poisson_pmf(y, lambda_away)


def lambdas_from_elo(
    r_home: float,
    r_away: float,
    c: float,
    k: float,
    H: float,
    is_home: bool,
) -> tuple[float, float]:
    d = (r_home - r_away + H * (1 if is_home else 0)) / 400
    return math.exp(c + k * d), math.exp(c - k * d)


def score_matrix(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int = 10,
) -> list[list[float]]:
    return [
        [score_probability(home_goals, away_goals, lambda_home, lambda_away, rho) for away_goals in range(max_goals + 1)]
        for home_goals in range(max_goals + 1)
    ]


def three_way_probs(matrix: list[list[float]]) -> tuple[float, float, float]:
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                p_home += probability
            elif home_goals == away_goals:
                p_draw += probability
            else:
                p_away += probability
    return p_home, p_draw, p_away
