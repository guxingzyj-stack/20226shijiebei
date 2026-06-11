from __future__ import annotations

import argparse
from typing import Any

from api.db import connect


CONFIRM_TOKEN = "CLEAN_TEST_DATA"

TEST_USER_WHERE = "(username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%')"
TEST_MATCH_WHERE = "match_id LIKE 'test-%%'"


def dry_run() -> dict[str, int]:
    with connect() as conn:
        targets = collect_targets(conn)
        validate_targets(conn, targets)
        return target_counts(targets)


def run(confirm: str | None) -> dict[str, int]:
    if confirm != CONFIRM_TOKEN:
        raise ValueError(f"run requires --confirm {CONFIRM_TOKEN}")
    with connect() as conn:
        try:
            targets = collect_targets(conn)
            validate_targets(conn, targets)
            counts = target_counts(targets)
            delete_targets(conn)
            conn.commit()
            return counts
        except Exception:
            conn.rollback()
            raise


def collect_targets(conn) -> dict[str, list[Any]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, username FROM users WHERE {TEST_USER_WHERE} ORDER BY id")
        users = [{"id": int(row[0]), "username": str(row[1])} for row in cur.fetchall()]
        user_ids = [row["id"] for row in users]

        cur.execute(f"SELECT match_id FROM matches WHERE {TEST_MATCH_WHERE} ORDER BY match_id")
        matches = [str(row[0]) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT id
            FROM bets
            WHERE user_id = ANY(%s)
               OR legs::text LIKE '%%test-%%'
            ORDER BY id
            """,
            (user_ids,),
        )
        bets = [int(row[0]) for row in cur.fetchall()]
    return {"users": users, "matches": matches, "bets": bets}


def validate_targets(conn, targets: dict[str, list[Any]]) -> None:
    unsafe_users = [row["username"] for row in targets["users"] if not _is_test_username(row["username"])]
    if unsafe_users:
        raise RuntimeError("refusing cleanup: non-test user selected")
    unsafe_matches = [match_id for match_id in targets["matches"] if not _is_test_match_id(match_id) or match_id.startswith("500-")]
    if unsafe_matches:
        raise RuntimeError("refusing cleanup: non-test or real match selected")
    _assert_no_real_match_delete(conn)


def target_counts(targets: dict[str, list[Any]]) -> dict[str, int]:
    return {
        "bet_legs": 0,
        "bets": len(targets["bets"]),
        "matches": len(targets["matches"]),
        "users": len(targets["users"]),
    }


def delete_targets(conn) -> None:
    with conn.cursor() as cur:
        # No bet_legs table exists in the current schema; bets.legs is JSONB.
        cur.execute(
            """
            DELETE FROM bets
            WHERE user_id IN (
              SELECT id FROM users
              WHERE username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%'
            )
               OR legs::text LIKE '%%test-%%'
            """
        )
        cur.execute("DELETE FROM matches WHERE match_id LIKE 'test-%%' AND match_id NOT LIKE '500-%%'")
        cur.execute("DELETE FROM users WHERE username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%'")


def _assert_no_real_match_delete(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM matches WHERE match_id LIKE '500-%%' AND match_id LIKE 'test-%%'")
        if int(cur.fetchone()[0]) != 0:
            raise RuntimeError("refusing cleanup: real 500- match matched test cleanup scope")


def _is_test_username(username: str) -> bool:
    return username.startswith("test_user_") or username.startswith("codex_blocker_")


def _is_test_match_id(match_id: str) -> bool:
    return match_id.startswith("test-")


def print_report(mode: str, counts: dict[str, Any]) -> None:
    print("Cleanup Test Data Report")
    print(f"- mode: {mode}")
    print(f"- bet_legs: {counts['bet_legs']}")
    print(f"- bets: {counts['bets']}")
    print(f"- matches: {counts['matches']}")
    print(f"- users: {counts['users']}")
    print("- protected_real_500_matches: true")
    print("- protected_non_test_users: true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cleanup test-only data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("dry-run")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        if args.command == "dry-run":
            counts = dry_run()
            print_report("dry-run", counts)
        else:
            counts = run(args.confirm)
            print_report("run", counts)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
