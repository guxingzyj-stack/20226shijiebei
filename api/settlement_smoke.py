from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import argparse
import sys
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.db import connect
from api.production_safety import TEST_SETTLEMENT_PREFIX, assert_test_match_id
from api.settlement_runner import SettlementStats, run_settlement


TEST_USER_PREFIX = "codex_blocker_"


@dataclass(frozen=True)
class SmokeReport:
    test_prefix: str
    test_user: str
    test_matches_created: int
    bets_created: int
    first_run: SettlementStats
    second_run: SettlementStats
    initial_balance: Decimal
    after_first_run_balance: Decimal
    after_second_run_balance: Decimal
    first_bet_snapshot: list[dict[str, Any]]
    second_bet_snapshot: list[dict[str, Any]]

    @property
    def second_run_changed_balance(self) -> bool:
        return self.after_first_run_balance != self.after_second_run_balance

    @property
    def second_run_changed_bets(self) -> bool:
        return self.first_bet_snapshot != self.second_bet_snapshot

    @property
    def passed(self) -> bool:
        statuses = {row["label"]: row["status"] for row in self.second_bet_snapshot}
        payouts = {row["label"]: Decimal(str(row["payout"])) for row in self.second_bet_snapshot}
        return (
            self.first_run.errors == 0
            and self.first_run.settled_won == 2
            and self.first_run.settled_lost == 1
            and self.first_run.settled_void == 0
            and self.first_run.skipped_not_ready == 0
            and not self.second_run_changed_balance
            and not self.second_run_changed_bets
            and statuses.get("single_win") == "won"
            and payouts.get("single_win") == Decimal("20.00")
            and statuses.get("single_loss") == "lost"
            and payouts.get("single_loss") == Decimal("0")
            and statuses.get("parlay_void_win") == "won"
            and payouts.get("parlay_void_win") == Decimal("20.00")
        )


def run_smoke(prefix: str | None = None) -> SmokeReport:
    test_prefix = prefix or _new_prefix()
    _assert_prefix(test_prefix)
    username = _username_from_prefix(test_prefix)
    with connect() as conn:
        _create_test_data(conn, test_prefix, username)
        initial_balance = _user_balance(conn, username)
    first_run = run_settlement(SmokeSettlementRepository(test_prefix), dry_run=False)
    with connect() as conn:
        after_first = _user_balance(conn, username)
        first_bets = _bet_snapshot(conn, test_prefix)
    second_run = run_settlement(SmokeSettlementRepository(test_prefix), dry_run=False)
    with connect() as conn:
        after_second = _user_balance(conn, username)
        second_bets = _bet_snapshot(conn, test_prefix)
    return SmokeReport(
        test_prefix=test_prefix,
        test_user=username,
        test_matches_created=2,
        bets_created=3,
        first_run=first_run,
        second_run=second_run,
        initial_balance=initial_balance,
        after_first_run_balance=after_first,
        after_second_run_balance=after_second,
        first_bet_snapshot=first_bets,
        second_bet_snapshot=second_bets,
    )


def run_smoke_on_repository(prefix: str, username: str, repository: Any, initial_balance: Decimal) -> SmokeReport:
    _assert_prefix(prefix)
    first_run = run_settlement(repository, dry_run=False)
    after_first = repository.user_balance(username)
    first_bets = repository.bet_snapshot(prefix)
    second_run = run_settlement(repository, dry_run=False)
    after_second = repository.user_balance(username)
    second_bets = repository.bet_snapshot(prefix)
    return SmokeReport(
        test_prefix=prefix,
        test_user=username,
        test_matches_created=2,
        bets_created=3,
        first_run=first_run,
        second_run=second_run,
        initial_balance=initial_balance,
        after_first_run_balance=after_first,
        after_second_run_balance=after_second,
        first_bet_snapshot=first_bets,
        second_bet_snapshot=second_bets,
    )


def cleanup(prefix: str) -> dict[str, int]:
    _assert_prefix(prefix)
    username = _username_from_prefix(prefix)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM bets WHERE legs::text LIKE %s", (f"%{prefix}%",))
        bets_deleted = cur.rowcount
        cur.execute("DELETE FROM matches WHERE match_id LIKE %s", (f"{prefix}%",))
        matches_deleted = cur.rowcount
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
        users_deleted = cur.rowcount
    return {"bets_deleted": bets_deleted, "matches_deleted": matches_deleted, "users_deleted": users_deleted}


