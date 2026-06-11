from __future__ import annotations

from copy import deepcopy
from typing import Any

from model import db
from model.dixon_coles import lambdas_from_elo, score_matrix, three_way_probs
from model.ev_signals import ev_candidates
from model.market import normalize_probs, proportional_devig, shin_devig_three_way
from model.matrix_calibration import (
    hhad_region_sums_from_matrix,
    recalibrate_score_matrix_to_hhad,
    recalibrate_score_matrix_to_three_way,
    region_sums_from_matrix,
)
from model.history import ELO_START_DATE, TRAINING_START_DATE
from model.team_names import to_english_team_name


PREDICTION_RUN_MODEL_NAME = "p1b-dixon-coles-predict-run"
DEFAULT_DC_PARAMS = {"c": 0.22314355131420976, "k": 0.25, "H": 80.0, "rho": -0.05, "xi": 0.0015, "max_goals": 10}
DEFAULT_MODEL_PARAMS = {
    "dc": DEFAULT_DC_PARAMS,
    "elo_start_date": ELO_START_DATE,
    "training_start_date": TRAINING_START_DATE,
    "production_weights": {
        "w_dc": 0.3,
        "w_market": 0.7,
        "source": "temporary_market_prior_until_historical_backtest_complete",
        "todo": "replace with backtest-optimized weights after verified historical market odds",
    },
}


def prediction_run_model_name() -> str:
    return PREDICTION_RUN_MODEL_NAME


def params_with_p1_5_metadata(params: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(params)
    normalized["dc"] = {**DEFAULT_DC_PARAMS, **(normalized.get("dc") or {})}
    normalized.setdefault("production_weights", DEFAULT_MODEL_PARAMS["production_weights"])
    normalized["elo_start_date"] = ELO_START_DATE
    normalized["training_start_date"] = TRAINING_START_DATE
    return normalized


def market_three_way_from_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, float] | None:
    for snapshot in snapshots:
        if snapshot["play_type"] == "had":
            odds = {key: float(value) for key, value in snapshot["odds"].items()}
            if set(odds) == {"3", "1", "0"}:
                return shin_devig_three_way(odds)
    return None


def _latest_three_way_snapshot(snapshots: list[dict[str, Any]], play_type: str) -> dict[str, Any] | None:
    for snapshot in snapshots:
        if snapshot["play_type"] == play_type and set(snapshot["odds"]) == {"3", "1", "0"}:
            return snapshot
    return None


def production_weights_for_match(snapshots: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, float | str]:
    production = params.get("production_weights") or DEFAULT_MODEL_PARAMS["production_weights"]
    has_had = any(snapshot["play_type"] == "had" and set(snapshot["odds"]) == {"3", "1", "0"} for snapshot in snapshots)
    has_hhad = any(snapshot["play_type"] == "hhad" and set(snapshot["odds"]) == {"3", "1", "0"} for snapshot in snapshots)
    if has_had or has_hhad:
        return {
            "production_weight_source": str(production.get("source", "temporary_market_prior_until_historical_backtest_complete")),
            "w_dc": float(production.get("w_dc", 0.3)),
            "w_market": float(production.get("w_market", 0.7)),
        }
    return {
        "production_weight_source": "missing_current_market_odds",
        "w_dc": 0.0,
        "w_market": 0.0,
    }


