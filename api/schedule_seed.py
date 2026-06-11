from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from psycopg.rows import dict_row

from api.db import connect


SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "data" / "schedule" / "worldcup2026_schedule.csv"
EXPECTED_ROWS = 104
IMPORT_CONFIRM = "IMPORT_WC26_SCHEDULE"
LEAGUE = "世界杯"
SEED_STATUS = "no_market"


@dataclass(frozen=True)
class ScheduleRow:
    match_id: str
    match_num: str
    stage: str
    group_name: str | None
    home_team: str
    away_team: str
    kickoff_at: datetime
    venue: str
    status: str


def load_schedule_rows(path: Path = SCHEDULE_PATH) -> list[ScheduleRow]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        return [_row_from_csv(row) for row in reader]


def validate_schedule_rows(rows: Iterable[ScheduleRow]) -> list[str]:
    rows = list(rows)
    errors: list[str] = []
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"expected {EXPECTED_ROWS} rows, got {len(rows)}")
    _require_unique(errors, "match_id", [row.match_id for row in rows])
    _require_unique(errors, "match_num", [row.match_num for row in rows])
    for row in rows:
        if not row.match_id.startswith("wc26-"):
            errors.append(f"{row.match_num}: match_id must start with wc26-")
        if not re.fullmatch(r"M\d{3}", row.match_num):
            errors.append(f"{row.match_id}: match_num must look like M001")
        if row.status != SEED_STATUS:
            errors.append(f"{row.match_id}: status must be {SEED_STATUS}")
        if row.kickoff_at.tzinfo is None:
            errors.append(f"{row.match_id}: kickoff_at must be timezone aware")
        if not row.home_team or not row.away_team:
            errors.append(f"{row.match_id}: teams are required")
    return errors


def build_import_plan(rows: list[ScheduleRow], existing_matches: list[dict[str, Any]]) -> dict[str, Any]:
    existing_by_id = {str(row["match_id"]): row for row in existing_matches}
    equivalent_by_seed = _find_equivalent_existing_matches(rows, existing_matches)
    would_insert: list[str] = []
    would_update_seed: list[str] = []
    would_update_existing: list[dict[str, str]] = []
    for row in rows:
        if row.match_id in existing_by_id:
            would_update_seed.append(row.match_id)
            continue
        equivalent = equivalent_by_seed.get(row.match_id)
        if equivalent:
            would_update_existing.append({"seed_match_id": row.match_id, "existing_match_id": str(equivalent["match_id"])})
            continue
        would_insert.append(row.match_id)
    return {
        "csv_rows": len(rows),
        "would_insert": len(would_insert),
        "would_update_seed": len(would_update_seed),
        "would_update_existing": len(would_update_existing),
        "insert_match_ids": would_insert,
        "update_seed_match_ids": would_update_seed,
        "equivalent_matches": would_update_existing,
    }


def run_import(*, dry_run: bool, confirm: str | None = None, path: Path = SCHEDULE_PATH) -> dict[str, Any]:
    rows = load_schedule_rows(path)
    errors = validate_schedule_rows(rows)
    if errors:
        return {"ok": False, "errors": errors}
    if not dry_run and confirm != IMPORT_CONFIRM:
        return {"ok": False, "errors": [f"import requires --confirm {IMPORT_CONFIRM}"]}

    with connect() as conn:
        existing = _fetch_existing_matches(conn, rows)
        plan = build_import_plan(rows, existing)
        if dry_run:
            return {"ok": True, "mode": "dry-run", "would_write_db": False, **plan}

        with conn.transaction():
            result = _apply_import(conn, rows, existing)
        return {"ok": True, "mode": "run", "would_write_db": True, **result}


