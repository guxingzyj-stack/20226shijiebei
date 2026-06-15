from __future__ import annotations

from typing import Literal


VerdictType = Literal[
    "draw_favored",
    "balanced",
    "strong_home",
    "strong_away",
    "lean_home",
    "lean_away",
]


def build_verdict(
    p_home: float | int | str | None,
    p_draw: float | int | str | None,
    p_away: float | int | str | None,
    home_team: str | None,
    away_team: str | None,
) -> dict[str, str]:
    probs = {
        "home": _prob(p_home),
        "draw": _prob(p_draw),
        "away": _prob(p_away),
    }
    if any(value is None for value in probs.values()):
        return _balanced()

    home = str(home_team or "主队").strip() or "主队"
    away = str(away_team or "客队").strip() or "客队"
    ranked = sorted(((key, float(value)) for key, value in probs.items()), key=lambda item: item[1], reverse=True)
    top_key, top_value = ranked[0]
    second_value = ranked[1][1]

    if top_key == "draw":
        return {"verdict_type": "draw_favored", "verdict": "模型认为平局可能性最大"}
    if top_value >= 0.60:
        if top_key == "home":
            return {"verdict_type": "strong_home", "verdict": f"模型看好{home}获胜"}
        return {"verdict_type": "strong_away", "verdict": f"模型看好{away}获胜"}
    if top_value >= 0.45 and top_value - second_value > 0.15:
        if top_key == "home":
            return {"verdict_type": "lean_home", "verdict": f"模型偏向{home}"}
        return {"verdict_type": "lean_away", "verdict": f"模型偏向{away}"}
    return _balanced()


def _balanced() -> dict[str, str]:
    return {"verdict_type": "balanced", "verdict": "模型认为这场势均力敌"}


def _prob(value: float | int | str | None) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not 0 <= number <= 1:
        return None
    return number
