from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from model import db
from model.features import build_team_feature_snapshot


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
SOURCE = "manual_csv"

SQUAD_FILE = DATA_DIR / "manual_squad_template.csv"
PLAYER_STATS_FILE = DATA_DIR / "manual_player_stats_template.csv"
INJURIES_FILE = DATA_DIR / "manual_injuries_template.csv"

REQUIRED_COLUMNS = {
    "squad": {"player_key", "name", "team", "position", "birth_date", "market_value", "source"},
    "player_stats": {"player_key", "season", "club", "minutes", "goals", "assists", "xg", "xa", "source"},
    "injuries": {"player_key", "team", "status", "injury_type", "expected_return", "source"},
}


@dataclass(frozen=True)
class ManualData:
    squad: list[dict[str, str]]
    player_stats: list[dict[str, str]]
    injuries: list[dict[str, str]]


def validate(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    paths = _paths(data_dir)
    details: dict[str, Any] = {}
    ok = True
    for name, path in paths.items():
        if not path.exists():
            details[name] = {"ok": False, "error": f"missing file: {path}"}
            ok = False
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_COLUMNS[name] - columns)
            row_count = sum(1 for _ in reader)
        details[name] = {"ok": not missing, "rows": row_count, "missing_columns": missing}
        ok = ok and not missing
    return {"ok": ok, "details": details}


def load_manual_data(data_dir: Path = DATA_DIR) -> ManualData:
    report = validate(data_dir)
    if not report["ok"]:
        raise ValueError(f"manual CSV validation failed: {report['details']}")
    paths = _paths(data_dir)
    return ManualData(
        squad=_read_rows(paths["squad"]),
        player_stats=_read_rows(paths["player_stats"]),
        injuries=_read_rows(paths["injuries"]),
    )