def _apply_import(conn, rows: list[ScheduleRow], existing_matches: list[dict[str, Any]]) -> dict[str, Any]:
    equivalent_by_seed = _find_equivalent_existing_matches(rows, existing_matches)
    inserted = 0
    updated_seed = 0
    updated_existing = 0
    with conn.cursor() as cur:
        for row in rows:
            equivalent = equivalent_by_seed.get(row.match_id)
            if equivalent and str(equivalent["match_id"]) != row.match_id:
                cur.execute(
                    """
                    UPDATE matches
                    SET stage = COALESCE(NULLIF(stage, ''), %s),
                        group_name = COALESCE(NULLIF(group_name, ''), %s),
                        updated_at = now()
                    WHERE match_id = %s
                    """,
                    (row.stage, row.group_name, equivalent["match_id"]),
                )
                updated_existing += cur.rowcount
                continue

            cur.execute(
                """
                INSERT INTO matches (
                  match_id, match_num, league, home_team, away_team, kickoff_at, stage, group_name,
                  result_home, result_away, status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, now())
                ON CONFLICT (match_id) DO UPDATE SET
                  match_num = EXCLUDED.match_num,
                  league = EXCLUDED.league,
                  home_team = EXCLUDED.home_team,
                  away_team = EXCLUDED.away_team,
                  kickoff_at = EXCLUDED.kickoff_at,
                  stage = EXCLUDED.stage,
                  group_name = EXCLUDED.group_name,
                  status = CASE
                    WHEN matches.status IN ('scheduled', 'closed', 'finished', 'completed', 'postponed') THEN matches.status
                    ELSE EXCLUDED.status
                  END,
                  updated_at = now()
                RETURNING (xmax = 0) AS inserted
                """,
                (
                    row.match_id,
                    row.match_num,
                    LEAGUE,
                    row.home_team,
                    row.away_team,
                    row.kickoff_at,
                    row.stage,
                    row.group_name,
                    row.status,
                ),
            )
            was_inserted = bool(cur.fetchone()[0])
            if was_inserted:
                inserted += 1
            else:
                updated_seed += 1
    return {
        "csv_rows": len(rows),
        "inserted": inserted,
        "updated_seed": updated_seed,
        "updated_existing": updated_existing,
    }


