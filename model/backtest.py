from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from model.dixon_coles import lambdas_from_elo, score_matrix, three_way_probs
from model.fit_dc import DCParams
from model.metrics import rps_three_way
from model.market import normalize_probs


VALIDATION_TOURNAMENTS = {"FIFA World Cup", "UEFA Euro", "Copa América"}


@dataclass(frozen=True)
class BacktestResult:
    market_rps: float | None
    dc_rps: float
    blended_rps: float
    best_w_dc: float
    matches: int


def outcome_from_score(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "3"
    if home_score == away_score:
        return "1"
    return "0"


def dc_probs_for_row(row, params: DCParams) -> dict[str, float]:
    lambda_home, lambda_away = lambdas_from_elo(
        float(row.elo_home_pre),
        float(row.elo_away_pre),
        params.c,
        params.k,
        params.H,
        not bool(row.neutral),
    )
    p_home, p_draw, p_away = three_way_probs(score_matrix(lambda_home, lambda_away, params.rho, params.max_goals))
    return normalize_probs({"3": p_home, "1": p_draw, "0": p_away})


def validation_frame(matches_with_elo: pd.DataFrame) -> pd.DataFrame:
    years = matches_with_elo["date"].dt.year
    is_validation = (
        ((years == 2022) & (matches_with_elo["tournament"] == "FIFA World Cup"))
        | ((years == 2024) & (matches_with_elo["tournament"] == "UEFA Euro"))
        | ((years == 2024) & (matches_with_elo["tournament"] == "Copa América"))
    )
    return matches_with_elo[is_validation].copy()


def rps_for_probs(probs: dict[str, float], outcome: str) -> float:
    return rps_three_way(probs["3"], probs["1"], probs["0"], outcome)


def choose_blend_weight(
    dc_probs: list[dict[str, float]],
    market_probs: list[dict[str, float]],
    outcomes: list[str],
) -> tuple[float, float]:
    best_weight = 1.0
    best_rps = math.inf
    for step in range(0, 21):
        w_dc = step / 20
        scores = []
        for dc, market, outcome in zip(dc_probs, market_probs, outcomes):
            blended = normalize_probs({key: w_dc * dc[key] + (1 - w_dc) * market[key] for key in ("3", "1", "0")})
            scores.append(rps_for_probs(blended, outcome))
        mean_rps = sum(scores) / len(scores)
        if mean_rps < best_rps:
            best_weight = w_dc
            best_rps = mean_rps
    return best_weight, best_rps


def backtest_dc_only(matches_with_elo: pd.DataFrame, params: DCParams) -> BacktestResult:
    frame = validation_frame(matches_with_elo)
    if frame.empty:
        raise ValueError("validation set is empty")
    scores = []
    for row in frame.itertuples(index=False):
        probs = dc_probs_for_row(row, params)
        scores.append(rps_for_probs(probs, outcome_from_score(int(row.home_score), int(row.away_score))))
    dc_rps = sum(scores) / len(scores)
    return BacktestResult(market_rps=None, dc_rps=dc_rps, blended_rps=dc_rps, best_w_dc=1.0, matches=len(frame))
