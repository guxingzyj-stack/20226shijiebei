from model.matrix_calibration import (
    hhad_region,
    hhad_region_sums_from_matrix,
    recalibrate_score_matrix_to_hhad,
    recalibrate_score_matrix_to_three_way,
    region_sums_from_matrix,
    three_way_region,
)


def test_three_way_region():
    assert three_way_region(2, 1) == "3"
    assert three_way_region(1, 1) == "1"
    assert three_way_region(0, 1) == "0"


def test_recalibrate_score_matrix_to_three_way_matches_target_margins():
    matrix = [
        [0.10, 0.05, 0.02],
        [0.20, 0.15, 0.04],
        [0.25, 0.12, 0.07],
    ]
    target = {"3": 0.55, "1": 0.25, "0": 0.20}

    calibrated = recalibrate_score_matrix_to_three_way(matrix, target)
    sums = region_sums_from_matrix(calibrated)

    assert abs(sum(sum(row) for row in calibrated) - 1.0) < 1e-12
    assert abs(sums["3"] - target["3"]) < 1e-12
    assert abs(sums["1"] - target["1"]) < 1e-12
    assert abs(sums["0"] - target["0"]) < 1e-12


def test_hhad_region_and_recalibration_matches_target_margins():
    assert hhad_region(2, 1, -1) == "1"
    assert hhad_region(3, 1, -1) == "3"
    assert hhad_region(1, 1, -1) == "0"
    matrix = [
        [0.10, 0.05, 0.02],
        [0.20, 0.15, 0.04],
        [0.25, 0.12, 0.07],
    ]
    target = {"3": 0.30, "1": 0.24, "0": 0.46}

    calibrated = recalibrate_score_matrix_to_hhad(matrix, -1, target)
    sums = hhad_region_sums_from_matrix(calibrated, -1)

    assert abs(sum(sum(row) for row in calibrated) - 1.0) < 1e-12
    assert abs(sums["3"] - target["3"]) < 1e-12
    assert abs(sums["1"] - target["1"]) < 1e-12
    assert abs(sums["0"] - target["0"]) < 1e-12