def _fetch_existing_matches(conn, rows: list[ScheduleRow]) -> list[dict[str, Any]]:
    start = min(row.kickoff_at for row in rows) - timedelta(minutes=5)
    end = max(row.kickoff_at for row in rows) + timedelta(minutes=5)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, kickoff_at, status, stage, group_name
            FROM matches
            WHERE kickoff_at BETWEEN %s AND %s
               OR match_id LIKE 'wc26-%%'
            """,
            (start, end),
        )
        return [dict(row) for row in cur.fetchall()]


def _find_equivalent_existing_matches(rows: list[ScheduleRow], existing_matches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    matches_by_kickoff: dict[datetime, list[dict[str, Any]]] = {}
    for existing in existing_matches:
        kickoff = _coerce_datetime(existing.get("kickoff_at"))
        if kickoff is None:
            continue
        matches_by_kickoff.setdefault(kickoff, []).append(existing)

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        for existing in matches_by_kickoff.get(row.kickoff_at, []):
            if str(existing.get("match_id")) == row.match_id:
                result[row.match_id] = existing
                break
            if _canonical_team(row.home_team) == _canonical_team(str(existing.get("home_team") or "")) and _canonical_team(row.away_team) == _canonical_team(
                str(existing.get("away_team") or "")
            ):
                result[row.match_id] = existing
                break
    return result


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _row_from_csv(row: dict[str, str]) -> ScheduleRow:
    return ScheduleRow(
        match_id=(row.get("match_id") or "").strip(),
        match_num=(row.get("match_num") or "").strip(),
        stage=(row.get("stage") or "").strip(),
        group_name=(row.get("group_name") or "").strip() or None,
        home_team=(row.get("home_team") or "").strip(),
        away_team=(row.get("away_team") or "").strip(),
        kickoff_at=_coerce_datetime((row.get("kickoff_at") or "").strip()) or datetime.min.replace(tzinfo=timezone.utc),
        venue=(row.get("venue") or "").strip(),
        status=(row.get("status") or "").strip(),
    )


def _require_unique(errors: list[str], field: str, values: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        errors.append(f"{field} has duplicates: {', '.join(sorted(duplicates))}")


TEAM_ALIASES = {
    "墨西哥": "mexico",
    "南非": "southafrica",
    "韩国": "southkorea",
    "捷克": "czechrepublic",
    "加拿大": "canada",
    "波黑": "bosniaherzegovina",
    "美国": "usa",
    "巴拉圭": "paraguay",
    "卡塔尔": "qatar",
    "瑞士": "switzerland",
    "巴西": "brazil",
    "摩洛哥": "morocco",
    "海地": "haiti",
    "苏格兰": "scotland",
    "澳大利亚": "australia",
    "土耳其": "turkey",
    "德国": "germany",
    "库拉索": "curacao",
    "荷兰": "netherlands",
    "日本": "japan",
    "科特迪瓦": "ivorycoast",
    "厄瓜多尔": "ecuador",
    "瑞典": "sweden",
    "突尼斯": "tunisia",
    "西班牙": "spain",
    "佛得角": "capeverde",
    "比利时": "belgium",
    "埃及": "egypt",
    "沙特": "saudiarabia",
    "沙特阿拉伯": "saudiarabia",
    "乌拉圭": "uruguay",
    "伊朗": "iran",
    "新西兰": "newzealand",
    "法国": "france",
    "塞内加尔": "senegal",
    "伊拉克": "iraq",
    "挪威": "norway",
    "阿根廷": "argentina",
    "阿尔及利亚": "algeria",
    "奥地利": "austria",
    "约旦": "jordan",
    "葡萄牙": "portugal",
    "刚果(金)": "drcongo",
    "刚果民主共和国": "drcongo",
    "英格兰": "england",
    "克罗地亚": "croatia",
    "加纳": "ghana",
    "巴拿马": "panama",
    "乌兹别克": "uzbekistan",
    "哥伦比亚": "colombia",
    "czechia": "czechrepublic",
    "czechrepublic": "czechrepublic",
    "unitedstates": "usa",
    "usa": "usa",
    "bosniaherzegovina": "bosniaherzegovina",
    "bosniaandherzegovina": "bosniaherzegovina",
    "curacao": "curacao",
    "curaçao": "curacao",
    "cotedivoire": "ivorycoast",
    "côtedivoire": "ivorycoast",
    "ivorycoast": "ivorycoast",
    "congodr": "drcongo",
    "drcongo": "drcongo",
    "drc": "drcongo",
}


def _canonical_team(value: str) -> str:
    normalized = re.sub(r"[\s\u3000'’.\-&/()]+", "", value).lower()
    normalized = normalized.replace("republic", "republic")
    return TEAM_ALIASES.get(normalized, normalized)


def _print_report(report: dict[str, Any]) -> None:
    print("World Cup 2026 Schedule Seed Report")
    for key, value in report.items():
        if key in {"insert_match_ids", "update_seed_match_ids", "equivalent_matches", "errors"}:
            continue
        print(f"- {key}: {value}")
    if report.get("equivalent_matches"):
        print("- equivalent_matches:")
        for row in report["equivalent_matches"][:20]:
            print(f"  - {row['seed_match_id']} -> {row['existing_match_id']}")
    if report.get("errors"):
        print("- errors:")
        for error in report["errors"]:
            print(f"  - {error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or import the 2026 World Cup full schedule seed.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--confirm")
    args = parser.parse_args(argv)

    if args.command == "validate":
        rows = load_schedule_rows()
        errors = validate_schedule_rows(rows)
        report = {"ok": not errors, "csv_rows": len(rows), "errors": errors}
        _print_report(report)
        return 0 if not errors else 1

    if args.command == "import":
        report = run_import(dry_run=bool(args.dry_run), confirm=args.confirm)
        _print_report(report)
        return 0 if report.get("ok") else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
