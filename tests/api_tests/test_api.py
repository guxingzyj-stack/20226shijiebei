from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from api.auth import hash_password
from api.betting import BETTING_DISABLED_MESSAGE
from api.db import _mark_research_only, get_db
from api.main import app, get_current_user


class FakeDb:
    def __init__(self):
        self.users = {}
        self.users_by_name = {}
        self.next_user_id = 1
        self.bets = []
        self.matches = {
            "m1": {
                "match_id": "m1",
                "home_team": "A",
                "away_team": "B",
                "kickoff_at": datetime.now(timezone.utc) + timedelta(hours=2),
                "status": "scheduled",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            }
        }
        self.snapshots = {
            ("m1", "had"): {"id": 10, "match_id": "m1", "play_type": "had", "goal_line": None, "odds": {"3": 2.0, "1": 3.0, "0": 4.0}}
        }
        self.ev_signal = {"match_id": "m1", "play_type": "had", "selection": "3", "model_prob": 0.60, "odds": 2.20, "ev": 0.32, "suggestion_eligible": False}
        self.prediction = {
            "id": 1,
            "match_id": "m1",
            "model_version": 1,
            "p_home": 0.5,
            "p_draw": 0.3,
            "p_away": 0.2,
            "score_matrix": [[0.1]],
            "lambda_home": 1.2,
            "lambda_away": 0.8,
        }

    def create_user(self, username, password_hash):
        user = {"id": self.next_user_id, "username": username, "password_hash": password_hash, "balance": Decimal("10000")}
        self.next_user_id += 1
        self.users[user["id"]] = user
        self.users_by_name[username] = user
        return user

    def get_user_by_username(self, username):
        return self.users_by_name.get(username)

    def get_user_by_id(self, user_id):
        return self.users.get(user_id)

    def list_matches(self, status="upcoming"):
        return list(self.matches.values())

    def get_match(self, match_id):
        return self.matches.get(match_id)

    def odds_history(self, match_id, play_type=None):
        rows = []
        for (mid, ptype), snapshot in self.snapshots.items():
            if mid == match_id and (play_type is None or ptype == play_type):
                rows.append(snapshot)
        return rows

    def latest_odds_by_match(self, match_id):
        return [snapshot for (mid, _), snapshot in self.snapshots.items() if mid == match_id]

    def latest_prediction(self, match_id):
        return self.prediction if match_id == "m1" else None

    def latest_ev_signals(self, match_id, limit=20):
        return _mark_research_only([dict(self.ev_signal)]) if match_id == "m1" else []

    def latest_odds(self, match_id, play_type):
        return self.snapshots.get((match_id, play_type))

    def create_bet(self, user_id, legs, parlay, stake, potential_payout):
        user = self.users[user_id]
        if user["balance"] < stake:
            raise ValueError("insufficient balance")
        user["balance"] -= stake
        bet = {
            "id": len(self.bets) + 1,
            "legs": legs,
            "parlay": parlay,
            "stake": stake,
            "potential_payout": potential_payout,
            "status": "open",
            "balance": user["balance"],
        }
        self.bets.append(bet)
        return bet

    def list_user_bets(self, user_id):
        return self.bets

    def leaderboard(self):
        return [
            {"username": user["username"], "balance": user["balance"], "roi": 0, "settled_bets": 0}
            for user in sorted(self.users.values(), key=lambda item: item["balance"], reverse=True)
        ]

    def best_ev_signal(self, match_id):
        if match_id != "m1":
            return None
        return (
            self.ev_signal
            if self.ev_signal.get("suggestion_eligible", False)
            and self.ev_signal["play_type"] in {"had", "hhad"}
            and self.ev_signal["ev"] > 0
            and self.ev_signal["ev"] <= 0.15
            and not self.ev_signal.get("research_only", False)
            else None
        )

    def legacy_best_ev_signal_without_suggestion_flag(self, match_id):
        if match_id != "m1":
            return None
        return (
            self.ev_signal
            if self.ev_signal["play_type"] in {"had", "hhad"}
            and self.ev_signal["ev"] <= 0.15
            and not self.ev_signal.get("research_only", False)
            else None
        )


