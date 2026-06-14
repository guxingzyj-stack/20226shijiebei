from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.db import connect
from api.ops_log import sanitize_error


CONFIRM_CODE = "APPLY_OFFICIAL_RESULTS"
JOB_NAME = "official_result_fallback"
REQUIRED_FIELDS = {
    "match_id",
    "home_team",
    "away_team",
    "result_home",
    "result_away",
    "ht_home",
    "ht_away",
    "status",
    "source_name",
    "source_url",
    "retrieved_at",
    "verified_by",
    "notes",
}
ALLOWED_STATUSES = {"finished", "completed"}
UPDATABLE_STATUSES = {"scheduled", "closed", "finished", "completed"}
FORBIDDEN_SOURCE_URL_MARKERS = ("<PASTE", "PLACEHOLDER", "TODO", "这里换成", "example.com")


@dataclass(frozen=True)
class OfficialResultRow:
    match_id: str
    home_team: str
    away_team: str
    result_home: int
    result_away: int
    ht_home: int | None
    ht_away: int | None
    status: str
    source_name: str
    source_url: str
    retrieved_at: str
    verified_by: str
    notes: str


@dataclass(frozen=True)
class PlannedUpdate:
    row: OfficialResultRow
    db_match: dict[str, Any] | None
    action: str
    reason: str


def load_csv(path: str | Path) -> list[OfficialResultRow]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_FIELDS - fieldnames)
        if missing:
            raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
        return [_parse_row(row, index + 2) for index, row in enumerate(reader)]


def plan_updates(rows: list[OfficialResultRow]) -> list[PlannedUpdate]:
    plans: list[PlannedUpdate] = []
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        for row in rows:
            cur.execute(
                """
                SELECT match_id, home_team, away_team, status,
                       result_home, result_away, ht_home, ht_away
                FROM matches
                WHERE match_id = %s
                """,
                (row.match_id,),
            )
            db_match = cur.fetchone()
            if db_match is None:
                plans.append(PlannedUpdate(row, None, "error", "match_id_not_found"))
                continue
            match = dict(db_match)
            if not _team_matches(row.home_team, str(match["home_team"])) or not _team_matches(row.away_team, str(match["away_team"])):
                plans.append(PlannedUpdate(row, match, "error", "team_name_mismatch"))
                continue
            if match["result_home"] is not None or match["result_away"] is not None:
                plans.append(PlannedUpdate(row, match, "skip", "existing_result_not_overwritten"))
                continue
            if str(match["status"]) not in UPDATABLE_STATUSES:
                plans.append(PlannedUpdate(row, match, "skip", "status_not_updatable"))
                continue
            plans.append(PlannedUpdate(row, match, "update", "eligible"))
    return plans


def dry_run(csv_path: str | Path) -> dict[str, Any]:
    rows = load_csv(csv_path)
    plans = plan_updates(rows)
    return _report(plans, updated_count=0, mode="dry-run")


