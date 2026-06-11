from decimal import Decimal

import pytest

from api.production_safety import assert_test_match_id
from api.settlement_smoke import cleanup, run_smoke_on_repository


class FakeSmokeRepository:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.username = "codex_blocker_20260101000000"
        self.users = {self.username: Decimal("9970")}
        self.matches = {
            prefix: {"match_id": prefix, "status": "finished", "result_home": 2, "result_away": 1, "ht_home": 1, "ht_away": 0},
            f"{prefix}-void": {"match_id": f"{prefix}-void", "status": "postponed", "result_home": None, "result_away": None, "ht_home": None, "ht_away": None},
            "500-real": {"match_id": "500-real", "status": "finished", "result_home": 9, "result_away": 9, "ht_home": 0, "ht_away": 0},
        }
        self.bets = [
            _bet(1, self.username, "single_win", [{"match_id": prefix, "play_type": "had", "selection": "3", "odds": "2.00"}]),
            _bet(2, self.username, "single_loss", [{"match_id": prefix, "play_type": "had", "selection": "0", "odds": "2.00"}]),
            _bet(
                3,
                self.username,
                "parlay_void_win",
                [
                    {"match_id": prefix, "play_type": "had", "selection": "3", "odds": "2.00"},
                    {"match_id": f"{prefix}-void", "play_type": "had", "selection": "3", "odds": "3.00"},
                ],
                parlay="2x1",
            ),
        ]

    def open_bets(self):
        return [bet for bet in self.bets if bet["status"] == "open" and self.prefix in str(bet["legs"])]

    def match_rows(self, match_ids):
        rows = {}
        for match_id in match_ids:
            assert_test_match_id(match_id)
            assert match_id.startswith(self.prefix)
            rows[match_id] = self.matches[match_id]
        return rows

    def apply_settlement(self, bet_id, status, payout):
        bet = next(item for item in self.bets if item["id"] == bet_id)
        if bet["status"] != "open":
            return False
        bet["status"] = status
        bet["payout"] = Decimal(str(payout))
        if payout > 0:
            self.users[bet["user_id"]] += Decimal(str(payout))
        return True

    def user_balance(self, username):
        return self.users[username]

    def bet_snapshot(self, prefix):
        return [
            {"id": bet["id"], "label": bet["legs"][0]["label"], "status": bet["status"], "payout": bet["payout"]}
            for bet in self.bets
            if prefix in str(bet["legs"])
        ]


def test_assert_test_match_id_rejects_real_500_and_real_match_num():
    with pytest.raises(ValueError):
        assert_test_match_id("500-xxx")
    with pytest.raises(ValueError):
        assert_test_match_id("test-settlement-xxx", "周四001")


def test_assert_test_match_id_accepts_test_settlement_prefix():
    assert_test_match_id("test-settlement-xxx")


def test_cleanup_rejects_empty_prefix():
    with pytest.raises(ValueError):
        cleanup("")


def test_smoke_run_only_uses_test_prefix_and_is_idempotent():
    prefix = "test-settlement-20260101000000"
    repo = FakeSmokeRepository(prefix)

    report = run_smoke_on_repository(prefix, repo.username, repo, Decimal("9970"))

    assert report.passed is True
    assert all(match_id.startswith("test-") or match_id == "500-real" for match_id in repo.matches)
    assert repo.matches["500-real"]["result_home"] == 9
    assert report.second_run_changed_balance is False
    assert report.second_run_changed_bets is False


def test_smoke_void_leg_uses_odds_as_one():
    prefix = "test-settlement-20260101000000"
    repo = FakeSmokeRepository(prefix)

    report = run_smoke_on_repository(prefix, repo.username, repo, Decimal("9970"))

    payouts = {row["label"]: row["payout"] for row in report.second_bet_snapshot}
    assert payouts["parlay_void_win"] == Decimal("20.00")
    assert report.after_first_run_balance == Decimal("10010.00")


def _bet(bet_id, username, label, legs, parlay="single"):
    return {
        "id": bet_id,
        "user_id": username,
        "legs": [{**leg, "label": label} for leg in legs],
        "parlay": parlay,
        "stake": Decimal("10"),
        "status": "open",
        "payout": None,
    }
