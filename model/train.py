from __future__ import annotations

from pathlib import Path
from typing import Any

from model import db
from model.backtest import backtest_dc_only
from model.fit_dc import fit_dixon_coles_with_diagnostics, model_version_params, prepare_training_frame
from model.history import DEFAULT_RESULTS_PATH, download_results, load_results


def train_once(results_path: Path = DEFAULT_RESULTS_PATH, download_if_missing: bool = True) -> dict[str, Any]:
    if download_if_missing and not results_path.exists():
        download_results(results_path)
    matches = load_results(results_path)
    matches_with_elo, ratings = prepare_training_frame(matches)
    fit_result = fit_dixon_coles_with_diagnostics(matches_with_elo)
    dc_params = fit_result.params
    backtest = backtest_dc_only(matches_with_elo, dc_params)
    params = model_version_params(
        dc_params,
        blend_weight=backtest.best_w_dc,
        extra={
            "backtest": {
                "market_rps": backtest.market_rps,
                "dc_rps": backtest.dc_rps,
                "blended_rps": backtest.blended_rps,
                "matches": backtest.matches,
            },
            "fit_diagnostics": fit_result.diagnostics,
        },
    )
    with db.get_conn() as conn:
        ratings_written = db.upsert_team_ratings(conn, ratings)
        model_version_id = db.insert_model_version(conn, "p1b-dixon-coles", params)
    return {
        "matches": len(matches),
        "team_ratings": ratings_written,
        "model_version": model_version_id,
        "dc_params": dc_params.as_dict(),
        "backtest": params["backtest"],
        "fit_diagnostics": fit_result.diagnostics,
    }