def apply_results(csv_path: str | Path, confirm: str | None) -> dict[str, Any]:
    if confirm != CONFIRM_CODE:
        raise ValueError(f"confirm code required: {CONFIRM_CODE}")
    rows = load_csv(csv_path)
    plans = plan_updates(rows)
    errors = [plan for plan in plans if plan.action == "error"]
    if errors:
        raise ValueError(f"CSV has blocking errors: {', '.join(plan.row.match_id for plan in errors)}")
    updates = [plan for plan in plans if plan.action == "update"]
    started_at = datetime.now(timezone.utc)
    try:
        with connect() as conn, conn.cursor() as cur:
            updated_count = 0
            for plan in updates:
                row = plan.row
                cur.execute(
                    """
                    UPDATE matches
                    SET status = %s,
                        result_home = %s,
                        result_away = %s,
                        ht_home = %s,
                        ht_away = %s
                    WHERE match_id = %s
                      AND status IN ('scheduled', 'closed', 'finished', 'completed')
                      AND result_home IS NULL
                      AND result_away IS NULL
                    """,
                    (
                        row.status,
                        row.result_home,
                        row.result_away,
                        row.ht_home,
                        row.ht_away,
                        row.match_id,
                    ),
                )
                updated_count += cur.rowcount
            cur.execute(
                """
                INSERT INTO ops_log (job_name, status, started_at, finished_at, summary, error)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    JOB_NAME,
                    "ok",
                    started_at,
                    datetime.now(timezone.utc),
                    Jsonb(_summary(plans, updated_count)),
                    None,
                ),
            )
        return _report(plans, updated_count=updated_count, mode="confirm")
    except Exception as exc:
        try:
            _record_error(started_at, sanitize_error(exc))
        except Exception:
            pass
        raise


def print_report(report: dict[str, Any]) -> None:
    print("Official Result Fallback Report")
    print(f"- mode: {report['mode']}")
    print(f"- ok: {report['ok']}")
    print(f"- would_update_count: {report['would_update_count']}")
    print(f"- updated_count: {report['updated_count']}")
    print(f"- error_count: {report['error_count']}")
    print(f"- skipped_count: {report['skipped_count']}")
    print("")
    print("matches:")
    for item in report["matches"]:
        print(f"- match_id: {item['match_id']}")
        print(f"  action: {item['action']}")
        print(f"  reason: {item['reason']}")
        print(f"  before: {item['before']}")
        print(f"  after: {item['after']}")
        print(f"  source_name: {item['source_name']}")
        print(f"  source_url: {item['source_url']}")
        print(f"  retrieved_at: {item['retrieved_at']}")
        print(f"  verified_by: {item['verified_by']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply verified official result fallback CSV")
    parser.add_argument("--csv", required=True, help="path to verified official result CSV")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm")
    args = parser.parse_args(argv)

    try:
        report = dry_run(args.csv) if args.dry_run else apply_results(args.csv, args.confirm)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    return 0 if report["ok"] else 1


def _parse_row(row: dict[str, str], line_no: int) -> OfficialResultRow:
    def required_text(name: str) -> str:
        value = (row.get(name) or "").strip()
        if not value:
            raise ValueError(f"line {line_no}: {name} is required")
        if value.lower() in {"unknown", "guessed", "guess"}:
            raise ValueError(f"line {line_no}: {name} cannot be {value}")
        return value

    match_id = required_text("match_id")
    status = required_text("status").lower()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"line {line_no}: status must be finished or completed")
    return OfficialResultRow(
        match_id=match_id,
        home_team=required_text("home_team"),
        away_team=required_text("away_team"),
        result_home=_required_nonnegative_int(row, "result_home", line_no),
        result_away=_required_nonnegative_int(row, "result_away", line_no),
        ht_home=_optional_nonnegative_int(row, "ht_home", line_no),
        ht_away=_optional_nonnegative_int(row, "ht_away", line_no),
        status=status,
        source_name=required_text("source_name"),
        source_url=_validated_source_url(required_text("source_url"), line_no),
        retrieved_at=required_text("retrieved_at"),
        verified_by=required_text("verified_by"),
        notes=(row.get("notes") or "").strip(),
    )


def _validated_source_url(value: str, line_no: int) -> str:
    lowered = value.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise ValueError(f"line {line_no}: source_url must start with http:// or https://")
    for marker in FORBIDDEN_SOURCE_URL_MARKERS:
        if marker.lower() in lowered:
            raise ValueError(f"line {line_no}: source_url contains placeholder marker")
    return value


def _required_nonnegative_int(row: dict[str, str], name: str, line_no: int) -> int:
    value = (row.get(name) or "").strip()
    if value == "":
        raise ValueError(f"line {line_no}: {name} is required")
    return _parse_nonnegative_int(value, name, line_no)


def _optional_nonnegative_int(row: dict[str, str], name: str, line_no: int) -> int | None:
    value = (row.get(name) or "").strip()
    if value == "":
        return None
    return _parse_nonnegative_int(value, name, line_no)


def _parse_nonnegative_int(value: str, name: str, line_no: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"line {line_no}: {name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"line {line_no}: {name} must be >= 0")
    return parsed


def _team_matches(csv_name: str, db_name: str) -> bool:
    return _normalize_team(csv_name) == _normalize_team(db_name)


def _normalize_team(value: str) -> str:
    return "".join(str(value).lower().split())


def _report(plans: list[PlannedUpdate], updated_count: int, mode: str) -> dict[str, Any]:
    error_count = sum(1 for plan in plans if plan.action == "error")
    skipped_count = sum(1 for plan in plans if plan.action == "skip")
    would_update_count = sum(1 for plan in plans if plan.action == "update")
    return {
        "mode": mode,
        "ok": error_count == 0,
        "would_update_count": would_update_count,
        "updated_count": updated_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "matches": [_plan_item(plan) for plan in plans],
    }


def _summary(plans: list[PlannedUpdate], updated_count: int) -> dict[str, Any]:
    return {
        "would_update_count": sum(1 for plan in plans if plan.action == "update"),
        "updated_count": updated_count,
        "skipped_count": sum(1 for plan in plans if plan.action == "skip"),
        "error_count": sum(1 for plan in plans if plan.action == "error"),
        "match_ids": [plan.row.match_id for plan in plans],
    }


def _plan_item(plan: PlannedUpdate) -> dict[str, Any]:
    before = None
    if plan.db_match is not None:
        before = {
            "status": plan.db_match.get("status"),
            "result_home": plan.db_match.get("result_home"),
            "result_away": plan.db_match.get("result_away"),
            "ht_home": plan.db_match.get("ht_home"),
            "ht_away": plan.db_match.get("ht_away"),
        }
    after = {
        "status": plan.row.status,
        "result_home": plan.row.result_home,
        "result_away": plan.row.result_away,
        "ht_home": plan.row.ht_home,
        "ht_away": plan.row.ht_away,
    }
    return {
        "match_id": plan.row.match_id,
        "action": plan.action,
        "reason": plan.reason,
        "before": before,
        "after": after,
        "source_name": plan.row.source_name,
        "source_url": plan.row.source_url,
        "retrieved_at": plan.row.retrieved_at,
        "verified_by": plan.row.verified_by,
    }


def _record_error(started_at: datetime, error: str) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops_log (job_name, status, started_at, finished_at, summary, error)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (JOB_NAME, "error", started_at, datetime.now(timezone.utc), Jsonb({}), error),
        )


if __name__ == "__main__":
    raise SystemExit(main())
