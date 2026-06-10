from __future__ import annotations

import math


def proportional_devig(odds: dict[str, float]) -> dict[str, float]:
    _validate_positive_odds(odds)
    implied = {key: 1 / value for key, value in odds.items()}
    return normalize_probs(implied)


def shin_devig_three_way(odds: dict[str, float]) -> dict[str, float]:
    if len(odds) != 3:
        raise ValueError("shin_devig_three_way requires exactly three selections")
    _validate_positive_odds(odds)
    best_probs: dict[str, float] | None = None
    best_error = math.inf
    for step in range(0, 501):
        z = step / 10000
        probs = _shin_raw_probs(odds, z)
        error = abs(sum(probs.values()) - 1)
        if error < best_error:
            best_error = error
            best_probs = probs
    if best_probs is None:
        raise RuntimeError("Shin grid search failed")
    # P1 spec limits z to [0, 0.05]; boundary cases are handled by final normalization.
    return normalize_probs(best_probs)


def _shin_raw_probs(odds: dict[str, float], z: float) -> dict[str, float]:
    _validate_positive_odds(odds)
    if z < 0 or z >= 1:
        raise ValueError("z must be in [0, 1)")
    pi = {key: 1 / value for key, value in odds.items()}
    beta = sum(pi.values())
    denominator = 2 * (1 - z)
    return {
        key: (math.sqrt(z**2 + 4 * (1 - z) * implied**2 / beta) - z) / denominator
        for key, implied in pi.items()
    }


def normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    total = sum(probs.values())
    if total <= 0:
        raise ValueError("probability total must be positive")
    return {key: value / total for key, value in probs.items()}


def _validate_positive_odds(odds: dict[str, float]) -> None:
    invalid = [key for key, value in odds.items() if value <= 0]
    if invalid:
        raise ValueError(f"odds must be positive for selections: {', '.join(invalid)}")