def print_report(report: SmokeReport) -> None:
    print("Settlement Smoke Report")
    print(f"- test_prefix: {report.test_prefix}")
    print(f"- test_user: {report.test_user}")
    print(f"- test_matches_created: {report.test_matches_created}")
    print(f"- bets_created: {report.bets_created}")
    print("- first_run:")
    print(f"  - settled_won: {report.first_run.settled_won}")
    print(f"  - settled_lost: {report.first_run.settled_lost}")
    print(f"  - settled_void: {report.first_run.settled_void}")
    print(f"  - skipped_not_ready: {report.first_run.skipped_not_ready}")
    print(f"  - errors: {report.first_run.errors}")
    print("- idempotency:")
    print(f"  - second_run_changed_balance: {str(report.second_run_changed_balance).lower()}")
    print(f"  - second_run_changed_bets: {str(report.second_run_changed_bets).lower()}")
    print("- balances:")
    print(f"  - initial: {report.initial_balance}")
    print(f"  - after_first_run: {report.after_first_run_balance}")
    print(f"  - after_second_run: {report.after_second_run_balance}")
    print(f"- result: {'PASS' if report.passed else 'FAIL'}")
    print(f"- cleanup_command: python -m api.settlement_smoke cleanup --prefix {report.test_prefix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="test-only settlement closed-loop smoke")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--prefix")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--prefix", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_smoke(args.prefix)
            print_report(report)
            return 0 if report.passed else 1
        result = cleanup(args.prefix)
        print("Settlement Smoke Cleanup")
        print(f"- prefix: {args.prefix}")
        for key, value in result.items():
            print(f"- {key}: {value}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


class SmokeSettlementRepository:
    def __init__(self, prefix: str):
        _assert_prefix(prefix)
        self.prefix = prefix

    def open_bets(self) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, legs, parlay, stake
                FROM bets
                WHERE status = 'open'
                  AND legs::text LIKE %s
                ORDER BY id
                """,
                (f"%{self.prefix}%",),
            )
            return [dict(row) for row in cur.fetchall()]

    def match_rows(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        for match_id in match_ids:
            assert_test_match_id(match_id)
            if not str(match_id).startswith(self.prefix):
                raise ValueError("settlement smoke repository refused out-of-prefix match_id")
        if not match_ids:
            return {}
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, match_num, status, result_home, result_away, ht_home, ht_away
                FROM matches
                WHERE match_id = ANY(%s)
                  AND match_id LIKE %s
                  AND match_id NOT LIKE '500-%%'
                  AND COALESCE(match_num, '') NOT LIKE '周%%'
                """,
                (match_ids, f"{self.prefix}%"),
            )
            return {str(row["match_id"]): dict(row) for row in cur.fetchall()}

    def apply_settlement(self, bet_id: int, status: str, payout: Decimal) -> bool:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE bets
                SET status = %s,
                    payout = %s,
                    settled_at = now()
                WHERE id = %s
                  AND status = 'open'
                  AND legs::text LIKE %s
                RETURNING user_id
                """,
                (status, payout, bet_id, f"%{self.prefix}%"),
            )
            row = cur.fetchone()
            if not row:
                return False
            if payout > 0:
                cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (payout, row["user_id"]))
            return True


def _create_test_data(conn, prefix: str, username: str) -> None:
    main_match = prefix
    postponed_match = f"{prefix}-void"
    assert_test_match_id(main_match, "TEST001")
    assert_test_match_id(postponed_match, "TEST002")
    kickoff = datetime.now(timezone.utc) - timedelta(hours=2)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO matches (
              match_id, match_num, league, home_team, away_team, kickoff_at,
              status, result_home, result_away, ht_home, ht_away
            )
            VALUES
              (%s, 'TEST001', '测试', '测试主队', '测试客队', %s, 'finished', 2, 1, 1, 0),
              (%s, 'TEST002', '测试', '测试主队', '测试客队', %s, 'postponed', NULL, NULL, NULL, NULL)
            ON CONFLICT (match_id) DO UPDATE SET
              status = EXCLUDED.status,
              result_home = EXCLUDED.result_home,
              result_away = EXCLUDED.result_away,
              ht_home = EXCLUDED.ht_home,
              ht_away = EXCLUDED.ht_away
            """,
            (main_match, kickoff, postponed_match, kickoff),
        )
        cur.execute(
            """
            INSERT INTO users (username, password_hash, balance)
            VALUES (%s, 'settlement-smoke-test-only', 10000)
            ON CONFLICT (username) DO UPDATE SET balance = 10000
            RETURNING id
            """,
            (username,),
        )
        user_id = int(cur.fetchone()["id"])
        cur.execute("DELETE FROM bets WHERE legs::text LIKE %s", (f"%{prefix}%",))
        bets = [
            ("single_win", [{"match_id": main_match, "play_type": "had", "selection": "3", "odds": "2.00"}], "single", Decimal("10"), Decimal("20")),
            ("single_loss", [{"match_id": main_match, "play_type": "had", "selection": "0", "odds": "2.00"}], "single", Decimal("10"), Decimal("20")),
            (
                "parlay_void_win",
                [
                    {"match_id": main_match, "play_type": "had", "selection": "3", "odds": "2.00"},
                    {"match_id": postponed_match, "play_type": "had", "selection": "3", "odds": "3.00"},
                ],
                "2x1",
                Decimal("10"),
                Decimal("60"),
            ),
        ]
        for label, legs, parlay, stake, potential_payout in bets:
            cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (stake, user_id))
            cur.execute(
                """
                INSERT INTO bets (user_id, legs, parlay, stake, potential_payout, status)
                VALUES (%s, %s, %s, %s, %s, 'open')
                """,
                (user_id, Jsonb([{**leg, "label": label} for leg in legs]), parlay, stake, potential_payout),
            )


def _bet_snapshot(conn, prefix: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, legs, status, payout
            FROM bets
            WHERE legs::text LIKE %s
            ORDER BY id
            """,
            (f"%{prefix}%",),
        )
        rows = [dict(row) for row in cur.fetchall()]
    snapshot: list[dict[str, Any]] = []
    for row in rows:
        label = row["legs"][0].get("label", "unknown")
        snapshot.append({"id": row["id"], "label": label, "status": row["status"], "payout": row["payout"]})
    return snapshot


def _user_balance(conn, username: str) -> Decimal:
    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"test user not found: {username}")
    return Decimal(str(row[0]))


def _new_prefix() -> str:
    return f"{TEST_SETTLEMENT_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _username_from_prefix(prefix: str) -> str:
    return f"{TEST_USER_PREFIX}{prefix.removeprefix(TEST_SETTLEMENT_PREFIX)}"


def _assert_prefix(prefix: str) -> None:
    if not prefix:
        raise ValueError("prefix is required")
    if not prefix.startswith(TEST_SETTLEMENT_PREFIX):
        raise ValueError("prefix must start with test-settlement-")
    assert_test_match_id(prefix, "TEST001")


if __name__ == "__main__":
    raise SystemExit(main())
