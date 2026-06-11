from __future__ import annotations

from api.main import _prediction_status


HAD_ODDS = [{"play_type": "had", "odds": {"3": 1.8, "1": 3.2, "0": 4.5}}]


def test_closed_with_had_odds_and_prediction_is_available() -> None:
    status = _prediction_status({"id": 1}, {"status": "closed", "latest_odds": HAD_ODDS})

    assert status["available"] is True
    assert status["reason"] is None


def test_closed_with_had_odds_without_prediction_is_pending_not_missing_market() -> None:
    status = _prediction_status(None, {"status": "closed", "latest_odds": HAD_ODDS})

    assert status["available"] is False
    assert status["reason"] == "prediction_pending"


def test_closed_without_had_odds_reports_missing_current_market() -> None:
    status = _prediction_status(None, {"status": "closed", "latest_odds": [{"play_type": "hhad", "odds": {"3": 2.0, "1": 3.0, "0": 4.0}}]})

    assert status["available"] is False
    assert status["reason"] == "missing_current_market_odds"


def test_scheduled_with_had_odds_without_prediction_is_pending() -> None:
    status = _prediction_status(None, {"status": "scheduled", "latest_odds": HAD_ODDS})

    assert status["available"] is False
    assert status["reason"] == "prediction_pending"


def test_finished_with_result_does_not_become_prediction_pending() -> None:
    status = _prediction_status(None, {"status": "finished", "result_home": 2, "result_away": 1, "latest_odds": HAD_ODDS})

    assert status["available"] is False
    assert status["reason"] is None
