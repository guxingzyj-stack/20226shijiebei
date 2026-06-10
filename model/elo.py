from __future__ import annotations

from typing import Any

import pandas as pd


def expected_score(r_home: float, r_away: float, home_advantage_units: float, is_home_advantage: bool) -> float:
    advantage = home_advantage_units * 100 * (1 if is_home_advantage else 0)
    return 1 / (1 + 10 ** (-(r_home + advantage - r_away) / 400))


def goal_diff_multiplier(goal_diff: int) -> float:
    abs_goal_diff = abs(goal_diff)
    if abs_goal_diff <= 1:
        return 1
    if abs_goal_diff == 2:
        return 1.5
    return (11 + abs_goal_diff) / 8


def match_k_factor(tournament: str) -> float:
    normalized = tournament.lower()
    if "世界杯" in tournament or "world cup" in normalized or "major" in normalized:
        return 35
    if "预选" in tournament or "qualifier" in normalized:
        return 30
    if "友谊" in tournament or "friendly" in normalized:
        return 20
    return 20


def update_elo_pair(
    r_home: float,
    r_away: float,
    goals_home: int,
    goals_away: int,
    tournament: str,
    home_advantage_units: float = 0.0,
    neutral: bool = True,
) -> tuple[float, float]:
    expected_home = expected_score(r_home, r_away, home_advantage_units, not neutral)
    if goals_home > goals_away:
        result_home = 1.0
    elif goals_home == goals_away:
        result_home = 0.5
    else:
        result_home = 0.0
    k_factor = match_k_factor(tournament)
    multiplier = goal_diff_multiplier(goals_home - goals_away)
    delta = k_factor * multiplier * (result_home - expected_home)
    return r_home + delta, r_away - delta


def add_rolling_elo_columns(
    matches: pd.DataFrame,
    initial_elo: float = 1500.0,
    home_advantage_units: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    required = {"date", "home_team", "away_team", "home_score", "away_score", "tournament", "neutral"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing columns for Elo rolling: {sorted(missing)}")
    ratings: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    ordered = matches.sort_values("date").reset_index(drop=True)
    for row in ordered.to_dict("records"):
        home_team = row["home_team"]
        away_team = row["away_team"]
        r_home = ratings.get(home_team, initial_elo)
        r_away = ratings.get(away_team, initial_elo)
        enriched = dict(row)
        enriched["elo_home_pre"] = r_home
        enriched["elo_away_pre"] = r_away
        rows.append(enriched)
        new_home, new_away = update_elo_pair(
            r_home,
            r_away,
            int(row["home_score"]),
            int(row["away_score"]),
            str(row["tournament"]),
            home_advantage_units=home_advantage_units,
            neutral=bool(row["neutral"]),
        )
        ratings[home_team] = new_home
        ratings[away_team] = new_away
    return pd.DataFrame(rows), ratings
