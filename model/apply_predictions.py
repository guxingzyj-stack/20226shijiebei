from __future__ import annotations

from typing import Any

from model import db
from model.dixon_coles import lambdas_from_elo, score_matrix, three_way_probs
from model.ev_signals import ev_candidates
from model.market import normalize_probs, proportional_devig, shin_devig_three_way
from model.team_names import to_english_team_name


DEFAULT_DC_PARAMS = {"c": 0.22314355131420976, "k": 0.25, "H": 80.0, "rho": -0.05, "max_goals": 10}
DEFAULT_MODEL_PARAMS = {
    "dc": DEFAULT_DC_PARAMS,
    "production_weights": {
        "production_weight_source": "default_due_to_missing_historical_market_odds",
        "w_dc": 0.35,
        "w_market": 0.65,
        "missing_current_market_policy": {
            "production_weight_source": "dc_only_due_to_missing_current_market_odds",
            "w_dc": 1.0,
            "w_market": 0.0,
        },
    },
}


def market_three_way_from_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, float] | None:
    for snapshot in snapshots:
        if snapshot["play_type"] == "had":
            odds = {key: float(value) for key, value in snapshot["odds"].items()}
            if set(odds) == {"3", "1", "0"}:
                return shin_devig_three_way(odds)
    for snapshot in snapshots:
        if snapshot["play_type"] == "hhad":
            odds = {key: float(value) for key, value in snapshot["odds"].items()}
            if set(odds) == {"3", "1", "0"}:
                return shin_devig_three_way(odds)
    for snapshot in snapshots:
        if snapshot["play_type"] == "crs":
            return _crs_market_three_way({key: float(value) for key, value in snapshot["odds"].items()})
    return None


def production_weights_for_match(snapshots: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, float | str]:
    production = params.get("production_weights") or DEFAULT_MODEL_PARAMS["production_weights"]
    has_had = any(snapshot["play_type"] == "had" and set(snapshot["odds"]) == {"3", "1", "0"} for snapshot in snapshots)
    if has_had:
        return {
            "production_weight_source": str(production.get("production_weight_source", "default_due_to_missing_historical_market_odds")),
            "w_dc": float(production.get("w_dc", 0.35)),
            "w_market": float(production.get("w_market", 0.65)),
        }
    policy = production.get("missing_current_market_policy") or {
        "production_weight_source": "dc_only_due_to_missing_current_market_odds",
        "w_dc": 1.0,
        "w_market": 0.0,
    }
    return {
        "production_weight_source": str(policy.get("production_weight_source", "dc_only_due_to_missing_current_market_odds")),
        "w_dc": float(policy.get("w_dc", 1.0)),
        "w_market": float(policy.get("w_market", 0.0)),
    }


def predict_once() -> dict[str, int]:
    with db.get_conn() as conn:
        ratings = db.fetch_team_ratings(conn)
        version = db.fetch_latest_model_version(conn)
        if version is None:
            model_version_id = db.insert_model_version(conn, "p1b-default", DEFAULT_MODEL_PARAMS)
            params = DEFAULT_MODEL_PARAMS
        else:
            model_version_id = int(version["id"])
            params = version["params"] or {}
        dc_params = {**DEFAULT_DC_PARAMS, **(params.get("dc") or {})}
        prediction_count = 0
        ev_count = 0
        market_fused_count = 0
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
            market_probs = market_three_way_from_snapshots(snapshots) or dc_probs
            weights = production_weights_for_match(snapshots, params)
            w_dc = float(weights["w_dc"])
            w_mkt = float(weights["w_market"])
            if w_mkt > 0:
                market_fused_count += 1
            else:
                dc_only_count += 1
            final = normalize_probs({key: w_dc * dc_probs[key] + w_mkt * market_probs[key] for key in ("3", "1", "0")})
            db.insert_prediction(
                conn,
                match["match_id"],
                model_version_id,
                final["3"],
                final["1"],
                final["0"],
                matrix,
                lambda_home,
                lambda_away,
            )
            prediction_count += 1
            for candidate in ev_candidates(
                snapshots,
                final,
                matrix,
                lambda_home=lambda_home,
                lambda_away=lambda_away,
                rho=dc_params["rho"],
            ):
                db.insert_ev_signal(conn, **candidate)
                ev_count += 1
        return {
            "predictions": prediction_count,
            "ev_signals": ev_count,
            "market_fused_matches": market_fused_count,
            "dc_only_matches": dc_only_count,
        }


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
