from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api import recap_service


class FakeRecapRepo:
    def __init__(self):
        self.kickoff = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
        self.matches = {
            "finished": {
                "match_id": "finished",
                "match_num": "001",
                "league": "World Cup",
                "home_team": "Mexico",
                "away_team": "South Africa",
                "kickoff_at": self.kickoff,
                "status": "finished",
                "result_home": 2,
                "result_away": 0,
                "ht_home": 1,
                "ht_away": 0,
            },
            "scheduled": {
                "match_id": "scheduled",
                "match_num": "002",
                "league": "World Cup",
                "home_team": "A",
                "away_team": "B",
                "kickoff_at": self.kickoff,
                "status": "scheduled",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            },
            "finished_null": {
                "match_id": "finished_null",
                "match_num": "003",
                "league": "World Cup",
                "home_team": "A",
                "away_team": "B",
                "kickoff_at": self.kickoff,
                "status": "finished",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            },
        }
        self.prediction = {
            "match_id": "finished",
            "model_version": 7,
            "p_home": 0.62,
            "p_draw": 0.23,
            "p_away": 0.15,
            "created_at": self.kickoff - timedelta(hours=1),
        }
        self.post_prediction = {
            "match_id": "finished",
            "model_version": 8,
            "p_home": 0.1,
            "p_draw": 0.2,
            "p_away": 0.7,
            "created_at": self.kickoff + timedelta(hours=1),
        }
        self.script_rows = [
            {
                "id": 1,
                "grp": "A",
                "stage": "group",
                "home_team": "Mexico",
                "away_team": "South Africa",
                "script_home": 2,
                "script_away": 0,
                "narrative": "known result sample",
                "is_real": True,
            }
        ]

    def match(self, match_id):
        return self.matches.get(match_id)

    def had_odds(self, match_id):
        return [
            {"odds": {"3": 1.8, "1": 3.2, "0": 4.5}, "fetched_at": self.kickoff - timedelta(days=1)},
            {"odds": {"3": 1.5, "1": 3.6, "0": 6.0}, "fetched_at": self.kickoff - timedelta(minutes=10)},
        ]

    def pre_kickoff_prediction(self, match_id, kickoff_at):
        return self.prediction if self.prediction and self.prediction["created_at"] <= kickoff_at else None

    def ev_signals(self, match_id):
        return [
            {"match_id": match_id, "model_version": 7, "play_type": "had", "selection": "3", "model_prob": 0.62, "odds": 1.5, "ev": 0.02, "research_only": False, "suggestion_eligible": True, "reason": None},
            {"match_id": match_id, "model_version": 7, "play_type": "had", "selection": "0", "model_prob": 0.15, "odds": 6.0, "ev": 0.30, "research_only": True, "suggestion_eligible": False, "reason": "model_market_divergence_too_large"},
        ]

    def settlement_summary(self, match_id):
        return {"settled_bets": 2, "won_bets": 1, "lost_bets": 1, "void_bets": 0, "open_bets": 0}

    def cumulative_vig_summary(self, match_id=None):
        return {
            "bet_count": 2,
            "total_virtual_stake": 20.0,
            "cumulative_vig": 0.12,
            "cumulative_vig_points": 2.4,
        }

    def finished_matches(self, limit):
        return [self.matches["finished"]][:limit]

    def script_predictions(self):
        return self.script_rows


def test_unfinished_match_returns_unavailable():
    result = recap_service.build_match_recap("scheduled", FakeRecapRepo())

    assert result == {"available": False, "reason": "match_not_finished_or_result_missing"}


def test_finished_missing_result_returns_unavailable():
    result = recap_service.build_match_recap("finished_null", FakeRecapRepo())

    assert result == {"available": False, "reason": "match_not_finished_or_result_missing"}


