from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.db import get_db
from api.main import app


class AnalyticsFakeDb:
    def __init__(self) -> None:
        self.matches = {
            "scheduled": {
                "match_id": "scheduled",
                "home_team": "Mexico",
                "away_team": "South Africa",
                "kickoff_at": datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
                "status": "scheduled",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            }
        }

    def get_match(self, match_id: str):
        return self.matches.get(match_id)

    def prediction_history(self, match_id: str):
        if match_id != "scheduled":
            return []
        return [
            {
                "created_at": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
                "model_version": 7,
                "model_version_name": "p1b-dixon-coles-predict-run",
                "p_home": 0.62,
                "p_draw": 0.23,
                "p_away": 0.15,
            }
        ]


def test_prediction_history_endpoint_returns_points() -> None:
    fake = AnalyticsFakeDb()
    app.dependency_overrides[get_db] = lambda: fake
    try:
        response = TestClient(app).get("/api/matches/scheduled/prediction-history")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data_status"] == "ok"
    assert body["points"][0]["model_version_name"] == "p1b-dixon-coles-predict-run"
    assert body["points"][0]["p_home"] == 0.62


def test_team_form_endpoint_returns_insufficient_data_when_local_history_missing(monkeypatch) -> None:
    fake = AnalyticsFakeDb()
    monkeypatch.setattr("api.main._history_results_path", lambda: None)
    app.dependency_overrides[get_db] = lambda: fake
    try:
        response = TestClient(app).get("/api/matches/scheduled/team-form")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data_status"] == "insufficient_data"
    assert body["home_form"] == []
    assert body["away_form"] == []
