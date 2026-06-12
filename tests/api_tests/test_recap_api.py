from fastapi.testclient import TestClient

from api import main
from api.main import app


def test_match_recap_api(monkeypatch):
    monkeypatch.setattr(main, "build_match_recap", lambda match_id: {"available": True, "recap": {"match_id": match_id}})
    client = TestClient(app)

    response = client.get("/api/recaps/matches/500-1359172")

    assert response.status_code == 200
    assert response.json() == {"available": True, "recap": {"match_id": "500-1359172"}}


def test_match_recap_api_unavailable(monkeypatch):
    monkeypatch.setattr(main, "build_match_recap", lambda match_id: {"available": False, "reason": "match_not_finished_or_result_missing"})
    client = TestClient(app)

    response = client.get("/api/recaps/matches/500-1359172")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_recent_recaps_api(monkeypatch):
    monkeypatch.setattr(main, "recent_recaps", lambda limit=10: {"items": [{"match_id": "m1"}], "count": 1})
    client = TestClient(app)

    response = client.get("/api/recaps/recent?limit=5")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_recaps_summary_api(monkeypatch):
    monkeypatch.setattr(main, "build_recap_summary", lambda: {"finished_matches": 2, "recap_available_matches": 2})
    client = TestClient(app)

    response = client.get("/api/recaps/summary")

    assert response.status_code == 200
    assert response.json()["finished_matches"] == 2
