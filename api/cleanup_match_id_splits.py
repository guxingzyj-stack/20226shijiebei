from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import make_json_safe
from api.result_source_mapping import normalize_team_name


TASK_ID = "076-cleanup-match-id-splits"
CONFIRM_TOKEN = "DELETE_DRIFTED_500_IDS"
DEFAULT_BACKUP_DIR = Path("output") / "cleanup_match_id_splits"
PROTECTED_500_ID_RE = re.compile(r"^500-1359\d+$")

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


def _collect_state(
    cur: Any,
    tracked_dirty_ids: list[str] | None = None,
    tracked_correct_ids: list[str] | None = None,
) -> dict[str, Any]:
    table_status = {table: table_exists(cur, table) for table in MATCH_ID_TABLES}
    table_status["bets"] = table_exists(cur, "bets")
    table_status["script_predictions"] = table_exists(cur, "script_predictions")

    match_rows = _load_500_matches(cur) if table_status["matches"] else []
    plans = _build_split_plans(match_rows)
    planned_dirty_ids = {dirty_id for plan in plans for dirty_id in plan["dirty_ids"] if plan.get("correct_id")}
    dirty_ids = sorted(planned_dirty_ids | set(tracked_dirty_ids or []))
    correct_ids = sorted({str(plan["correct_id"]) for plan in plans if plan.get("correct_id")} | set(tracked_correct_ids or []))

    dirty_counts = _dirty_counts(cur, table_status, dirty_ids)
    bets_by_dirty_id = _bets_by_dirty_id(cur, dirty_ids) if table_status["bets"] else {dirty_id: 0 for dirty_id in dirty_ids}
    correct_prediction_counts = {
        plan["correct_id"]: _count_correct_pre_kickoff_predictions(cur, plan["correct_id"])
        for plan in plans
        if plan.get("correct_id")
    }
    correct_matches = {match_id: _fetch_one_match(cur, match_id) for match_id in correct_ids}
    script_prediction_count = _count_table(cur, "script_predictions") if table_status["script_predictions"] else "table_not_found_skipped"

    state = {
        "task_id": TASK_ID,
        "table_status": table_status,
        "split_group_count": len(plans),
        "plans": plans,
        "dirty_ids": dirty_ids,
        "dirty_counts": dirty_counts,
        "bets_by_dirty_id": bets_by_dirty_id,
        "correct_matches": correct_matches,
        "correct_pre_kickoff_predictions": correct_prediction_counts,
        "script_predictions_count": script_prediction_count,
        "script_predictions": "untouched",
    }
    state["errors"] = validate_state(state, require_dirty=False)
    return state


