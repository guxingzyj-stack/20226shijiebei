from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from api.db import connect
from api.result_source_mapping import normalize_team_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = Path(__file__).resolve().parent / "script_assets" / "script_predictions_groupstage.json"


def load_script_prediction_file(path: Path = DEFAULT_FILE) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("predictions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("script prediction file must contain a predictions list")
    return [_validate_row(row, index) for index, row in enumerate(rows, start=1)]


def upsert_script_predictions(rows: list[dict[str, Any]]) -> int:
    with connect() as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO script_predictions (
                    grp, stage, home_team, away_team,
                    script_home, script_away, narrative, is_real
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (home_team, away_team, stage) DO UPDATE SET
                    grp = EXCLUDED.grp,
                    script_home = EXCLUDED.script_home,
                    script_away = EXCLUDED.script_away,
                    narrative = EXCLUDED.narrative,
                    is_real = EXCLUDED.is_real
                """,
                (
                    row["grp"],
                    row["stage"],
                    row["home_team"],
                    row["away_team"],
                    row["script_home"],
                    row["script_away"],
                    row.get("narrative"),
                    row.get("is_real", False),
                ),
            )
        conn.commit()
    return len(rows)


def _validate_row(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"row {index} must be an object")
    group_value = row.get("grp", row.get("group"))
    required = {
        "grp": group_value,
        "stage": row.get("stage"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "script_home": row.get("script_home"),
        "script_away": row.get("script_away"),
    }
    missing = [key for key, value in required.items() if value is None or value == ""]
    if missing:
        raise ValueError(f"row {index} missing fields: {', '.join(missing)}")
    try:
        script_home = int(row["script_home"])
        script_away = int(row["script_away"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {index} has invalid script score") from exc
    return {
        "grp": str(group_value).strip().upper(),
        "stage": str(row["stage"]).strip(),
        "home_team": normalize_team_name(row["home_team"]),
        "away_team": normalize_team_name(row["away_team"]),
        "script_home": script_home,
        "script_away": script_away,
        "narrative": str(row.get("narrative") or "").strip() or None,
        "is_real": bool(row.get("is_real", False)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import script-vs-real group-stage predictions.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--dry-run", action="store_true", help="Validate input without writing to the database.")
    args = parser.parse_args(argv)

    rows = load_script_prediction_file(args.file)
    imported = 0 if args.dry_run else upsert_script_predictions(rows)
    print("Script Predictions Import Report")
    print(f"- mode: {'dry-run' if args.dry_run else 'import'}")
    print(f"- file: {args.file}")
    print(f"- rows_loaded: {len(rows)}")
    print(f"- rows_upserted: {imported}")
    print(f"- would_write_db: {not args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
