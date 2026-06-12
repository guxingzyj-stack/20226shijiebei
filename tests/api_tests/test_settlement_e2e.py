from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from api.settlement_runner import run_settlement


class InMemorySettlementRepository:
    def __init__(self) -> None:
        self.username = "test_user_settlement_e2e"
        self.users = {self.username: {"balance": Decimal("9950")}}
        self.matches: dict[str, dict[str, Any]] = {
            "test-settlement-e2e-win": _match("test-settlement-e2e-win", "finished", 2, 1, 1, 0),
            "test-settlement-e2e-loss": _match("test-settlement-e2e-loss", "finished", 0, 2, 0, 1),
            "test-settlement-e2e-postponed": _match("test-settlement-e2e-postponed", "postponed"),
            "test-settlement-e2e-closed": _match("test-settlement-e2e-closed", "closed"),
            "test-settlement-e2e-finished-null": _match("test-settlement-e2e-finished-null", "finished"),
        }
        self.bets: list[dict[str, Any]] = [
            _bet(1, self.username, "winning_single", [{"match_id": "test-settlement-e2e-win", "play_type": "had", "selection": "3", "odds": "2.00"}]),
            _bet(2, self.username, "losing_single", [{"match_id": "test-settlement-e2e-loss", "play_type": "had", "selection": "3", "odds": "2.00"}]),
            _bet(
                3,
                self.username,
                "void_leg_parlay",
                [
                    {"match_id": "test-settlement-e2e-win", "play_type": "had", "selection": "3", "odds": "2.00"},
                    {"match_id": "test-settlement-e2e-postponed", "play_type": "had", "selection": "3", "odds": "3.00"},
                ],
                parlay="2x1",
            ),
            _bet(4, self.username, "closed_not_ready", [{"match_id": "test-settlement-e2e-closed", "play_type": "had", "selection": "3", "odds": "2.00"}]),
            _bet(5, self.username, "finished_null_guard", [{"match_id": "test-settlement-e2e-finished-null", "play_type": "had", "selection": "3", "odds": "2.00"}]),
        ]

    def open_bets(self) -> list[dict[str, Any]]:
        return [bet for bet in self.bets if bet["status"] == "open"]

    def match_rows(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {match_id: self.matches[match_id] for match_id in match_ids}

    def apply_settlement(self, bet_id: int, status: str, payout: Decimal) -> bool:
        bet = next(item for item in self.bets if item["id"] == bet_id)
        if bet["status"] != "open":
            return False
        bet["status"] = status
        bet["payout"] = Decimal(str(payout))
        bet["settled_at"] = "test-clock"
        if payout > 0:
            self.users[bet["user_id"]]["balance"] += Decimal(str(payout))
        return True

    def balance(self) -> Decimal:
        return self.users[self.username]["balance"]

    def leaderboard(self) -> list[dict[str, Any]]:
        settled = [bet for bet in self.bets if bet["status"] in {"won", "lost", "void"}]
        settled_stake = sum((Decimal(str(bet["stake"])) for bet in settled), Decimal("0"))
        settled_payout = sum((Decimal(str(bet["payout"] or 0)) for bet in settled), Decimal("0"))
        roi = Decimal("0") if settled_stake == 0 else (settled_payout - settled_stake) / settled_stake
        return [
            {
                "username": self.username,
                "balance": self.balance(),
                "roi": roi,
                "settled_bets": len(settled),
            }
        ]

    def bet_by_label(self, label: str) -> dict[str, Any]:
        return next(bet for bet in self.bets if bet["label"] == label)


def test_settlement_e2e_won_lost_void_not_ready_and_idempotent():
    repo = InMemorySettlementRepository()
    initial_balance = repo.balance()

    first = run_settlement(repo)

    assert first.open_bets_seen == 5
    assert first.settled_won == 2
    assert first.settled_lost == 1
    assert first.settled_void == 0
    assert first.skipped_not_ready == 2
    assert first.errors == 0
    assert repo.bet_by_label("winning_single")["status"] == "won"
    assert repo.bet_by_label("winning_single")["payout"] == Decimal("20.00")
    assert repo.bet_by_label("losing_single")["status"] == "lost"
    assert repo.bet_by_label("losing_single")["payout"] == Decimal("0")
    assert repo.bet_by_label("void_leg_parlay")["status"] == "won"
    assert repo.bet_by_label("void_leg_parlay")["payout"] == Decimal("20.00")
    assert repo.bet_by_label("closed_not_ready")["status"] == "open"
    assert repo.bet_by_label("finished_null_guard")["status"] == "open"
    assert repo.balance() == initial_balance + Decimal("40.00")

    first_snapshot = deepcopy(repo.bets)
    balance_after_first = repo.balance()
    second = run_settlement(repo)

    assert second.open_bets_seen == 2
    assert second.settled_won == 0
    assert second.settled_lost == 0
    assert second.skipped_not_ready == 2
    assert second.errors == 0
    assert repo.balance() == balance_after_first
    assert repo.bets == first_snapshot

    leaderboard = repo.leaderboard()[0]
    assert "roi" in leaderboard
    assert "id" not in leaderboard
    assert "user_id" not in leaderboard
    assert leaderboard["settled_bets"] == 3


def _match(
    match_id: str,
    status: str,
    result_home: int | None = None,
    result_away: int | None = None,
    ht_home: int | None = None,
    ht_away: int | None = None,
) -> dict[str, Any]:
    return {
        "match_id": match_id,
        "status": status,
        "result_home": result_home,
        "result_away": result_away,
        "ht_home": ht_home,
        "ht_away": ht_away,
    }


def _bet(bet_id: int, username: str, label: str, legs: list[dict[str, str]], parlay: str = "single") -> dict[str, Any]:
    return {
        "id": bet_id,
        "user_id": username,
        "label": label,
        "legs": legs,
        "parlay": parlay,
        "stake": Decimal("10"),
        "status": "open",
        "payout": None,
        "settled_at": None,
    }
