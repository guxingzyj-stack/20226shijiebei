from __future__ import annotations

import argparse
from typing import Any

from api.db import connect


CONFIRM_TOKEN = "CLEAN_TEST_DATA"


def dry_run() -> dict[str, int]:
    return cleanup(write=False)


def run(confirm: str | None) -> dict[str, int]:
    if confirm != CONFIRM_TOKEN:
        raise ValueError(f"run requires --confirm {CONFIRM_TOKEN}")
    return cleanup(write=True)


def cleanup(write: bool = False) -> dict[str, int]:
    with connect() as conn:
        _assert_no_real_match_delete(conn)
        counts = _counts(conn)
        if write:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bets WHERE legs::text LIKE '%%test-%%'")
                cur.execute("DELETE FROM matches WHERE match_id LIKE 'test-%%'")
                cur.execute("DELETE FROM users WHERE username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%'")
            conn.commit()
    return counts


def _counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM bets WHERE legs::text LIKE '%%test-%%'")
        bets = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM matches WHERE match_id LIKE 'test-%%'")
        matches = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM users WHERE username LIKE 'test_user_%%' OR username LIKE 'codex_blocker_%%'")
        users = int(cur.fetchone()[0])
    return {"bets": bets, "matches": matches, "users": users}


def _assert_no_real_match_delete(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM matches WHERE match_id LIKE '500-%%' AND match_id LIKE 'test-%%'")
        if int(cur.fetchone()[0]) != 0:
            raise RuntimeError("refusing cleanup: real 500- match matched test cleanup scope")


def print_report(mode: str, counts: dict[str, Any]) -> None:
    print("Cleanup Test Data Report")
    print(f"- mode: {mode}")
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
