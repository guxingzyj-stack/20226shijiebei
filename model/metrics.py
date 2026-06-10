from __future__ import annotations


def rps_three_way(p_home: float, p_draw: float, p_away: float, outcome: str) -> float:
    if outcome == "3":
        e_home, e_draw = 1.0, 0.0
    elif outcome == "1":
        e_home, e_draw = 0.0, 1.0
    elif outcome == "0":
        e_home, e_draw = 0.0, 0.0
    else:
        raise ValueError("outcome must be one of '3', '1', '0'")
    return 0.5 * ((p_home - e_home) ** 2 + (p_home + p_draw - e_home - e_draw) ** 2)
