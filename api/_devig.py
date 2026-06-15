from __future__ import annotations


def proportional_devig_three_way(
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
) -> dict[str, float] | None:
    odds = _valid_odds(home_odds, draw_odds, away_odds)
    if odds is None:
        return None
    home, draw, away = odds
    raw_home = 1.0 / home
    raw_draw = 1.0 / draw
    raw_away = 1.0 / away
    raw_sum = raw_home + raw_draw + raw_away
    if raw_sum <= 0:
        return None
    return {
        "home": raw_home / raw_sum,
        "draw": raw_draw / raw_sum,
        "away": raw_away / raw_sum,
    }


def calc_three_way_margin_and_vig(
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
) -> dict[str, float] | None:
    odds = _valid_odds(home_odds, draw_odds, away_odds)
    if odds is None:
        return None
    home, draw, away = odds
    raw_sum = 1.0 / home + 1.0 / draw + 1.0 / away
    if raw_sum <= 0:
        return None
    margin = raw_sum - 1.0
    return {
        "margin": margin,
        "vig": margin / raw_sum,
    }


def _valid_odds(
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
) -> tuple[float, float, float] | None:
    try:
        home = float(home_odds)  # type: ignore[arg-type]
        draw = float(draw_odds)  # type: ignore[arg-type]
        away = float(away_odds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if home <= 1 or draw <= 1 or away <= 1:
        return None
    return home, draw, away
