from __future__ import annotations

from decimal import Decimal

from api.settlement_runner import settle_bet_if_ready


def test_finished_without_score_is_not_ready_for_settlement() -> None:
    bet = {
        "id": 1,
        "user_id": 1,
        "legs": [{"match_id": "m1", "play_type": "had", "selection": "3", "odds": "2.00"}],
        "stake": Decimal("10"),
    }

    result = settle_bet_if_ready(
        bet,
        {"m1": {"match_id": "m1", "status": "finished", "result_home": None, "result_away": None}},
    )

    assert result is None

