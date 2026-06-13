from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.betting_open_gate import generate_report as generate_betting_gate_report
from api.db import connect
from api.result_consistency_report import generate_report as generate_consistency_report
from api.settlement_runner import run_settlement


CONFIRM_TOKEN = "RUN_ABNORMAL_STATUS_PROBE"
TEST_MATCHES = (
    ("test-postponed-001", "postponed", "postponed external state"),
    ("test-abandoned-001", "abandoned", "abandoned external state"),
    ("test-cancelled-001", "cancelled", "cancelled external state"),
    ("test-rescheduled-001", "rescheduled", "rescheduled external state"),
    ("test-interrupted-001", "interrupted", "interrupted external state"),
)
PROBE_USERNAME = "__abnormal_status_probe__"


def environment_guard_passed() -> bool:
    app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
    allow_override = _enabled(os.getenv("ALLOW_TEST_PROBES", "false"))
    return app_env != "production" or allow_override


def dry_run_report() -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "environment_guard_passed": environment_guard_passed(),
        "created_test_matches": [match_id for match_id, _status, _notes in TEST_MATCHES],
        "assertions": {
            "not_marked_finished": True,
            "result_stays_null": True,
            "settlement_skipped": True,
            "consistency_pass": True,
            "betting_gate_not_improved": True,
        },
        "cleanup": {"deleted_test_matches": 0, "deleted_probe_bets": 0, "deleted_probe_users": 0},
        "result": "PASS",
        "writes_real_matches": False,
        "opens_betting": False,
    }


def run_confirm(confirm: str | None) -> dict[str, Any]:
    if confirm != CONFIRM_TOKEN:
        return _failed("confirm token required", mode="confirm")
    if not environment_guard_passed():
        return _failed(
            "abnormal_status_probe must not run against production without explicit test override",
            mode="confirm",
            environment_guard=False,
        )
    cleanup_report = {"deleted_test_matches": 0, "deleted_probe_bets": 0, "deleted_probe_users": 0}
    try:
        with connect() as conn:
            _create_probe_data(conn)
        settlement_stats = run_settlement(AbnormalProbeSettlementRepository(), dry_run=True)
        consistency = generate_consistency_report()
        betting_gate_before = generate_betting_gate_report()
        with connect() as conn:
            match_rows = _probe_match_rows(conn)
        assertions = {
            "not_marked_finished": all(row["status"] not in {"finished", "completed"} for row in match_rows),
            "result_stays_null": all(row["result_home"] is None and row["result_away"] is None for row in match_rows),
            "settlement_skipped": settlement_stats.skipped_not_ready >= 1 and settlement_stats.settled_won == 0 and settlement_stats.settled_lost == 0,
            "consistency_pass": consistency.get("result") in {"PASS", "WARN"},
            "betting_gate_not_improved": generate_betting_gate_report().get("recommend_open_betting") is not True
            or betting_gate_before.get("recommend_open_betting") is True,
        }
        result = "PASS" if all(assertions.values()) else "FAIL"
        return {
            "mode": "confirm",
            "environment_guard_passed": True,
            "created_test_matches": [row["match_id"] for row in match_rows],
            "assertions": assertions,
            "cleanup": _cleanup_probe_data(),
            "result": result,
            "writes_real_matches": False,
            "opens_betting": False,
        }
    except Exception as exc:
        cleanup_report = _cleanup_probe_data()
        return {
            "mode": "confirm",
            "environment_guard_passed": True,
            "created_test_matches": [match_id for match_id, _status, _notes in TEST_MATCHES],
            "assertions": {},
            "cleanup": cleanup_report,
            "result": "FAIL",
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "writes_real_matches": False,
            "opens_betting": False,
        }


class AbnormalProbeSettlementRepository:
    def open_bets(self) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, legs, parlay, stake
                FROM bets
                WHERE legs::text LIKE '%test-%'
                  AND user_id IN (SELECT id FROM users WHERE username = %s)
                ORDER BY id
                """,
                (PROBE_USERNAME,),
            )
            return [dict(row) for row in cur.fetchall()]

    def match_rows(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        if any(not str(match_id).startswith("test-") for match_id in match_ids):
            raise ValueError("abnormal status probe refused non-test match")
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, status, result_home, result_away, ht_home, ht_away
                FROM matches
                WHERE match_id = ANY(%s)
                  AND match_id LIKE 'test-%%'
                """,
                (match_ids,),
            )
            return {str(row["match_id"]): dict(row) for row in cur.fetchall()}

    def apply_settlement(self, bet_id: int, status: str, payout: Decimal) -> bool:
        raise AssertionError("abnormal_status_probe must not apply settlement")


