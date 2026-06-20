from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import make_json_safe


TASK_ID = "076-cleanup-dirty-match-id-500--1"
DIRTY_MATCH_ID = "500--1"
CORRECT_MATCH_ID = "500-1359210"
CONFIRM_TOKEN = "DELETE_500_DASH_1"
DEFAULT_BACKUP_DIR = Path("output") / "cleanup_dirty_match_id"

MATCH_ID_TABLES = (
    "matches",
    "odds_snapshots",
    "predictions",
    "ev_signals",
    "gbm_predictions",
    "result_ingest_observations",
)

DELETE_ORDER = (
    "gbm_predictions",
    "odds_snapshots",
    "predictions",
    "ev_signals",
    "result_ingest_observations",
    "matches",
)


def table_exists(cur: Any, table_name: str) -> bool:
    if table_name == "gbm_predictions":
        cur.execute("SELECT to_regclass('public.gbm_predictions') AS table_name")
    else:
        cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
    row = cur.fetchone()
    return bool(row and row["table_name"])


def collect_state() -> dict[str, Any]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        return _collect_state(cur)


def _collect_state(cur: Any) -> dict[str, Any]:
    table_status = {table: table_exists(cur, table) for table in MATCH_ID_TABLES}
    table_status["bets"] = table_exists(cur, "bets")
    table_status["script_predictions"] = table_exists(cur, "script_predictions")

    dirty_counts: dict[str, int | str] = {}
    for table in MATCH_ID_TABLES:
        if not table_status[table]:
            dirty_counts[table] = "table_not_found_skipped"
            continue
        dirty_counts[table] = _count_match_id(cur, table, DIRTY_MATCH_ID)

    dirty_match = _fetch_one_match(cur, DIRTY_MATCH_ID) if table_status["matches"] else None
    correct_match = _fetch_one_match(cur, CORRECT_MATCH_ID) if table_status["matches"] else None
    correct_pre_kickoff_predictions = (
        _count_correct_pre_kickoff_predictions(cur) if table_status["matches"] and table_status["predictions"] else 0
    )

    bets_with_dirty_match_id = _count_bets_with_match_id(cur, DIRTY_MATCH_ID) if table_status["bets"] else 0
    script_prediction_count = _count_table(cur, "script_predictions") if table_status["script_predictions"] else "table_not_found_skipped"
    split_identity_count = _count_correct_identity_matches(cur, correct_match) if correct_match else 0

    return {
        "task_id": TASK_ID,
        "target": DIRTY_MATCH_ID,
        "correct_id": CORRECT_MATCH_ID,
        "table_status": table_status,
        "dirty_counts": dirty_counts,
        "dirty_match": dirty_match,
        "correct_match": correct_match,
        "correct_pre_kickoff_predictions": correct_pre_kickoff_predictions,
        "bets_with_dirty_match_id": bets_with_dirty_match_id,
        "script_predictions_count": script_prediction_count,
        "script_predictions": "untouched",
        "split_identity_count": split_identity_count,
    }


def _count_match_id(cur: Any, table_name: str, match_id: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table_name} WHERE match_id = %s", (match_id,))
    return int(cur.fetchone()["count"])


def _count_table(cur: Any, table_name: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table_name}")
    return int(cur.fetchone()["count"])


def _fetch_one_match(cur: Any, match_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT match_id, match_num, league, home_team, away_team, kickoff_at,
               status, result_home, result_away, ht_home, ht_away
        FROM matches
        WHERE match_id = %s
        """,
        (match_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _count_correct_pre_kickoff_predictions(cur: Any) -> int:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM predictions
        WHERE match_id = %s
          AND created_at <= (
            SELECT kickoff_at FROM matches WHERE match_id = %s
          )
        """,
        (CORRECT_MATCH_ID, CORRECT_MATCH_ID),
    )
    return int(cur.fetchone()["count"])


def _count_bets_with_match_id(cur: Any, match_id: str) -> int:
    cur.execute("SELECT count(*) AS count FROM bets WHERE legs::text LIKE %s", (f"%{match_id}%",))
    return int(cur.fetchone()["count"])