def import_manual_data(dry_run: bool = False, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    manual = load_manual_data(data_dir)
    counts = {
        "players": len(manual.squad),
        "player_season_stats": len(manual.player_stats),
        "injuries": len(manual.injuries),
    }
    if dry_run:
        return {"status": "dry_run", "source": SOURCE, **counts}
    with db.get_conn() as conn:
        written = _write_manual_data(conn, manual)
    return {"status": "imported", "source": SOURCE, **written}


def build_team_features(dry_run: bool = False) -> dict[str, Any]:
    with db.get_conn() as conn:
        players = _fetch_players(conn)
        stats = _fetch_player_stats(conn)
        injuries = _fetch_injuries(conn)
        ratings = db.fetch_team_ratings(conn)
        teams = sorted({str(row["team"]).strip() for row in players if str(row.get("team") or "").strip()})
        snapshots = [build_team_feature_snapshot(team, ratings, players, stats, injuries) for team in teams]
        if dry_run:
            return {"status": "dry_run", "teams": len(teams), "team_features": len(snapshots)}
        written = _write_team_features(conn, snapshots)
    return {"status": "built", "teams": len(teams), "team_features": written}


def _write_manual_data(conn: psycopg.Connection, manual: ManualData) -> dict[str, int]:
    with conn.cursor() as cur:
        for row in manual.squad:
            cur.execute(
                """
                INSERT INTO players (player_key, name, team, position, birth_date, source, raw, updated_at)
                VALUES (%s, %s, %s, %s, NULLIF(%s, '')::date, %s, %s, now())
                ON CONFLICT (player_key) DO UPDATE SET
                  name = EXCLUDED.name,
                  team = EXCLUDED.team,
                  position = EXCLUDED.position,
                  birth_date = EXCLUDED.birth_date,
                  source = EXCLUDED.source,
                  raw = EXCLUDED.raw,
                  updated_at = now()
                """,
                (
                    row["player_key"],
                    row["name"],
                    _empty_to_none(row.get("team")),
                    _empty_to_none(row.get("position")),
                    row.get("birth_date", ""),
                    SOURCE,
                    Jsonb({**row, "source": SOURCE}),
                ),
            )
        for row in manual.player_stats:
            cur.execute(
                """
                INSERT INTO player_season_stats (
                  player_key, season, club, minutes, goals, assists, xg, xa, source, raw, updated_at
                )
                VALUES (%s, %s, %s, NULLIF(%s, '')::numeric, NULLIF(%s, '')::numeric,
                        NULLIF(%s, '')::numeric, NULLIF(%s, '')::numeric, NULLIF(%s, '')::numeric,
                        %s, %s, now())
                ON CONFLICT (player_key, season, club, source) DO UPDATE SET
                  minutes = EXCLUDED.minutes,
                  goals = EXCLUDED.goals,
                  assists = EXCLUDED.assists,
                  xg = EXCLUDED.xg,
                  xa = EXCLUDED.xa,
                  raw = EXCLUDED.raw,
                  updated_at = now()
                """,
                (
                    row["player_key"],
                    row["season"],
                    _empty_to_none(row.get("club")),
                    row.get("minutes", ""),
                    row.get("goals", ""),
                    row.get("assists", ""),
                    row.get("xg", ""),
                    row.get("xa", ""),
                    SOURCE,
                    Jsonb({**row, "source": SOURCE}),
                ),
            )
        cur.execute("DELETE FROM injuries WHERE source = %s", (SOURCE,))
        for row in manual.injuries:
            cur.execute(
                """
                INSERT INTO injuries (player_key, team, status, injury_type, expected_return, source, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    row["player_key"],
                    _empty_to_none(row.get("team")),
                    _empty_to_none(row.get("status")),
                    _empty_to_none(row.get("injury_type")),
                    _empty_to_none(row.get("expected_return")),
                    SOURCE,
                    Jsonb({**row, "source": SOURCE}),
                ),
            )
    conn.commit()
    return {"players": len(manual.squad), "player_season_stats": len(manual.player_stats), "injuries": len(manual.injuries)}


def _write_team_features(conn: psycopg.Connection, snapshots: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        for snapshot in snapshots:
            cur.execute(
                """
                INSERT INTO team_features (
                  team, squad_value_total, squad_value_median, core_minutes_share, core_xg_xa_per90,
                  avg_age, injured_core_count, elo, elo_adjustment, features, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s)
                """,
                (
                    snapshot["team"],
                    snapshot["squad_value_total"],
                    snapshot["squad_value_median"],
                    snapshot["core_minutes_share"],
                    snapshot["core_xg_xa_per90"],
                    snapshot["avg_age"],
                    int(snapshot["injured_core_count"]),
                    snapshot["elo"],
                    Jsonb({key: snapshot[key] for key in snapshot if key != "team"}),
                    SOURCE,
                ),
            )
    conn.commit()
    return len(snapshots)


def _fetch_players(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT player_key, name, team, position, birth_date, source, raw,
                   raw->>'market_value' AS market_value
            FROM players
            WHERE source = %s
            """,
            (SOURCE,),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_player_stats(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT player_key, season, club, minutes, goals, assists, xg, xa, source, raw
            FROM player_season_stats
            WHERE source = %s
            """,
            (SOURCE,),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_injuries(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT player_key, team, status, injury_type, expected_return, source, raw
            FROM injuries
            WHERE source = %s
            """,
            (SOURCE,),
        )
        return [dict(row) for row in cur.fetchall()]


def _paths(data_dir: Path) -> dict[str, Path]:
    return {
        "squad": data_dir / SQUAD_FILE.name,
        "player_stats": data_dir / PLAYER_STATS_FILE.name,
        "injuries": data_dir / INJURIES_FILE.name,
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _empty_to_none(value: Any) -> Any:
    value = "" if value is None else str(value).strip()
    return value or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 manual CSV ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--dry-run", action="store_true")
    build_parser = subparsers.add_parser("build-team-features")
    build_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate()
    elif args.command == "import":
        result = import_manual_data(dry_run=args.dry_run)
    elif args.command == "build-team-features":
        result = build_team_features(dry_run=args.dry_run)
    else:
        parser.error(f"unknown command: {args.command}")
    print(result)
    return 0 if result.get("ok", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