def test_register_and_login_return_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    fake = FakeDb()
    app.dependency_overrides[get_db] = lambda: fake
    try:
        client = TestClient(app)
        registered = client.post("/api/auth/register", json={"username": "alice", "password": "dummy-test-passphrase"})
        assert registered.status_code == 200
        assert registered.json()["access_token"]

        logged_in = client.post("/api/auth/login", json={"username": "alice", "password": "dummy-test-passphrase"})
        assert logged_in.status_code == 200
        assert logged_in.json()["access_token"]
    finally:
        app.dependency_overrides.clear()


def test_bet_placement_uses_server_odds_not_client_odds(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("BETTING_ENABLED", "true")
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": hash_password("dummy-test-passphrase"), "balance": Decimal("100")}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.post(
            "/api/bets",
            json={"parlay": "single", "stake": "10", "legs": [{"match_id": "m1", "play_type": "had", "selection": "3", "odds": "99"}]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["legs"][0]["odds"] == "2.0"
        assert body["potential_payout"] == "20.0"
        assert body["balance"] == "90"
    finally:
        app.dependency_overrides.clear()


def test_bet_placement_rejects_when_betting_disabled(monkeypatch):
    monkeypatch.delenv("BETTING_ENABLED", raising=False)
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": hash_password("dummy-test-passphrase"), "balance": Decimal("100")}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.post(
            "/api/bets",
            json={"parlay": "single", "stake": "10", "legs": [{"match_id": "m1", "play_type": "had", "selection": "3"}]},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == BETTING_DISABLED_MESSAGE
        assert fake.bets == []
        assert fake.users[1]["balance"] == Decimal("100")
    finally:
        app.dependency_overrides.clear()


def test_betting_disabled_preempts_fake_match_id_without_writing_bet(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "false")
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": hash_password("dummy-test-passphrase"), "balance": Decimal("100")}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.post(
            "/api/bets",
            json={"parlay": "single", "stake": "10", "legs": [{"match_id": "__missing_match__", "play_type": "had", "selection": "3"}]},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == BETTING_DISABLED_MESSAGE
        assert fake.bets == []
        assert fake.users[1]["balance"] == Decimal("100")
    finally:
        app.dependency_overrides.clear()


def test_match_detail_includes_smoke_fields(monkeypatch):
    fake = FakeDb()
    app.dependency_overrides[get_db] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/matches/m1")
        assert response.status_code == 200
        body = response.json()
        assert body["latest_odds"]
        assert body["latest_prediction"]["match_id"] == "m1"
        assert "result_home" in body
        assert "result_away" in body
        assert "ht_home" in body
        assert "ht_away" in body
        assert "score_matrix" not in body
        assert body["latest_prediction"]["score_matrix"] == [[0.1]]
        assert body["prediction_status"]["available"] is True
        assert body["ev_signals"][0]["selection"] == "3"
        assert body["ev_signals"][0]["research_only"] is True
    finally:
        app.dependency_overrides.clear()


def test_match_detail_finished_missing_result_returns_warning(monkeypatch):
    fake = FakeDb()
    fake.matches["m1"]["status"] = "finished"
    fake.matches["m1"]["result_home"] = None
    fake.matches["m1"]["result_away"] = None
    app.dependency_overrides[get_db] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/matches/m1")
        assert response.status_code == 200
        body = response.json()
        assert body["prediction_status"]["reason"] == "finished_missing_result"
        assert body["prediction_status"]["message"] == "已标记完赛，但赛果尚未回填"
    finally:
        app.dependency_overrides.clear()


def test_health_returns_scheduler_fields(monkeypatch):
    monkeypatch.setattr(
        "api.main.scheduler_freshness",
        lambda: {"scheduler_last_seen": "2026-06-12T00:00:00+00:00", "scheduler_last_seen_age_minutes": 12, "scheduler_stale": False},
    )
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "scheduler_last_seen": "2026-06-12T00:00:00+00:00",
        "scheduler_last_seen_age_minutes": 12,
        "scheduler_stale": False,
    }


def test_match_detail_without_current_prediction_returns_status(monkeypatch):
    fake = FakeDb()
    fake.prediction = None
    app.dependency_overrides[get_db] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/matches/m1")
        assert response.status_code == 200
        body = response.json()
        assert body["latest_prediction"] is None
        assert body["prediction_status"]["available"] is False
        assert body["prediction_status"]["reason"] == "missing_current_market_odds"
        assert "score_matrix" not in body
        assert body["ev_signals"] == []
    finally:
        app.dependency_overrides.clear()


def test_bet_placement_rejects_inside_five_minutes(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "true")
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("100")}
    fake.matches["m1"]["kickoff_at"] = datetime.now(timezone.utc) + timedelta(minutes=4)
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.post(
            "/api/bets",
            json={"parlay": "single", "stake": "10", "legs": [{"match_id": "m1", "play_type": "had", "selection": "3"}]},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "betting closed"
    finally:
        app.dependency_overrides.clear()


def test_bet_placement_rejects_insufficient_balance(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "true")
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("5")}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.post(
            "/api/bets",
            json={"parlay": "single", "stake": "10", "legs": [{"match_id": "m1", "play_type": "had", "selection": "3"}]},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "insufficient balance"
    finally:
        app.dependency_overrides.clear()


def test_model_suggestion_caps_kelly_at_five_percent(monkeypatch):
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("1000")}
    fake.ev_signal = {"match_id": "m1", "play_type": "had", "selection": "3", "model_prob": 0.76, "odds": 1.50, "ev": 0.14, "suggestion_eligible": True}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.get("/api/model/suggestion?match_id=m1")
        assert response.status_code == 200
        assert response.json()["suggested_stake"] == "50.00"
    finally:
        app.dependency_overrides.clear()


