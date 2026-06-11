import pytest

from model.ev_signals import (
    EV_RESEARCH_ONLY_THRESHOLD,
    calibrate_hafu_probs_to_final_three_way,
    ev_candidates,
    hafu_probs_from_lambdas,
    normalize_hafu_selection_key,
    result_code,
)


def test_result_code():
    assert result_code(2, 1) == "3"
    assert result_code(1, 1) == "1"
    assert result_code(0, 1) == "0"


def test_hafu_probs_from_lambdas_returns_nine_keys_and_sums_to_one():
    probs = hafu_probs_from_lambdas(1.4, 1.1, -0.04)
    assert set(probs) == {"33", "31", "30", "13", "11", "10", "03", "01", "00"}
    assert sum(probs.values()) == pytest.approx(1.0)
    assert all(value >= 0 for value in probs.values())


def test_normalize_hafu_selection_key():
    assert normalize_hafu_selection_key("3-3") == "33"
    assert normalize_hafu_selection_key("胜平") == "31"
    with pytest.raises(KeyError):
        normalize_hafu_selection_key("unknown")


def test_hafu_ev_candidates_from_odds_json():
    snapshots = [
        {
            "id": 10,
            "match_id": "m1",
            "play_type": "hafu",
            "goal_line": None,
            "odds": {"3-3": 1.5, "1-1": 4.0, "0-0": 8.0},
        }
    ]
    candidates = ev_candidates(
        snapshots,
        {"3": 0.5, "1": 0.25, "0": 0.25},
        [[1.0]],
        lambda_home=1.4,
        lambda_away=1.1,
        rho=-0.04,
        threshold=-1.0,
    )
    assert candidates
    assert {candidate["play_type"] for candidate in candidates} == {"hafu"}


def test_ev_candidates_marks_research_only_above_fuse_threshold():
    snapshots = [
        {"id": 10, "match_id": "m1", "play_type": "had", "goal_line": None, "odds": {"3": 2.0}}
    ]

    candidates = ev_candidates(snapshots, {"3": 0.7, "1": 0.2, "0": 0.1}, [[1.0]], threshold=-1.0)

    assert candidates[0]["ev"] > EV_RESEARCH_ONLY_THRESHOLD
    assert candidates[0]["research_only"] is True
    assert candidates[0]["reason"] == "model_market_divergence_too_large"


def test_hafu_calibration_matches_final_three_way_margins():
    raw = hafu_probs_from_lambdas(1.4, 1.1, -0.04)
    target = {"3": 0.62, "1": 0.22, "0": 0.16}

    calibrated = calibrate_hafu_probs_to_final_three_way(raw, target)

    assert sum(prob for key, prob in calibrated.items() if key[1] == "3") == pytest.approx(target["3"])
    assert sum(prob for key, prob in calibrated.items() if key[1] == "1") == pytest.approx(target["1"])
    assert sum(prob for key, prob in calibrated.items() if key[1] == "0") == pytest.approx(target["0"])
