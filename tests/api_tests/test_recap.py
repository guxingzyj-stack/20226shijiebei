from api import recap


def test_random_baseline_stub_is_deterministic():
    assert recap.compute_random_baseline_stub(2026) == recap.compute_random_baseline_stub(2026)


def test_calibration_curve_insufficient_finished_matches(monkeypatch):
    monkeypatch.setattr(recap, "_finished_matches_count", lambda: 3)

    result = recap.calibration_curve_from_finished_matches()

    assert result["status"] == "insufficient_finished_matches"
    assert "完赛场次不足" in result["message"]
