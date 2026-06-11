from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GbmUnavailable(Exception):
    pass


@dataclass(frozen=True)
class GbmResult:
    status: str
    model: Any | None = None
    params: dict[str, Any] | None = None


def train_gbm_or_stub(features: list[dict[str, Any]], labels: list[str], params: dict[str, Any] | None = None) -> GbmResult:
    try:
        import lightgbm as lgb  # type: ignore
    except Exception:
        return GbmResult(status="gbm_unavailable", model=None, params={"w_gbm": 0})
    if not features or not labels:
        return GbmResult(status="insufficient_training_data", model=None, params={"w_gbm": 0})
    keys = sorted({key for row in features for key in row if isinstance(row.get(key), (int, float, bool))})
    x = [[float(row.get(key) or 0.0) for key in keys] for row in features]
    label_map = {"3": 0, "1": 1, "0": 2}
    y = [label_map[str(label)] for label in labels]
    model = lgb.LGBMClassifier(objective="multiclass", num_class=3, **(params or {}))
    model.fit(x, y)
    return GbmResult(status="ok", model={"model": model, "feature_keys": keys}, params=params or {})


def predict_gbm_or_zero_weight(model_payload: Any, features: dict[str, Any]) -> dict[str, Any]:
    if not model_payload:
        return {"status": "gbm_unavailable", "weight": 0.0, "probs": {"3": 0.0, "1": 0.0, "0": 0.0}}
    model = model_payload.get("model")
    keys = model_payload.get("feature_keys") or []
    if model is None or not keys:
        return {"status": "gbm_unavailable", "weight": 0.0, "probs": {"3": 0.0, "1": 0.0, "0": 0.0}}
    row = [[float(features.get(key) or 0.0) for key in keys]]
    probs = model.predict_proba(row)[0]
    return {"status": "ok", "weight": None, "probs": {"3": float(probs[0]), "1": float(probs[1]), "0": float(probs[2])}}