def _load_500_matches(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT match_id, match_num, league, home_team, away_team, kickoff_at,
               status, result_home, result_away, ht_home, ht_away
        FROM matches
        WHERE match_id LIKE '500-%%'
        ORDER BY kickoff_at, match_id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _build_split_plans(match_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in match_rows:
        groups[_identity_key(row)].append(row)

    plans: list[dict[str, Any]] = []
    for key, rows in sorted(groups.items(), key=lambda item: item[0]):
        ids = sorted(str(row["match_id"]) for row in rows)
        if len(ids) <= 1:
            continue

        correct_row, selection_error = _select_correct_row(rows)
        correct_id = str(correct_row["match_id"]) if correct_row else None
        dirty_ids = [match_id for match_id in ids if match_id != correct_id] if correct_id else []
        errors = [selection_error] if selection_error else []
        if correct_row:
            errors.extend(_identity_conflict_errors(correct_row, rows))
        plans.append(
            {
                "identity": {"home": key[0], "away": key[1], "kickoff_at": key[2]},
                "match_ids": ids,
                "correct_id": correct_id,
                "dirty_ids": dirty_ids,
                "matches": [_match_summary(row) for row in rows],
                "errors": errors,
            }
        )
    return plans


def _identity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_team_name(row.get("home_team")),
        normalize_team_name(row.get("away_team")),
        _iso(row.get("kickoff_at")),
    )


def _select_correct_row(rows: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    protected = [row for row in rows if PROTECTED_500_ID_RE.match(str(row.get("match_id") or ""))]
    if len(protected) == 1:
        return protected[0], None
    if not protected:
        ids = ", ".join(sorted(str(row.get("match_id")) for row in rows))
        return None, f"no unique protected 500-1359xxx match_id for split group: {ids}"
    ids = ", ".join(sorted(str(row.get("match_id")) for row in protected))
    return None, f"multiple protected 500-1359xxx match_ids in one identity group: {ids}"


def _identity_conflict_errors(correct_row: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    correct_result = (correct_row.get("result_home"), correct_row.get("result_away"))
    for row in rows:
        if row is correct_row:
            continue
        dirty_result = (row.get("result_home"), row.get("result_away"))
        if all(value is not None for value in dirty_result) and all(value is not None for value in correct_result) and dirty_result != correct_result:
            errors.append(f"result conflict: {row.get('match_id')} has {dirty_result}, correct has {correct_result}")
    return errors


def _dirty_counts(cur: Any, table_status: dict[str, bool], dirty_ids: list[str]) -> dict[str, dict[str, int | str]]:
    counts: dict[str, dict[str, int | str]] = {dirty_id: {} for dirty_id in dirty_ids}
    for dirty_id in dirty_ids:
        for table in MATCH_ID_TABLES:
            if not table_status.get(table):
                counts[dirty_id][table] = "table_not_found_skipped"
                continue
            counts[dirty_id][table] = _count_match_id(cur, table, dirty_id)
    return counts


def _count_match_id(cur: Any, table_name: str, match_id: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table_name} WHERE match_id = %s", (match_id,))
    return int(cur.fetchone()["count"])


def _count_table(cur: Any, table_name: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table_name}")
    return int(cur.fetchone()["count"])


def _count_correct_pre_kickoff_predictions(cur: Any, match_id: str) -> int:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM predictions
        WHERE match_id = %s
          AND created_at <= (
            SELECT kickoff_at FROM matches WHERE match_id = %s
          )
        """,
        (match_id, match_id),
    )
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


def _bets_by_dirty_id(cur: Any, dirty_ids: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for dirty_id in dirty_ids:
        cur.execute("SELECT count(*) AS count FROM bets WHERE legs::text LIKE %s", (f"%{dirty_id}%",))
        result[dirty_id] = int(cur.fetchone()["count"])
    return result


def validate_state(state: dict[str, Any], *, require_dirty: bool) -> list[str]:
    errors: list[str] = []
    dirty_ids = list(state.get("dirty_ids") or [])
    if require_dirty and not dirty_ids:
        errors.append("no dirty match_id candidates found")

    for plan in state.get("plans") or []:
        errors.extend(plan.get("errors") or [])
        correct_id = plan.get("correct_id")
        if not correct_id:
            continue
        if int((state.get("correct_pre_kickoff_predictions") or {}).get(correct_id) or 0) < 1:
            errors.append(f"correct match {correct_id} has no pre-kickoff prediction")
        for dirty_id in plan.get("dirty_ids") or []:
            if int((state.get("bets_by_dirty_id") or {}).get(dirty_id) or 0) > 0:
                errors.append(f"bets reference dirty match_id {dirty_id}; refusing to modify bets/users/balance")
    return errors


def create_backup(conn: Any, state: dict[str, Any], backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_file = backup_dir / f"{TASK_ID}_{timestamp}.json"
    dirty_ids = list(state.get("dirty_ids") or [])
    payload: dict[str, Any] = {
        "task_id": TASK_ID,
        "state": state,
        "rows": {},
    }
    with conn.cursor(row_factory=dict_row) as cur:
        for table in MATCH_ID_TABLES:
            if not state["table_status"].get(table):
                payload["rows"][table] = "table_not_found_skipped"
                continue
            cur.execute(f"SELECT * FROM {table} WHERE match_id = ANY(%s) ORDER BY match_id, 1", (dirty_ids,))
            payload["rows"][table] = [dict(row) for row in cur.fetchall()]
    backup_file.write_text(json.dumps(make_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_file


def dry_run() -> dict[str, Any]:
    state = collect_state()
    errors = validate_state(state, require_dirty=False)
    return {
        "ok": not errors,
        "errors": errors,
        "state": state,
        "would_delete": state["dirty_counts"],
    }


def run_delete() -> dict[str, Any]:
    with connect() as conn:
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                state = _collect_state(cur)
                errors = validate_state(state, require_dirty=True)
                if errors:
                    raise RuntimeError("; ".join(errors))

            backup_file = create_backup(conn, state)
            dirty_ids = list(state.get("dirty_ids") or [])
            correct_ids = sorted({str(plan["correct_id"]) for plan in state.get("plans") or [] if plan.get("correct_id")})

            deleted: dict[str, int | str] = {}
            with conn.cursor(row_factory=dict_row) as cur:
                for table in DELETE_ORDER:
                    if not state["table_status"].get(table):
                        deleted[table] = "table_not_found_skipped"
                        continue
                    cur.execute(f"DELETE FROM {table} WHERE match_id = ANY(%s)", (dirty_ids,))
                    deleted[table] = int(cur.rowcount or 0)

                after_state = _collect_state(cur, tracked_dirty_ids=dirty_ids, tracked_correct_ids=correct_ids)
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
    for dirty_id in before_state.get("dirty_ids") or []:
        after_counts = (after_state.get("dirty_counts") or {}).get(dirty_id, {})
        for table, count in after_counts.items():
            if isinstance(count, int) and count != 0:
                errors.append(f"{table} still has {count} rows for {dirty_id}")
    before_correct_ids = {str(plan.get("correct_id")) for plan in before_state.get("plans") or [] if plan.get("correct_id")}
    for match_id in sorted(before_correct_ids):
        if not (after_state.get("correct_matches") or {}).get(match_id):
            errors.append(f"correct match {match_id} missing after delete")
        if int((after_state.get("correct_pre_kickoff_predictions") or {}).get(match_id) or 0) < 1:
            errors.append(f"correct match {match_id} lost pre-kickoff predictions")
    if after_state.get("script_predictions_count") != before_state.get("script_predictions_count"):
        errors.append("script_predictions count changed")
    return errors


def print_report(report: dict[str, Any], *, mode: str) -> None:
    state = report.get("state") or report.get("before") or {}
    print("Cleanup Match ID Splits Report")
    print(f"- task_id: {TASK_ID}")
    print(f"- mode: {mode}")
    print(f"- ok: {report.get('ok')}")
    if report.get("errors"):
        print("- errors:")
        for error in report["errors"]:
            print(f"  - {error}")
    print(f"- split_group_count: {state.get('split_group_count')}")
    print(f"- dirty_ids: {', '.join(state.get('dirty_ids') or []) or 'none'}")
    print(f"- script_predictions: {state.get('script_predictions')}")
    print(f"- script_predictions_count: {state.get('script_predictions_count')}")
    print("- plans:")
    for plan in state.get("plans") or []:
        print(f"  - correct_id: {plan.get('correct_id')}")
        print(f"    dirty_ids: {', '.join(plan.get('dirty_ids') or []) or 'none'}")
        if plan.get("errors"):
            print(f"    errors: {'; '.join(plan['errors'])}")
    if mode == "dry-run":
        print("- action: no rows deleted")
        return
    print(f"- backup_file: {report.get('backup_file')}")
    print("- deleted_rows:")
    for table in DELETE_ORDER:
        print(f"  - {table}: {report.get('deleted', {}).get(table)}")
    print(f"- rollback: {report.get('rollback')}")


def _match_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "match_id": row.get("match_id"),
        "match_num": row.get("match_num"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "kickoff_at": _iso(row.get("kickoff_at")),
        "status": row.get("status"),
        "result_home": row.get("result_home"),
        "result_away": row.get("result_away"),
    }


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely dry-run or delete drifted 500 match_id split rows.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--confirm", action="store_true")
    parser.add_argument("--confirm-token")
    args = parser.parse_args(argv)

    if not args.confirm:
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
