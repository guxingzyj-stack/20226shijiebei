from __future__ import annotations

from decimal import Decimal
from typing import Any

from model.dixon_coles import score_matrix
from model.market import normalize_probs


EV_RESEARCH_ONLY_THRESHOLD = 0.15


def suggestion_eligible_for_signal(play_type: str, ev: float, research_only: bool = False) -> bool:
    return play_type in {"had", "hhad"} and ev > 0 and ev <= EV_RESEARCH_ONLY_THRESHOLD and not research_only


def handicap_three_way_probs(matrix: list[list[float]], goal_line: float) -> dict[str, float]:
    probs = {"3": 0.0, "1": 0.0, "0": 0.0}
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            adjusted = home_goals + goal_line - away_goals
            if adjusted > 0:
                probs["3"] += probability
            elif adjusted == 0:
                probs["1"] += probability
            else:
                probs["0"] += probability
    return normalize_probs(probs)


def score_selection_probs(matrix: list[list[float]]) -> dict[str, float]:
    probs: dict[str, float] = {}
    other_home = 0.0
    other_draw = 0.0
    other_away = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            key = f"{home_goals}:{away_goals}"
            if home_goals <= 5 and away_goals <= 5:
                probs[key] = probability
            elif home_goals > away_goals:
                other_home += probability
            elif home_goals == away_goals:
                other_draw += probability
            else:
                other_away += probability
    probs["胜其它"] = other_home
    probs["平其它"] = other_draw
    probs["负其它"] = other_away
    return probs


def total_goals_probs(matrix: list[list[float]]) -> dict[str, float]:
    probs = {str(total): 0.0 for total in range(0, 7)}
    probs["7"] = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            total = home_goals + away_goals
            probs[str(total if total < 7 else 7)] += probability
    return probs


def result_code(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "3"
    if home_goals == away_goals:
        return "1"
    return "0"


def hafu_probs_from_lambdas(
    lambda_home: float,
    lambda_away: float,
    rho: float,
    max_goals: int = 10,
) -> dict[str, float]:
    keys = ("33", "31", "30", "13", "11", "10", "03", "01", "00")
    probs = {key: 0.0 for key in keys}
    ht_matrix = score_matrix(0.45 * lambda_home, 0.45 * lambda_away, rho, max_goals=max_goals)
    sh_matrix = score_matrix(0.55 * lambda_home, 0.55 * lambda_away, rho, max_goals=max_goals)
    for ht_home, ht_row in enumerate(ht_matrix):
        for ht_away, p_ht in enumerate(ht_row):
            ht_result = result_code(ht_home, ht_away)
            for sh_home, sh_row in enumerate(sh_matrix):
                for sh_away, p_sh in enumerate(sh_row):
                    ft_result = result_code(ht_home + sh_home, ht_away + sh_away)
                    probs[ht_result + ft_result] += p_ht * p_sh
    return normalize_probs(probs)


def calibrate_hafu_probs_to_final_three_way(
    hafu_probs: dict[str, float],
    final_three_way: dict[str, float],
) -> dict[str, float]:
    full_time_sums = {"3": 0.0, "1": 0.0, "0": 0.0}
    for key, probability in hafu_probs.items():
        full_time_sums[key[1]] += probability
    target = normalize_probs({key: float(final_three_way[key]) for key in ("3", "1", "0")})
    calibrated: dict[str, float] = {}
    for key, probability in hafu_probs.items():
        full_time_region = key[1]
        source = full_time_sums[full_time_region]
        calibrated[key] = probability * (target[full_time_region] / source if source > 0 else 0.0)
    return normalize_probs(calibrated)


def normalize_hafu_selection_key(raw_key: str) -> str:
    value = str(raw_key).strip()
    compact = value.replace("-", "").replace("_", "").replace(" ", "")
    if compact in {"33", "31", "30", "13", "11", "10", "03", "01", "00"}:
        return compact
    chinese = {
        "胜胜": "33",
        "胜平": "31",
        "胜负": "30",
        "平胜": "13",
        "平平": "11",
        "平负": "10",
        "负胜": "03",
        "负平": "01",
        "负负": "00",
    }
    if value in chinese:
        return chinese[value]
    raise KeyError(f"unmapped hafu selection key: {raw_key}")


def selection_model_probs(
    play_type: str,
    final_three_way: dict[str, float],
    matrix: list[list[float]],
    goal_line: Decimal | float | None = None,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    rho: float | None = None,
) -> dict[str, float]:
    if play_type == "had":
        return final_three_way
    if play_type == "hhad":
        return handicap_three_way_probs(matrix, float(goal_line or 0))
    if play_type == "crs":
        return score_selection_probs(matrix)
    if play_type == "ttg":
        return total_goals_probs(matrix)
    if play_type == "hafu" and lambda_home is not None and lambda_away is not None and rho is not None:
        return calibrate_hafu_probs_to_final_three_way(
            hafu_probs_from_lambdas(lambda_home, lambda_away, rho),
            final_three_way,
        )
    return {}


def ev_candidates(
    snapshots: list[dict[str, Any]],
    final_three_way: dict[str, float],
    matrix: list[list[float]],
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    rho: float | None = None,
    threshold: float = -0.02,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for snapshot in snapshots:
        model_probs = selection_model_probs(
            snapshot["play_type"],
            final_three_way,
            matrix,
            snapshot.get("goal_line"),
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            rho=rho,
        )
        odds = snapshot["odds"]
        for selection, odd in odds.items():
            lookup_key = normalize_hafu_selection_key(selection) if snapshot["play_type"] == "hafu" else selection
            if lookup_key not in model_probs:
                continue
            probability = float(model_probs[lookup_key])
            ev = probability * float(odd) - 1
            if ev > threshold:
                research_only = ev > EV_RESEARCH_ONLY_THRESHOLD
                candidates.append(
                    {
                        "match_id": snapshot["match_id"],
                        "play_type": snapshot["play_type"],
                        "selection": selection,
                        "model_prob": probability,
                        "odds": float(odd),
                        "ev": ev,
                        "snapshot_id": snapshot["id"],
                        "research_only": research_only,
                        "reason": "model_market_divergence_too_large" if research_only else None,
                        "suggestion_eligible": suggestion_eligible_for_signal(snapshot["play_type"], ev, research_only),
                    }
                )
    return candidates
