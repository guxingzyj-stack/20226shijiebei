from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from model.dixon_coles import lambdas_from_elo, score_probability
from model.elo import add_rolling_elo_columns
from model.history import ELO_START_DATE, TRAINING_START_DATE


XI = 0.0015
MAX_GOALS = 10


@dataclass(frozen=True)
class DCParams:
    c: float
    k: float
    H: float
    rho: float
    xi: float = XI
    max_goals: int = MAX_GOALS

    def as_dict(self) -> dict[str, float | int]:
        return {
            "c": self.c,
            "k": self.k,
            "H": self.H,
            "rho": self.rho,
            "xi": self.xi,
            "max_goals": self.max_goals,
        }


@dataclass(frozen=True)
class DCFitResult:
    params: DCParams
    diagnostics: dict[str, Any]


def prepare_training_frame(matches: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    warmup_matches = matches[matches["date"] >= pd.Timestamp(ELO_START_DATE)].copy()
    enriched, ratings = add_rolling_elo_columns(warmup_matches)
    training = enriched[enriched["date"] >= pd.Timestamp(TRAINING_START_DATE)].reset_index(drop=True)
    return training, ratings


def fit_dixon_coles(matches_with_elo: pd.DataFrame, xi: float = XI) -> DCParams:
    return fit_dixon_coles_with_diagnostics(matches_with_elo, xi).params


def fit_dixon_coles_with_diagnostics(matches_with_elo: pd.DataFrame, xi: float = XI) -> DCFitResult:
    if matches_with_elo.empty:
        raise ValueError("cannot fit Dixon-Coles parameters on empty data")
    initial_params = [math.log(1.25), 1.0, 80.0, -0.05]
    bounds = [(math.log(0.2), math.log(4.5)), (0.05, 2.0), (-200.0, 200.0), (-0.2, 0.2)]
    max_date = matches_with_elo["date"].max()
    days_ago = (max_date - matches_with_elo["date"]).dt.days.astype(float)
    weights = np.exp(-xi * days_ago.to_numpy())

    def objective(theta: np.ndarray) -> float:
        c, k, H, rho = theta
        nll = 0.0
        for idx, row in enumerate(matches_with_elo.itertuples(index=False)):
            lambda_home, lambda_away = lambdas_from_elo(
                float(row.elo_home_pre),
                float(row.elo_away_pre),
                c,
                k,
                H,
                not bool(row.neutral),
            )
            home_goals = min(int(row.home_score), MAX_GOALS)
            away_goals = min(int(row.away_score), MAX_GOALS)
            probability = max(score_probability(home_goals, away_goals, lambda_home, lambda_away, rho), 1e-12)
            nll -= weights[idx] * math.log(probability)
        return float(nll)

    result = minimize(
        objective,
        x0=np.array(initial_params, dtype=float),
        method="L-BFGS-B",
        bounds=bounds,
    )
    if not result.success:
        raise RuntimeError(f"Dixon-Coles fit failed: {result.message}")
    c, k, H, rho = [float(value) for value in result.x]
    params = DCParams(c=c, k=k, H=H, rho=rho, xi=xi, max_goals=MAX_GOALS)
    diagnostics = {
        "optimizer_success": bool(result.success),
        "optimizer_message": str(result.message),
        "nll": float(result.fun),
        "training_rows": int(len(matches_with_elo)),
        "skipped_rows": 0,
        "bounds": {
            "c": list(bounds[0]),
            "k": list(bounds[1]),
            "H": list(bounds[2]),
            "rho": list(bounds[3]),
        },
        "initial_params": {"c": initial_params[0], "k": initial_params[1], "H": initial_params[2], "rho": initial_params[3]},
        "final_params": params.as_dict(),
    }
    return DCFitResult(params=params, diagnostics=diagnostics)


def model_version_params(dc_params: DCParams, blend_weight: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dc": dc_params.as_dict(),
        "backtest_weights": {
            "backtest_market_status": "missing_historical_odds",
            "backtest_w_dc": blend_weight,
            "backtest_w_market": 1 - blend_weight,
        },
        "production_weights": {
            "w_dc": 0.3,
            "w_market": 0.7,
            "source": "temporary_market_prior_until_historical_backtest_complete",
            "todo": "replace with backtest-optimized weights after verified historical market odds",
        },
        "elo_start_date": ELO_START_DATE,
        "training_start_date": TRAINING_START_DATE,
    }
    if extra:
        payload.update(extra)
    return payload