def test_model_suggestion_filters_research_only_and_non_had_hhad(monkeypatch):
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("1000")}
    fake.ev_signal = {"match_id": "m1", "play_type": "crs", "selection": "1:0", "model_prob": 0.20, "odds": 9.0, "ev": 0.80, "suggestion_eligible": False}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    try:
        client = TestClient(app)
        response = client.get("/api/model/suggestion?match_id=m1")
        assert response.status_code == 200
        body = response.json()
        assert body["suggested_stake"] == "0"
        assert body["reason"] == "no_calibrated_value_signal"
    finally:
        app.dependency_overrides.clear()


def test_model_suggestion_ignores_ttg_hafu_and_research_only_had(monkeypatch):
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("1000")}
    app.dependency_overrides[get_db] = lambda: fake
    app.dependency_overrides[get_current_user] = lambda: fake.users[1]
    client = TestClient(app)
    try:
        for play_type in ("ttg", "hafu"):
            fake.ev_signal = {"match_id": "m1", "play_type": play_type, "selection": "7", "model_prob": 0.20, "odds": 1.5, "ev": 0.10, "suggestion_eligible": False}
            response = client.get("/api/model/suggestion?match_id=m1")
            assert response.status_code == 200
            assert response.json()["reason"] == "no_calibrated_value_signal"

        fake.ev_signal = {
            "match_id": "m1",
            "play_type": "had",
            "selection": "3",
            "model_prob": 0.70,
            "odds": 1.4,
            "ev": 0.10,
            "research_only": True,
            "suggestion_eligible": False,
        }
        response = client.get("/api/model/suggestion?match_id=m1")
        assert response.status_code == 200
        assert response.json()["reason"] == "no_calibrated_value_signal"
    finally:
        app.dependency_overrides.clear()


def test_leaderboard_does_not_expose_internal_id(monkeypatch):
    fake = FakeDb()
    fake.users[1] = {"id": 1, "username": "bob", "password_hash": "x", "balance": Decimal("1000")}
    app.dependency_overrides[get_db] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/leaderboard")
        assert response.status_code == 200
        body = response.json()
        assert body[0]["username"] == "bob"
        assert "id" not in body[0]
        assert "settled_bets" in body[0]
    finally:
        app.dependency_overrides.clear()
