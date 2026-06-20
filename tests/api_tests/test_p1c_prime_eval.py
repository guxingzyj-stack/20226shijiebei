from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api import p1c_prime_eval as eval_mod


def row(match_id: str = "m1", outcome: str = "3") -> eval_mod.EvalRow:
    result = {"3": (1, 0), "1": (1, 1), "0": (0, 1)}[outcome]
    return eval_mod.EvalRow(
        match_id=match_id,
        match_num="001",
        home_team="A",
        away_team="B",
        kickoff_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        result_home=result[0],
        result_away=result[1],
        actual_outcome=outcome,
        prediction_id=1,
        prediction_created_at=datetime(2026, 6, 12, 0, tzinfo=timezone.utc),
        model_version=7,
        dc={"3": 0.6, "1": 0.2, "0": 0.2},
        market={"3": 0.5, "1": 0.25, "0": 0.25},
    )


def test_brier_rps_logloss_known_values() -> None:
    probs = {"3": 1.0, "1": 0.0, "0": 0.0}

    assert eval_mod.brier_score(probs, "3") == pytest.approx(0.0)
    assert eval_mod.rps_score(probs, "3") == pytest.approx(0.0)
    assert eval_mod.logloss(probs, "3") == pytest.approx(0.0)


def test_blend_probs_normalizes_weighted_probabilities() -> None:
    blended = eval_mod.blend_probs(
        {"3": 0.8, "1": 0.1, "0": 0.1},
        {"3": 0.3, "1": 0.3, "0": 0.4},
        0.25,
    )

    assert sum(blended.values()) == pytest.approx(1.0)
    assert set(blended) == {"3", "1", "0"}


def test_evaluate_rows_outputs_required_schemes() -> None:
    report = eval_mod.evaluate_rows([row(f"m{i}") for i in range(3)])

    assert "market-only" in report["metrics"]
    assert "dc-only" in report["metrics"]
    assert "current 0.3/0.7" in report["metrics"]
    assert "candidate 0.5/0.5" in report["metrics"]
    assert report["calibration"]
    assert set(report["strata"]) == {"favorite", "balanced", "underdog"}


def test_recommendation_does_not_change_when_sample_less_than_30() -> None:
    evaluation = eval_mod.evaluate_rows([row("m1")])

    recommendation = eval_mod.recommend_weight(evaluation, sample_size=1)

    assert recommendation["choice"] == "C"
    assert recommendation["change_now"] is False


def test_render_markdown_says_no_production_weight_change() -> None:
    rows = [row(f"m{i}") for i in range(30)]
    evaluation = eval_mod.evaluate_rows(rows)
    report = {
        "sample": {
            "usable_finished_matches": 30,
            "included_matches": 30,
            "excluded_matches": {},
            "finished_missing_result": 0,
            "non_finished_with_result": 0,
            "p1c_ready": True,
        },
        "evaluation": evaluation,
        "recommendation": eval_mod.recommend_weight(evaluation, sample_size=30),
    }

    markdown = eval_mod.render_markdown(report)

    assert "不修改生产权重" in markdown
    assert "BETTING_ENABLED 继续保持 false" in markdown


def test_cli_requires_read_only_flag() -> None:
    with pytest.raises(SystemExit):
        eval_mod.main([])