def _count_correct_identity_matches(cur: Any, correct_match: dict[str, Any]) -> int:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM matches
        WHERE match_id IN (%s, %s)
           OR (
             home_team = %s
             AND away_team = %s
             AND kickoff_at = %s
           )
        """,
        (
            DIRTY_MATCH_ID,
            CORRECT_MATCH_ID,
            correct_match["home_team"],
            correct_match["away_team"],
            correct_match["kickoff_at"],
        ),
    )
    return int(cur.fetchone()["count"])


def validate_state(state: dict[str, Any], *, require_dirty_match: bool) -> list[str]:
    errors: list[str] = []
    dirty_match_count = _int_count(state["dirty_counts"].get("matches"))
    correct_match = state.get("correct_match")

    if require_dirty_match and dirty_match_count != 1:
        errors.append(f"expected exactly one dirty match {DIRTY_MATCH_ID}, found {dirty_match_count}")
    if dirty_match_count and not correct_match:
        errors.append(f"correct match {CORRECT_MATCH_ID} is missing")
    if dirty_match_count and int(state.get("correct_pre_kickoff_predictions") or 0) < 1:
        errors.append(f"correct match {CORRECT_MATCH_ID} has no pre-kickoff prediction")
    if int(state.get("bets_with_dirty_match_id") or 0) > 0:
        errors.append("bets reference dirty match id; refusing to modify bets/users/balance")
    return errors


def _int_count(value: int | str | None) -> int:
    return value if isinstance(value, int) else 0


def create_backup(conn: Any, state: dict[str, Any], backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_file = backup_dir / f"{TASK_ID}_{timestamp}.json"
    payload: dict[str, Any] = {
        "task_id": TASK_ID,
        "target": DIRTY_MATCH_ID,
        "correct_id": CORRECT_MATCH_ID,
        "state": state,
        "rows": {},
    }
    with conn.cursor(row_factory=dict_row) as cur:
        for table in MATCH_ID_TABLES:
            if not state["table_status"].get(table):
                payload["rows"][table] = "table_not_found_skipped"
                continue
            cur.execute(f"SELECT * FROM {table} WHERE match_id = %s ORDER BY 1", (DIRTY_MATCH_ID,))
            payload["rows"][table] = [dict(row) for row in cur.fetchall()]
    backup_file.write_text(json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_file


def run_delete() -> dict[str, Any]:
    with connect() as conn:
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                state = _collect_state(cur)
                errors = validate_state(state, require_dirty_match=True)
                if errors:
                    raise RuntimeError("; ".join(errors))

            backup_file = create_backup(conn, state)

            deleted: dict[str, int | str] = {}
            with conn.cursor(row_factory=dict_row) as cur:
                for table in DELETE_ORDER:
                    if not state["table_status"].get(table):
                        deleted[table] = "table_not_found_skipped"
                        continue
                    cur.execute(f"DELETE FROM {table} WHERE match_id = %s", (DIRTY_MATCH_ID,))
                    deleted[table] = int(cur.rowcount or 0)

                after_state = _collect_state(cur)
                verification_errors = _verify_after_delete(after_state, state)
                if verification_errors:
                    raise RuntimeError("; ".join(verification_errors))

            conn.commit()
            return {
                "ok": True,
                "backup_file": str(backup_file),
                "before": state,
                "deleted": deleted,
                "after": after_state,
                "rollback": False,
            }
        except Exception:
            conn.rollback()
            raise


def _verify_after_delete(after_state: dict[str, Any], before_state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for table, count in after_state["dirty_counts"].items():
        if isinstance(count, int) and count != 0:
            errors.append(f"{table} still has {count} rows for {DIRTY_MATCH_ID}")
    if not after_state.get("correct_match"):
        errors.append(f"correct match {CORRECT_MATCH_ID} missing after delete")
    if int(after_state.get("correct_pre_kickoff_predictions") or 0) < 1:
        errors.append(f"correct match {CORRECT_MATCH_ID} lost pre-kickoff predictions")
    if after_state.get("split_identity_count") != 1:
        errors.append(f"Spain vs Saudi identity count expected 1, found {after_state.get('split_identity_count')}")
    if after_state.get("script_predictions_count") != before_state.get("script_predictions_count"):
        errors.append("script_predictions count changed")
    return errors


def dry_run() -> dict[str, Any]:
    state = collect_state()
    errors = validate_state(state, require_dirty_match=False)
    return {
        "ok": not errors,
        "errors": errors,
        "state": state,
        "would_delete": state["dirty_counts"],
    }


def print_report(report: dict[str, Any], *, mode: str) -> None:
    state = report.get("state") or report.get("before") or {}
    after = report.get("after")
    print("Cleanup Dirty Match ID Report")
    print(f"- task_id: {TASK_ID}")
    print(f"- mode: {mode}")
    print(f"- target: {DIRTY_MATCH_ID}")
    print(f"- correct_id: {CORRECT_MATCH_ID}")
    print(f"- ok: {report.get('ok')}")
    if report.get("errors"):
        print("- errors:")
        for error in report["errors"]:
            print(f"  - {error}")
    print(f"- correct_pre_kickoff_predictions: {state.get('correct_pre_kickoff_predictions')}")
    print(f"- bets_with_dirty_match_id: {state.get('bets_with_dirty_match_id')}")
    print(f"- script_predictions: {state.get('script_predictions')}")
    print(f"- script_predictions_count: {state.get('script_predictions_count')}")
    print("- matched_rows:")
    for table in MATCH_ID_TABLES:
        value = state.get("dirty_counts", {}).get(table)
        print(f"  - {table}: {value}")
    if mode == "dry-run":
        print("- action: no rows deleted")
        return
    print(f"- backup_file: {report.get('backup_file')}")
    print("- deleted_rows:")
    for table in DELETE_ORDER:
        print(f"  - {table}: {report.get('deleted', {}).get(table)}")
    print("- verification:")
    if after:
        for table in MATCH_ID_TABLES:
            print(f"  - {table}: {after.get('dirty_counts', {}).get(table)}")
        print(f"  - correct_match_exists: {bool(after.get('correct_match'))}")
        print(f"  - correct_pre_kickoff_predictions: {after.get('correct_pre_kickoff_predictions')}")
        print(f"  - spain_saudi_identity_count: {after.get('split_identity_count')}")
        print(f"  - script_predictions: {after.get('script_predictions')}")
    print(f"- rollback: {report.get('rollback')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely delete dirty match_id 500--1 after protecting 500-1359210.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--confirm", action="store_true")
    parser.add_argument("--confirm-token")
    args = parser.parse_args(argv)

    if args.dry_run:
        report = dry_run()
        print_report(report, mode="dry-run")
        return 0 if report["ok"] else 1

    if args.confirm_token != CONFIRM_TOKEN:
        raise SystemExit(f"--confirm-token must be {CONFIRM_TOKEN}")
    report = run_delete()
    print_report(report, mode="confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
