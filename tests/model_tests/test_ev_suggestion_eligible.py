from model.ev_signals import ev_candidates, suggestion_eligible_for_signal


def test_non_had_hhad_ev_signal_is_not_suggestion_eligible():
    assert suggestion_eligible_for_signal("crs", 0.10, False) is False
    assert suggestion_eligible_for_signal("ttg", 0.10, False) is False
    assert suggestion_eligible_for_signal("hafu", 0.10, False) is False


def test_ev_over_threshold_is_research_only_and_not_suggestion_eligible():
    matrix = [[0.0 for _ in range(11)] for _ in range(11)]
    matrix[1][0] = 1.0
    snapshots = [
        {
            "id": 1,
            "match_id": "m1",
            "play_type": "had",
            "goal_line": None,
            "odds": {"3": 2.0},
        }
    ]

    [candidate] = ev_candidates(snapshots, {"3": 0.60, "1": 0.20, "0": 0.20}, matrix)

    assert candidate["ev"] > 0.15
    assert candidate["research_only"] is True
    assert candidate["suggestion_eligible"] is False


def test_had_hhad_positive_calibrated_ev_is_suggestion_eligible():
    assert suggestion_eligible_for_signal("had", 0.10, False) is True
    assert suggestion_eligible_for_signal("hhad", 0.15, False) is True
    assert suggestion_eligible_for_signal("had", 0.0, False) is False
    assert suggestion_eligible_for_signal("had", 0.10, True) is False


def test_non_had_hhad_candidate_can_exist_but_is_not_suggestion_eligible():
    matrix = [[0.0 for _ in range(11)] for _ in range(11)]
    matrix[0][0] = 1.0
    snapshots = [
        {
            "id": 2,
            "match_id": "m1",
            "play_type": "ttg",
            "goal_line": None,
            "odds": {"0": 1.10},
        }
    ]

    [candidate] = ev_candidates(snapshots, {"3": 0.60, "1": 0.20, "0": 0.20}, matrix)

    assert candidate["play_type"] == "ttg"
    assert 0 < candidate["ev"] <= 0.15
    assert candidate["research_only"] is False
    assert candidate["suggestion_eligible"] is False
