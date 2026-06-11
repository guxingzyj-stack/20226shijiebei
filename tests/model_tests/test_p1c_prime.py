from __future__ import annotations

from datetime import datetime, timezone

from model import p1c_prime


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def match(match_id: str = "m1", status: str = "finished", result: tuple[int | None, int | None] = (1, 0), kickoff: str | None = "2026-06-12T10:00:00") -> p1c_prime.MatchRow:
    return p1c_prime.MatchRow(match_id, status, dt(kickoff) if kickoff else None, result[0], result[1])


def odds(match_id: str = "m1", play_type: str = "had", fetched: str = "2026-06-12T09:00:00", prices: dict[str, float] | None = None) -> p1c_prime.OddsRow:
    return p1c_prime.OddsRow(match_id, play_type, prices or {"3": 1.8, "1": 3.2, "0": 4.0}, dt(fetched))


def prediction(match_id: str = "m1", created: str | None = "2026-06-12T09:30:00", probs: tuple[float, float, float] = (0.55, 0.25, 0.20)) -> p1c_prime.PredictionRow:
    return p1c_prime.PredictionRow(match_id, 7, probs[0], probs[1], probs[2], dt(created) if created else None)


def test_latest_had_close_odds_uses_last_pre_kickoff_and_ignores_after() -> None:
    rows = [
        odds(fetched="2026-06-12T08:00:00", prices={"3": 2.0, "1": 3.0, "0": 4.0}),
        odds(fetched="2026-06-12T09:59:00", prices={"3": 1.8, "1": 3.2, "0": 4.0}),
        odds(fetched="2026-06-12T10:01:00", prices={"3": 1.1, "1": 9.9, "0": 9.9}),
    ]

    selected = p1c_prime._latest_pre_kickoff_had(rows, dt("2026-06-12T10:00:00"))

    assert selected is not None
    assert selected.odds["3"] == 1.8


def test_unfinished_match_is_skipped() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match(status="scheduled")], [], [], min_required_matches=1)

    assert report["skips"]["not_finished"] == 1
    assert report["result"] == "WAIT"


def test_missing_had_skip_and_hhad_not_used_as_had() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match()], [odds(play_type="hhad")], [prediction()], min_required_matches=1)

    assert report["skips"]["unsupported_hhad_only"] == 1
    assert report["skips"]["missing_had_market_odds"] == 0
    assert report["data_availability"]["evaluable_matches"] == 0
    assert report["result"] == "WAIT"


def test_missing_prediction_skip() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match()], [odds()], [], min_required_matches=1)

    assert report["skips"]["missing_prediction"] == 1
    assert report["result"] == "WAIT"


def test_prediction_after_kickoff_is_not_used() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match()], [odds()], [prediction(created="2026-06-12T10:01:00")], min_required_matches=1)

    assert report["skips"]["missing_prediction"] == 1
    assert report["data_availability"]["evaluable_matches"] == 0


def test_missing_prediction_created_at_sets_leakage_risk() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match()], [odds()], [prediction(created=None)], min_required_matches=1)

    assert report["leakage"]["leakage_risk"] is True
    assert report["result"] == "WAIT"
    assert report["blocker"] == "leakage_risk"


def test_sample_less_than_30_waits_with_partial_metrics() -> None:
    report = p1c_prime.build_prospective_calibration_summary([match()], [odds()], [prediction()], min_required_matches=30)

    assert report["data_availability"]["evaluable_matches"] == 1
    assert report["result"] == "WAIT"
    assert report["metrics"]["market_rps"] is None
    assert report["metrics"]["partial_metrics_available"] is True
    assert report["metrics"]["not_for_production_weight_change"] is True


def test_sample_at_threshold_outputs_metrics_and_best_weight() -> None:
    matches = [match(match_id=f"m{i}") for i in range(30)]
    odds_rows = [odds(match_id=f"m{i}") for i in range(30)]
    prediction_rows = [prediction(match_id=f"m{i}") for i in range(30)]

    report = p1c_prime.build_prospective_calibration_summary(matches, odds_rows, prediction_rows, min_required_matches=30)

    assert report["result"] == "PASS"
    assert report["metrics"]["market_rps"] is not None
    assert report["metrics"]["dc_rps"] is not None
    assert report["metrics"]["blended_rps"] is not None
    assert report["metrics"]["best_w_dc"] in p1c_prime.WEIGHT_GRID
    assert report["metrics"]["not_for_production_weight_change"] is True


def test_rps_calculation_known_value() -> None:
    assert p1c_prime._rps({"3": 1.0, "1": 0.0, "0": 0.0}, "3") == 0


def test_run_is_dry_run_and_does_not_write_db(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(p1c_prime, "status", lambda: {"result": "WAIT", "blocker": "x"})

    report = p1c_prime.run(dry_run=True)

    assert report["would_write_db"] is False
