from __future__ import annotations

from typing import Any

from api._devig import calc_three_way_margin_and_vig, proportional_devig_three_way


def calculate_had_vig(odds: dict[str, Any] | None) -> dict[str, float] | None:
    normalized = _three_way_odds(odds)
    if normalized is None:
        return None
    return calc_three_way_margin_and_vig(normalized["3"], normalized["1"], normalized["0"])


def market_implied_prob_had(odds: dict[str, Any] | None) -> dict[str, float] | None:
    normalized = _three_way_odds(odds)
    if normalized is None:
        return None
    return proportional_devig_three_way(normalized["3"], normalized["1"], normalized["0"])


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
