from decimal import Decimal

from api.settlement_runner import run_settlement, settle_bet_if_ready


class FakeSettlementRepository:
    def __init__(self):
        self.users = {1: {"id": 1, "balance": Decimal("90")}}
        self.bets = [
            _bet(1, 1, Decimal("10"), [{"match_id": "m1", "play_type": "had", "selection": "3", "odds": "2.00"}]),
        ]
        self.matches = {
            "m1": {"match_id": "m1", "status": "finished", "result_home": 2, "result_away": 0, "ht_home": 1, "ht_away": 0}
        }

    def open_bets(self):
        return [bet for bet in self.bets if bet["status"] == "open"]

    def match_rows(self, match_ids):
        return {match_id: self.matches[match_id] for match_id in match_ids if match_id in self.matches}

    def apply_settlement(self, bet_id, status, payout):
        bet = next(item for item in self.bets if item["id"] == bet_id)
        if bet["status"] != "open":
            return False
        bet["status"] = status
        bet["payout"] = payout
        if payout > 0:
            self.users[bet["user_id"]]["balance"] += payout
        return True


def test_runner_settles_single_win_and_is_idempotent():
    repo = FakeSettlementRepository()

    stats = run_settlement(repo)

    assert stats.open_bets_seen == 1
    assert stats.settled_won == 1
    assert repo.bets[0]["status"] == "won"
    assert repo.bets[0]["payout"] == Decimal("20.00")
    assert repo.users[1]["balance"] == Decimal("110.00")

    second = run_settlement(repo)

    assert second.open_bets_seen == 0
    assert repo.users[1]["balance"] == Decimal("110.00")


def test_runner_settles_loss_without_payout():
    repo = FakeSettlementRepository()
    repo.bets[0]["legs"][0]["selection"] = "0"

    stats = run_settlement(repo)

    assert stats.settled_lost == 1
    assert repo.bets[0]["status"] == "lost"
    assert repo.bets[0]["payout"] == Decimal("0")
    assert repo.users[1]["balance"] == Decimal("90")


def test_runner_settles_parlay_all_win_and_one_loss():
    bet = _bet(
        2,
        1,
        Decimal("10"),
        [
            {"match_id": "m1", "play_type": "hhad", "selection": "1", "odds": "3.00", "goal_line": -1},
            {"match_id": "m2", "play_type": "ttg", "selection": "7", "odds": "4.00"},
        ],
    )
    rows = {
        "m1": {"status": "finished", "result_home": 2, "result_away": 1, "ht_home": 1, "ht_away": 0},
        "m2": {"status": "finished", "result_home": 4, "result_away": 3, "ht_home": 2, "ht_away": 1},
    }

    won = settle_bet_if_ready(bet, rows)

    assert won["status"] == "won"
    assert won["payout"] == Decimal("120.0000")

    rows["m2"]["result_home"] = 1
    rows["m2"]["result_away"] = 0
    lost = settle_bet_if_ready(bet, rows)

    assert lost["status"] == "lost"
    assert lost["payout"] == Decimal("0")


def test_runner_handles_crs_other_ttg_seven_plus_and_hafu_void():
    crs_other = _bet(3, 1, Decimal("10"), [{"match_id": "m3", "play_type": "crs", "selection": "胜其他", "odds": "8.00"}])
    ttg_seven = _bet(4, 1, Decimal("10"), [{"match_id": "m4", "play_type": "ttg", "selection": "7", "odds": "5.00"}])
    hafu_missing = _bet(5, 1, Decimal("10"), [{"match_id": "m5", "play_type": "hafu", "selection": "33", "odds": "6.00"}])
    rows = {
        "m3": {"status": "finished", "result_home": 6, "result_away": 0, "ht_home": 3, "ht_away": 0},
        "m4": {"status": "finished", "result_home": 4, "result_away": 3, "ht_home": 2, "ht_away": 1},
        "m5": {"status": "finished", "result_home": 2, "result_away": 0, "ht_home": None, "ht_away": None},
    }

    assert settle_bet_if_ready(crs_other, {"m3": rows["m3"]})["status"] == "won"
    assert settle_bet_if_ready(ttg_seven, {"m4": rows["m4"]})["status"] == "won"
    hafu = settle_bet_if_ready(hafu_missing, {"m5": rows["m5"]})
    assert hafu["status"] == "void"
    assert hafu["payout"] == Decimal("10")


def test_runner_skips_bet_when_match_result_not_ready():
    repo = FakeSettlementRepository()
    repo.matches["m1"]["status"] = "scheduled"
    repo.matches["m1"]["result_home"] = None
    repo.matches["m1"]["result_away"] = None

    stats = run_settlement(repo)

    assert stats.skipped_not_ready == 1
    assert repo.bets[0]["status"] == "open"
    assert repo.users[1]["balance"] == Decimal("90")


def test_runner_skips_finished_match_when_score_is_missing():
    repo = FakeSettlementRepository()
    repo.matches["m1"]["status"] = "finished"
    repo.matches["m1"]["result_home"] = None
    repo.matches["m1"]["result_away"] = None

    stats = run_settlement(repo)

    assert stats.skipped_not_ready == 1
    assert repo.bets[0]["status"] == "open"
    assert repo.users[1]["balance"] == Decimal("90")


def test_runner_voids_postponed_match_with_odds_as_one():
    repo = FakeSettlementRepository()
    repo.matches["m1"]["status"] = "postponed"
    repo.matches["m1"]["result_home"] = None
    repo.matches["m1"]["result_away"] = None

    stats = run_settlement(repo)

    assert stats.settled_void == 1
    assert repo.bets[0]["status"] == "void"
    assert repo.bets[0]["payout"] == Decimal("10")
    assert repo.users[1]["balance"] == Decimal("100")


def _bet(bet_id, user_id, stake, legs):
    return {
        "id": bet_id,
        "user_id": user_id,
        "legs": legs,
        "parlay": "single" if len(legs) == 1 else f"{len(legs)}x1",
        "stake": stake,
        "status": "open",
        "payout": None,
    }
