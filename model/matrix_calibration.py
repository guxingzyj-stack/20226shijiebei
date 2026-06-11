from __future__ import annotations

from model.market import normalize_probs


THREE_WAY_KEYS = ("3", "1", "0")


def three_way_region(score_home: int, score_away: int) -> str:
    if score_home > score_away:
        return "3"
    if score_home == score_away:
        return "1"
    return "0"


def hhad_region(score_home: int, score_away: int, goal_line: float) -> str:
    adjusted_home = score_home + goal_line
    if adjusted_home > score_away:
        return "3"
    if adjusted_home == score_away:
        return "1"
    return "0"


def region_sums_from_matrix(matrix: list[list[float]]) -> dict[str, float]:
    sums = {"3": 0.0, "1": 0.0, "0": 0.0}
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            sums[three_way_region(home_goals, away_goals)] += float(probability)
    return normalize_probs(sums)


def hhad_region_sums_from_matrix(matrix: list[list[float]], goal_line: float) -> dict[str, float]:
    sums = {"3": 0.0, "1": 0.0, "0": 0.0}
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            sums[hhad_region(home_goals, away_goals, goal_line)] += float(probability)
    return normalize_probs(sums)


def recalibrate_score_matrix_to_three_way(
    dc_matrix: list[list[float]],
    target_probs: dict[str, float],
) -> list[list[float]]:
    source_probs = region_sums_from_matrix(dc_matrix)
    normalized_target = normalize_probs({key: float(target_probs[key]) for key in THREE_WAY_KEYS})
    return _recalibrate_by_region(dc_matrix, source_probs, normalized_target, three_way_region)


def recalibrate_score_matrix_to_hhad(
    dc_matrix: list[list[float]],
    goal_line: float,
    target_hhad_probs: dict[str, float],
) -> list[list[float]]:
    source_probs = hhad_region_sums_from_matrix(dc_matrix, goal_line)
    normalized_target = normalize_probs({key: float(target_hhad_probs[key]) for key in THREE_WAY_KEYS})
    return _recalibrate_by_region(
        dc_matrix,
        source_probs,
        normalized_target,
        lambda home_goals, away_goals: hhad_region(home_goals, away_goals, goal_line),
    )


def _recalibrate_by_region(
    matrix: list[list[float]],
    source_probs: dict[str, float],
    target_probs: dict[str, float],
    region_fn,
) -> list[list[float]]:
    factors = {
        key: (target_probs[key] / source_probs[key] if source_probs[key] > 0 else 0.0)
        for key in THREE_WAY_KEYS
    }
    calibrated: list[list[float]] = []
    for home_goals, row in enumerate(matrix):
        calibrated_row: list[float] = []
        for away_goals, probability in enumerate(row):
            calibrated_row.append(float(probability) * factors[region_fn(home_goals, away_goals)])
        calibrated.append(calibrated_row)
    total = sum(sum(row) for row in calibrated)
    if total <= 0:
        raise ValueError("calibrated score matrix total must be positive")
    return [[value / total for value in row] for row in calibrated]
