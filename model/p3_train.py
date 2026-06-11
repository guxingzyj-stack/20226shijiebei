from __future__ import annotations

from typing import Any

from model.gbm_model import train_gbm_or_stub


def train_p3_stub(features: list[dict[str, Any]] | None = None, labels: list[str] | None = None) -> dict[str, Any]:
    result = train_gbm_or_stub(features or [], labels or [])
    return {"status": result.status, "params": result.params or {"w_gbm": 0}}
