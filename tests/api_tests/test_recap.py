from fastapi.testclient import TestClient

from api import recap
from api.main import app


def test_random_baseline_stub_is_deterministic():
    assert recap.compute_random_baseline_stub(2026) == recap.compute_random_baseline_stub(2026)


def test_calibration_curve_insufficient_finished_matches(monkeypatch):
    monkeypatch.setattr(recap, "_finished_matches_count", lambda: 3)

    result = recap.calibration_curve_from_finished_matches()

    assert result["status"] == "insufficient_finished_matches"
    assert result["message"] == "完赛场次不足，复盘将在小组赛进行后生成。"


def test_recap_api_returns_insufficient_placeholders(monkeypatch):
    monkeypatch.setattr(recap, "_finished_matches_count", lambda: 3)
    client = TestClient(app)

    for path in ("/api/recap/status", "/api/recap/calibration", "/api/recap/funds", "/api/recap/plays"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json()["status"] == "insufficient_finished_matches"
