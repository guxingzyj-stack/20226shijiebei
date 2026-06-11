from __future__ import annotations

from fastapi.testclient import TestClient

from api.db import get_db
from api.main import app
from tests.api_tests.test_api import FakeDb


def test_match_detail_exposes_result_fields() -> None:
    fake = FakeDb()
    fake.matches["m1"].update({"status": "finished", "result_home": 2, "result_away": 1, "ht_home": 1, "ht_away": 0})
    app.dependency_overrides[get_db] = lambda: fake
    try:
        response = TestClient(app).get("/api/matches/m1")
        body = response.json()
        assert response.status_code == 200
        assert body["result_home"] == 2
        assert body["result_away"] == 1
        assert body["ht_home"] == 1
        assert body["ht_away"] == 0
        assert body["prediction_status"]["message"] == "已完赛"
    finally:
        app.dependency_overrides.clear()