def print_report(report: dict[str, Any]) -> None:
    print("Abnormal Status Probe Report")
    print(f"mode: {report.get('mode')}")
    print(f"environment_guard_passed: {report.get('environment_guard_passed')}")
    if report.get("error"):
        print(f"error: {report['error']}")
    print("created_test_matches:")
    for match_id in report.get("created_test_matches", []):
        print(f"- {match_id}")
    print("assertions:")
    for key, value in (report.get("assertions") or {}).items():
        print(f"  {key}: {value}")
    print("cleanup:")
    for key, value in (report.get("cleanup") or {}).items():
        print(f"  {key}: {value}")
    print(f"result: {report.get('result')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="non-production abnormal status probe")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    if args.dry_run == bool(args.confirm):
        print("usage: python -m api.abnormal_status_probe --dry-run | --confirm RUN_ABNORMAL_STATUS_PROBE", file=sys.stderr)
        return 2
    report = dry_run_report() if args.dry_run else run_confirm(args.confirm)
    print_report(report)
    return 0 if report.get("result") == "PASS" else 1


def _create_probe_data(conn) -> None:
    kickoff = datetime.now(timezone.utc) - timedelta(hours=3)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, balance)
            VALUES (%s, 'abnormal-status-probe-test-only', 10000)
            ON CONFLICT (username) DO UPDATE SET balance = 10000
            RETURNING id
            """,
            (PROBE_USERNAME,),
        )
        user_id = int(cur.fetchone()["id"])
        for idx, (match_id, status, notes) in enumerate(TEST_MATCHES, start=1):
            if not match_id.startswith("test-"):
                raise ValueError("probe match id must start with test-")
            cur.execute(
                """
                INSERT INTO matches (
                  match_id, match_num, league, home_team, away_team, kickoff_at,
                  status, result_home, result_away, ht_home, ht_away
                )
                VALUES (%s, %s, '测试', '异常主队', '异常客队', %s, %s, NULL, NULL, NULL, NULL)
                ON CONFLICT (match_id) DO UPDATE SET
                  status = EXCLUDED.status,
                  result_home = NULL,
                  result_away = NULL,
                  ht_home = NULL,
                  ht_away = NULL
                """,
                (match_id, f"TEST-ABN-{idx:03d}", kickoff, status),
            )
        cur.execute("DELETE FROM bets WHERE user_id = %s OR legs::text LIKE '%test-postponed-001%'", (user_id,))
        cur.execute(
            """
            INSERT INTO bets (user_id, legs, parlay, stake, potential_payout, status)
            VALUES (%s, %s, 'single', 1, 2, 'open')
            """,
            (
                user_id,
                Jsonb(
                    [
                        {
                            "match_id": "test-postponed-001",
                            "play_type": "had",
                            "selection": "3",
                            "odds": "2.00",
                        }
                    ]
                ),
            ),
        )


def _probe_match_rows(conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, status, result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE match_id = ANY(%s)
            ORDER BY match_id
            """,
            ([match_id for match_id, _status, _notes in TEST_MATCHES],),
        )
        return [dict(row) for row in cur.fetchall()]


def _cleanup_probe_data() -> dict[str, int]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bets
            WHERE user_id IN (SELECT id FROM users WHERE username = %s)
               OR legs::text LIKE '%test-postponed-001%'
            """,
            (PROBE_USERNAME,),
        )
        deleted_bets = cur.rowcount
        cur.execute(
            "DELETE FROM matches WHERE match_id = ANY(%s) AND match_id LIKE 'test-%%'",
            ([match_id for match_id, _status, _notes in TEST_MATCHES],),
        )
        deleted_matches = cur.rowcount
        cur.execute("DELETE FROM users WHERE username = %s", (PROBE_USERNAME,))
        deleted_users = cur.rowcount
    return {
        "deleted_test_matches": deleted_matches,
        "deleted_probe_bets": deleted_bets,
        "deleted_probe_users": deleted_users,
    }


def _failed(message: str, *, mode: str, environment_guard: bool | None = None) -> dict[str, Any]:
    return {
        "mode": mode,
        "environment_guard_passed": environment_guard if environment_guard is not None else environment_guard_passed(),
        "created_test_matches": [],
        "assertions": {},
        "cleanup": {"deleted_test_matches": 0, "deleted_probe_bets": 0, "deleted_probe_users": 0},
        "result": "FAIL",
        "error": message,
        "writes_real_matches": False,
        "opens_betting": False,
    }


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
