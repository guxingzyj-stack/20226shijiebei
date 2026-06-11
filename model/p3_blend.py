from __future__ import annotations

from typing import Any

from model.market import normalize_probs


def normalize_blend_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.0, float(weights.get(key, 0.0))) for key in ("w_dc", "w_market", "w_gbm")}
    total = sum(cleaned.values())
    if total <= 0:
        return {"w_dc": 0.3, "w_market": 0.7, "w_gbm": 0.0}
    return {key: value / total for key, value in cleaned.items()}


def choose_p3_weights(
    p1_weights: dict[str, float],
    gbm_status: str,
    p1_rps: float | None = None,
    gbm_rps: float | None = None,
    requested_w_gbm: float = 0.0,
) -> dict[str, Any]:
    if gbm_status != "ok":
        return {"weights": normalize_blend_weights({**p1_weights, "w_gbm": 0.0}), "status": gbm_status}
    if p1_rps is not None and gbm_rps is not None and gbm_rps > p1_rps:
        return {"weights": normalize_blend_weights({**p1_weights, "w_gbm": 0.0}), "status": "gbm_zero_weight_rps_worse_than_p1"}
    w_gbm = max(0.0, requested_w_gbm)
    remaining = max(0.0, 1.0 - w_gbm)
    base = normalize_blend_weights({**p1_weights, "w_gbm": 0.0})
    return {
        "weights": normalize_blend_weights(
            {"w_dc": base["w_dc"] * remaining, "w_market": base["w_market"] * remaining, "w_gbm": w_gbm}
        ),
        "status": "ok",
    }


def blend_three_way(
    p_dc: dict[str, float],
    p_market: dict[str, float],
    p_gbm: dict[str, float] | None,
    weights: dict[str, float],
) -> dict[str, float]:
    normalized_weights = normalize_blend_weights(weights)
    p_gbm = p_gbm or {"3": 0.0, "1": 0.0, "0": 0.0}
    return normalize_probs(
        {
            key: normalized_weights["w_dc"] * p_dc[key]
            + normalized_weights["w_market"] * p_market[key]
            + normalized_weights["w_gbm"] * p_gbm[key]
            for key in ("3", "1", "0")
        }
    )