def predict_once() -> dict[str, int]:
    with db.get_conn() as conn:
        ratings = db.fetch_team_ratings(conn)
        version = db.fetch_latest_model_version(conn)
        if version is None:
            params = params_with_p1_5_metadata(DEFAULT_MODEL_PARAMS)
        else:
            params = params_with_p1_5_metadata(version["params"] or {})
        model_version_id = db.insert_model_version(conn, prediction_run_model_name(), params)
        dc_params = {**DEFAULT_DC_PARAMS, **(params.get("dc") or {})}
        prediction_count = 0
        ev_count = 0
        market_fused_count = 0
        market_source_had_count = 0
        market_source_hhad_count = 0
        skipped_missing_market_count = 0
        dc_only_count = 0
        for match in db.fetch_upcoming_matches(conn):
            home = to_english_team_name(match["home_team"])
            away = to_english_team_name(match["away_team"])
            r_home = ratings.get(home, 1500.0)
            r_away = ratings.get(away, 1500.0)
            lambda_home, lambda_away = lambdas_from_elo(r_home, r_away, dc_params["c"], dc_params["k"], dc_params["H"], False)
            matrix = score_matrix(lambda_home, lambda_away, dc_params["rho"], int(dc_params["max_goals"]))
            dc_home, dc_draw, dc_away = three_way_probs(matrix)
            dc_probs = normalize_probs({"3": dc_home, "1": dc_draw, "0": dc_away})
            snapshots = db.fetch_latest_snapshots_for_match(conn, match["match_id"])
            weights = production_weights_for_match(snapshots, params)
            if weights["production_weight_source"] == "missing_current_market_odds":
                skipped_missing_market_count += 1
                continue
            w_dc = float(weights["w_dc"])
            w_mkt = float(weights["w_market"])
            if w_mkt <= 0:
                skipped_missing_market_count += 1
                continue
            had_snapshot = _latest_three_way_snapshot(snapshots, "had")
            hhad_snapshot = _latest_three_way_snapshot(snapshots, "hhad")
            if had_snapshot is not None:
                market_probs = shin_devig_three_way({key: float(value) for key, value in had_snapshot["odds"].items()})
                final = normalize_probs({key: w_dc * dc_probs[key] + w_mkt * market_probs[key] for key in ("3", "1", "0")})
                calibrated_matrix = recalibrate_score_matrix_to_three_way(matrix, final)
                market_source_had_count += 1
            elif hhad_snapshot is not None and hhad_snapshot.get("goal_line") is not None:
                goal_line = float(hhad_snapshot["goal_line"])
                market_hhad = shin_devig_three_way({key: float(value) for key, value in hhad_snapshot["odds"].items()})
                dc_hhad = hhad_region_sums_from_matrix(matrix, goal_line)
                final_hhad = normalize_probs({key: w_dc * dc_hhad[key] + w_mkt * market_hhad[key] for key in ("3", "1", "0")})
                calibrated_matrix = recalibrate_score_matrix_to_hhad(matrix, goal_line, final_hhad)
                final = region_sums_from_matrix(calibrated_matrix)
                market_source_hhad_count += 1
            else:
                skipped_missing_market_count += 1
                continue
            market_fused_count += 1
            db.insert_prediction(
                conn,
                match["match_id"],
                model_version_id,
                final["3"],
                final["1"],
                final["0"],
                calibrated_matrix,
                lambda_home,
                lambda_away,
            )
            prediction_count += 1
            for candidate in ev_candidates(
                snapshots,
                final,
                calibrated_matrix,
                lambda_home=lambda_home,
                lambda_away=lambda_away,
                rho=dc_params["rho"],
            ):
                db.insert_ev_signal(
                    conn,
                    match_id=candidate["match_id"],
                    model_version=model_version_id,
                    play_type=candidate["play_type"],
                    selection=candidate["selection"],
                    model_prob=candidate["model_prob"],
                    odds=candidate["odds"],
                    ev=candidate["ev"],
                    snapshot_id=candidate["snapshot_id"],
                    research_only=bool(candidate.get("research_only", False)),
                    reason=candidate.get("reason"),
                    suggestion_eligible=bool(candidate.get("suggestion_eligible", False)),
                )
                ev_count += 1
        run_stats = {
            "predictions": prediction_count,
            "predictions_written": prediction_count,
            "ev_signals": ev_count,
            "ev_signals_written": ev_count,
            "market_fused_matches": market_fused_count,
            "market_source_had_count": market_source_had_count,
            "market_source_hhad_count": market_source_hhad_count,
            "skipped_missing_market_matches": skipped_missing_market_count,
            "skipped_missing_market_count": skipped_missing_market_count,
            "dc_only_matches": dc_only_count,
            "dc_only_count": dc_only_count,
        }
        params["prediction_run"] = run_stats
        params["last_predict_stats"] = run_stats
        db.update_model_version_params(conn, model_version_id, params)
        return run_stats


def _crs_market_three_way(odds: dict[str, float]) -> dict[str, float]:
    selection_probs = proportional_devig(odds)
    probs = {"3": 0.0, "1": 0.0, "0": 0.0}
    for score, probability in selection_probs.items():
        if ":" not in score:
            if score.startswith("胜"):
                probs["3"] += probability
            elif score.startswith("平"):
                probs["1"] += probability
            elif score.startswith("负"):
                probs["0"] += probability
            continue
        home_text, away_text = score.split(":", 1)
        home_goals = int(home_text)
        away_goals = int(away_text)
        if home_goals > away_goals:
            probs["3"] += probability
        elif home_goals == away_goals:
            probs["1"] += probability
        else:
            probs["0"] += probability
    return normalize_probs(probs)
