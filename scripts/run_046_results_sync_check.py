from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from typing import Any


# 046-RUN: real result sync verification.
#
# Intended location: wc-p2-api container /app.
#
# Safety boundaries:
# - does not print DATABASE_URL
# - does not execute manual UPDATE statements
# - does not execute migrations
# - stops immediately if BETTING_ENABLED=true
# - only runs settlement_runner automatically when open_pending_count=0

DATABASE_URL = os.environ.get("DATABASE_URL")
BETTING_ENABLED = os.environ.get("BETTING_ENABLED", "false")

TARGET_MATCHES = {
    "500-1359172": {
        "label": "Mexico vs South Africa",
        "expected_home": 2,
        "expected_away": 0,
    },
    "500-1359224": {
        "label": "Korea Republic vs Czech Republic",
        "expected_home": 2,
        "expected_away": 1,
    },
}


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL missing")

    try:
        import psycopg2

        return psycopg2.connect(DATABASE_URL)
    except Exception:
        pass

    try:
        import psycopg

        return psycopg.connect(DATABASE_URL)
    except Exception as exc:
        raise RuntimeError(f"No usable postgres driver found: {exc}") from exc


def fetch_all(sql: str, params: tuple[Any, ...] | None = None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows
    finally:
        conn.close()


def print_rows(title: str, cols, rows) -> None:
    print()
    print(f"=== {title} ===")
    print("columns:", cols)
    print("row_count:", len(rows))

    for row in rows:
        clean = []
        for value in row:
            if isinstance(value, (dict, list)):
                clean.append(json.dumps(value, ensure_ascii=False))
            else:
                clean.append(str(value) if value is not None else "NULL")
        print(" | ".join(clean))


def run_module(title: str, args: list[str]) -> None:
    print()
    print(f"=== {title} ===")
    proc = subprocess.run(args, text=True, capture_output=True)

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print("STDERR:", proc.stderr)

    print("exit_code:", proc.returncode)

    if proc.returncode != 0:
        raise SystemExit(f"{title} failed")


def health_check() -> None:
    print()
    print("=== Step 1: API Health by urllib ===")
    try:
        with urllib.request.urlopen(
            "https://fifa2026.zeabur.app/api/health",
            timeout=20,
        ) as response:
            print(response.read().decode("utf-8"))
    except Exception as exc:
        print("api_health_error:", repr(exc))


def main() -> None:
    print("=" * 70)
    print("046-RUN Real Result Sync Check")
    print("=" * 70)
    print("time_utc=", datetime.now(timezone.utc).isoformat())
    print("pwd=", os.getcwd())
    print("BETTING_ENABLED=", BETTING_ENABLED)
    print("DATABASE_URL_SET=", bool(DATABASE_URL))

    if BETTING_ENABLED == "true":
        raise SystemExit("ERROR: BETTING_ENABLED=true detected. Stop.")

    if not DATABASE_URL:
        raise SystemExit("ERROR: DATABASE_URL missing. Stop.")

    os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", ".")

    health_check()

    cols, rows = fetch_all(
        """
        SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
               result_home, result_away, ht_home, ht_away
        FROM matches
        WHERE match_id IN ('500-1359172','500-1359224')
        ORDER BY match_id;
        """
    )
    print_rows("Step 2: Target matches BEFORE results_sync", cols, rows)

    cols, rows = fetch_all(
        """
        SELECT job_name,status,started_at,finished_at,error
        FROM ops_log
        ORDER BY id DESC
        LIMIT 8;
        """
    )
    print_rows("Step 3: Latest ops_log BEFORE results_sync", cols, rows)

    run_module(
        "Step 4: Run results_sync once",
        ["python", "-m", "api.results_sync", "once"],
    )

    cols, rows = fetch_all(
        """
        SELECT match_id, match_num, home_team, away_team, kickoff_at, status,
               result_home, result_away, ht_home, ht_away
        FROM matches
        WHERE match_id IN ('500-1359172','500-1359224')
        ORDER BY match_id;
        """
    )
    print_rows("Step 5: Target matches AFTER results_sync", cols, rows)

    result_map = {}
    for row in rows:
        match_id = row[0]
        status = row[5]
        result_home = row[6]
        result_away = row[7]
        result_map[match_id] = {
            "status": status,
            "result_home": result_home,
            "result_away": result_away,
        }

    print()
    print("=== Step 6: Expected-result verification, read-only ===")

    all_targets_synced = True

    for match_id, expected in TARGET_MATCHES.items():
        actual = result_map.get(match_id)

        if not actual:
            print(f"{match_id}: MISSING_FROM_DB")
            all_targets_synced = False
            continue

        status_ok = actual["status"] in ("finished", "completed")
        score_ok = (
            actual["result_home"] == expected["expected_home"]
            and actual["result_away"] == expected["expected_away"]
        )

        print(
            f"{match_id} {expected['label']}: "
            f"status={actual['status']} "
            f"score={actual['result_home']}-{actual['result_away']} "
            f"expected={expected['expected_home']}-{expected['expected_away']} "
            f"status_ok={status_ok} "
            f"score_ok={score_ok}"
        )

        if not (status_ok and score_ok):
            all_targets_synced = False

    run_module(
        "Step 7: Result consistency report",
        ["python", "-m", "api.result_consistency_report"],
    )

    cols, rows = fetch_all(
        """
        SELECT match_id,match_num,home_team,away_team,kickoff_at,status,
               result_home,result_away,ht_home,ht_away
        FROM matches
        WHERE status IN ('finished','completed')
          AND (result_home IS NULL OR result_away IS NULL)
        ORDER BY kickoff_at;
        """
    )
    print_rows("Step 8: finished/completed + NULL result", cols, rows)
    finished_null_count = len(rows)

    cols, rows = fetch_all(
        """
        SELECT match_id,match_num,home_team,away_team,kickoff_at,status,
               result_home,result_away
        FROM matches
        WHERE status NOT IN ('finished','completed')
          AND (result_home IS NOT NULL OR result_away IS NOT NULL)
        ORDER BY kickoff_at;
        """
    )
    print_rows("Step 9: non-finished + populated result", cols, rows)
    non_finished_with_result_count = len(rows)

    cols, rows = fetch_all(
        """
        SELECT status, COUNT(*)
        FROM bets
        GROUP BY status
        ORDER BY status;
        """
    )
    print_rows("Step 10: Bets status counts", cols, rows)

    cols, rows = fetch_all(
        """
        SELECT COALESCE(COUNT(*),0) AS open_pending_count
        FROM bets
        WHERE status IN ('open','pending');
        """
    )
    open_pending_count = int(rows[0][0]) if rows else 0

    print()
    print("open_pending_count=", open_pending_count)

    if open_pending_count == 0:
        run_module(
            "Step 11: Safe no-op settlement_runner",
            ["python", "-m", "api.settlement_runner", "once"],
        )

        cols, rows = fetch_all(
            """
            SELECT status, COUNT(*)
            FROM bets
            GROUP BY status
            ORDER BY status;
            """
        )
        print_rows("Step 12: Bets status AFTER settlement_runner no-op", cols, rows)

        cols, rows = fetch_all(
            """
            SELECT job_name,status,started_at,finished_at,summary,error
            FROM ops_log
            WHERE job_name='settlement_runner'
            ORDER BY id DESC
            LIMIT 5;
            """
        )
        print_rows("Step 13: Latest settlement_runner ops_log", cols, rows)
    else:
        print()
        print("=== Step 11: SKIP settlement_runner ===")
        print("open/pending bets exist. Do NOT auto-run settlement_runner.")
        print("Paste this output back before running true settlement once.")

    cols, rows = fetch_all(
        """
        SELECT COUNT(*) AS evaluable_finished_matches
        FROM matches
        WHERE status IN ('finished','completed')
          AND result_home IS NOT NULL
          AND result_away IS NOT NULL;
        """
    )
    print_rows("Step 14: P1-C evaluable finished matches count", cols, rows)
    evaluable_finished_matches = int(rows[0][0]) if rows else 0

    cols, rows = fetch_all(
        """
        SELECT job_name,status,started_at,finished_at,error
        FROM ops_log
        ORDER BY id DESC
        LIMIT 10;
        """
    )
    print_rows("Step 15: Latest ops_log AFTER run", cols, rows)

    print()
    print("=" * 70)
    print("046-RUN FINAL SUMMARY")
    print("=" * 70)
    print("target_results_synced=", all_targets_synced)
    print("finished_null_count=", finished_null_count)
    print("non_finished_with_result_count=", non_finished_with_result_count)
    print("open_pending_count=", open_pending_count)
    print("settlement_runner_noop_verified=", open_pending_count == 0)
    print("bet_settlement_pass=", False)
    print("evaluable_finished_matches=", evaluable_finished_matches)

    if (
        all_targets_synced
        and finished_null_count == 0
        and non_finished_with_result_count == 0
    ):
        print("result_sync_status=PASS")
    else:
        print("result_sync_status=FAIL_OR_NEEDS_FALLBACK")
        print("next_action=implement official result fallback; do not hand-update scores")

    print("recommend_open_betting=false")
    print("No migration executed.")
    print("No manual UPDATE executed.")
    print("BETTING_ENABLED must remain false.")


if __name__ == "__main__":
    main()