def test_finished_result_generates_recap_with_market_model_ev_and_settlement():
    result = recap_service.build_match_recap("finished", FakeRecapRepo())

    assert result["available"] is True
    recap = result["recap"]
    assert recap["result"]["winner"] == "home"
    assert recap["market"]["favorite"] == "home"
    assert abs(sum(recap["market"]["close_implied_probabilities"].values()) - 1.0) < 1e-9
    assert recap["model"]["model_version"] == 7
    assert recap["model"]["predicted_outcome"] == "home"
    assert recap["model"]["prediction_correct"] is True
    assert recap["ev"]["hit_count"] == 1
    assert recap["ev"]["miss_count"] == 1
    assert recap["ev"]["research_only_count"] == 1
    assert recap["ev"]["signals"][1]["recommendation_label"] == "research_signal"
    assert recap["settlement"]["settled_bets"] == 2
    assert recap["settlement"]["cumulative_vig"]["cumulative_vig_points"] == 2.4
    assert "user_id" not in recap["settlement"]
    assert recap["summary"]["title_cn"]
    assert recap["script"]["has_script"] is True
    assert recap["script"]["script_score"] == "2:0"
    assert recap["script"]["group"] == "A"
    assert recap["script"]["stage"] == "group"
    assert recap["script"]["is_real"] is True
    assert recap["script"]["direction_hit"] is None
    assert recap["script"]["exact_hit"] is None
    assert recap["three_way_summary"]["market_hit"] is True
    assert recap["three_way_summary"]["model_hit"] is True


def test_post_kickoff_prediction_is_not_used():
    repo = FakeRecapRepo()
    repo.prediction = repo.post_prediction

    result = recap_service.build_match_recap("finished", repo)

    assert result["recap"]["model"]["model_version"] is None
    assert result["recap"]["data_quality"]["has_prediction"] is False


def test_missing_prediction_still_generates_recap():
    repo = FakeRecapRepo()
    repo.prediction = None

    result = recap_service.build_match_recap("finished", repo)

    assert result["available"] is True
    assert result["recap"]["model"]["prediction_correct"] is None


def test_script_projection_reports_hits_for_non_real_script():
    repo = FakeRecapRepo()
    repo.script_rows = [
        {
            "id": 2,
            "grp": "A",
            "stage": "group",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "script_home": 1,
            "script_away": 0,
            "narrative": "script projection",
            "is_real": False,
        }
    ]

    result = recap_service.build_match_recap("finished", repo)

    script = result["recap"]["script"]
    assert script["has_script"] is True
    assert script["is_real"] is False
    assert script["direction_hit"] is True
    assert script["exact_hit"] is False


def test_no_script_returns_empty_script_section():
    repo = FakeRecapRepo()
    repo.script_rows = []

    result = recap_service.build_match_recap("finished", repo)

    assert result["recap"]["script"] == {"has_script": False}


def test_recent_and_summary_only_use_finished_matches():
    repo = FakeRecapRepo()

    recent = recap_service.recent_recaps(repository=repo)
    summary = recap_service.recap_summary(repository=repo)

    assert recent["count"] == 1
    assert recent["items"][0]["match_id"] == "finished"
    assert summary["finished_matches"] == 1
    assert summary["model_correct_count"] == 1
    assert summary["ev_signal_count"] == 2
    assert summary["settled_bets"] == 2
    assert summary["cumulative_vig"]["bet_count"] == 2


def test_cumulative_vig_returns_zero_without_bets():
    assert recap_service._cumulative_vig_from_bets([], {}) == {
        "bet_count": 0,
        "total_virtual_stake": 0.0,
        "cumulative_vig": 0.0,
        "cumulative_vig_points": 0.0,
    }


def test_cumulative_vig_uses_stake_times_snapshot_vig():
    rows = [
        {"stake": "10", "legs": [{"play_type": "had", "snapshot_id": 1}]},
        {"stake": "20", "legs": [{"play_type": "had", "snapshot_id": 2}]},
    ]
    odds_by_snapshot = {
        1: {"3": 2.0, "1": 3.0, "0": 4.0},
        2: {"3": 1.8, "1": 3.2, "0": 5.0},
    }

    summary = recap_service._cumulative_vig_from_bets(rows, odds_by_snapshot)

    expected_points = (
        10 * recap_service.calculate_had_vig(odds_by_snapshot[1])["vig"]
        + 20 * recap_service.calculate_had_vig(odds_by_snapshot[2])["vig"]
    )
    assert summary["bet_count"] == 2
    assert summary["total_virtual_stake"] == 30.0
    assert abs(summary["cumulative_vig_points"] - expected_points) < 1e-9
