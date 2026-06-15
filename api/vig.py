from __future__ import annotations

from typing import Any

from model.market import shin_devig_three_way


HAD_KEY_MAP = {"3": "home", "1": "draw", "0": "away"}


def calculate_had_vig(odds: dict[str, Any] | None) -> dict[str, float] | None:
    normalized = _three_way_odds(odds)
    if normalized is None:
        return None
    margin = sum(1.0 / value for value in normalized.values()) - 1.0
    vig = margin / (1.0 + margin) if margin > -1 else None
    if vig is None:
        return None
    return {"margin": margin, "vig": vig}


def market_implied_prob_had(odds: dict[str, Any] | None) -> dict[str, float] | None:
    normalized = _three_way_odds(odds)
    if normalized is None:
        return None
    probs = shin_devig_three_way(normalized)
    return {label: probs[key] for key, label in HAD_KEY_MAP.items()}


def _three_way_odds(odds: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(odds, dict):
        return None
    values: dict[str, float] = {}
    for key in ("3", "1", "0"):
        try:
            value = float(odds[key])
        except (KeyError, TypeError, ValueError):
            return None
        if value <= 0:
            return None
        values[key] = value
    return values
