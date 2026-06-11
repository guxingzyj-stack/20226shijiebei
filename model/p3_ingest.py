from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from model import db
from model.features import build_team_feature_snapshot


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "p3"
SAMPLE_DIR = DATA_DIR / "samples"
SOURCE = "manual_csv"
SAMPLE_CONFIRM_TOKEN = "IMPORT_SAMPLE_DATA"

SQUAD_FILE = DATA_DIR / "manual_squad_template.csv"
PLAYER_STATS_FILE = DATA_DIR / "manual_player_stats_template.csv"
INJURIES_FILE = DATA_DIR / "manual_injuries_template.csv"
SAMPLE_SQUAD_FILE = SAMPLE_DIR / "sample_squad.csv"
SAMPLE_PLAYER_STATS_FILE = SAMPLE_DIR / "sample_player_stats.csv"
SAMPLE_INJURIES_FILE = SAMPLE_DIR / "sample_injuries.csv"
REAL_SQUAD_FILE = DATA_DIR / "manual_real_squad_template.csv"
REAL_PLAYER_STATS_FILE = DATA_DIR / "manual_real_player_stats_template.csv"
REAL_INJURIES_FILE = DATA_DIR / "manual_real_injuries_template.csv"
REAL_SQUAD_DATA_FILE = DATA_DIR / "manual_real_squad.csv"
REAL_PLAYER_STATS_DATA_FILE = DATA_DIR / "manual_real_player_stats.csv"
REAL_INJURIES_DATA_FILE = DATA_DIR / "manual_real_injuries.csv"
GBM_COVERAGE_THRESHOLD = 0.70
GBM_GRAY_WEIGHT = 0.20

REQUIRED_COLUMNS = {
    "squad": {"player_key", "name", "team", "position", "birth_date", "market_value", "source"},
    "player_stats": {"player_key", "season", "club", "minutes", "goals", "assists", "xg", "xa", "source"},
    "injuries": {"player_key", "team", "status", "injury_type", "expected_return", "source"},
}

REQUIRED_VALUES = {
    "squad": {"player_key", "name", "team"},
    "player_stats": {"player_key", "season"},
    "injuries": {"player_key", "team", "status"},
}
NUMERIC_COLUMNS = {
    "squad": {"market_value"},
    "player_stats": {"minutes", "goals", "assists", "xg", "xa"},
    "injuries": set(),
}
REAL_REQUIRED_COLUMNS = {
    "team",
    "player_name",
    "position",
    "age",
    "club",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "injury_status",
    "source",
    "retrieved_at",
    "confidence",
    "notes",
}
REAL_REQUIRED_VALUES = {"team", "player_name", "source", "retrieved_at", "confidence"}
PERFORMANCE_REQUIRED_COLUMNS = {
    "team",
    "player_name",
    "club",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "source",
    "retrieved_at",
    "confidence",
    "notes",
}
PERFORMANCE_REQUIRED_VALUES = PERFORMANCE_REQUIRED_COLUMNS - {"notes"}
PERFORMANCE_NUMERIC_COLUMNS = {"minutes_recent", "goals_recent", "assists_recent", "xg_recent", "xa_recent"}
REAL_NUMERIC_COLUMNS = {
    "age",
    "minutes_recent",
    "goals_recent",
    "assists_recent",
    "xg_recent",
    "xa_recent",
    "height_cm",
    "caps",
    "national_team_goals",
}
REAL_CONFIDENCE_VALUES = {"high", "medium", "low"}
REAL_TEAM_NAME_ALIASES = {
    "Bosnia And Herzegovina": "Bosnia & Herzegovina",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "Curaçao": "Curacao",
    "Czechia": "Czech Republic",
    "Côte D'Ivoire": "Ivory Coast",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Türkiye": "Turkey",
}


@dataclass(frozen=True)
class ManualData:
    squad: list[dict[str, str]]
    player_stats: list[dict[str, str]]
    injuries: list[dict[str, str]]


def validate(data_dir: Path = DATA_DIR, sample: bool = False) -> dict[str, Any]:
    paths = _paths(data_dir, sample=sample)
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
            rows = [dict(row) for row in reader]
        errors = [] if missing else _validate_rows(name, rows)
        details[name] = {"ok": not missing and not errors, "rows": len(rows), "missing_columns": missing, "errors": errors}
        ok = ok and not missing and not errors
    return {"ok": ok, "sample": sample, "details": details}


def load_manual_data(data_dir: Path = DATA_DIR, sample: bool = False) -> ManualData:
    report = validate(data_dir, sample=sample)
    if not report["ok"]:
        raise ValueError(f"manual CSV validation failed: {report['details']}")
    paths = _paths(data_dir, sample=sample)
    return ManualData(
        squad=_read_rows(paths["squad"]),
        player_stats=_read_rows(paths["player_stats"]),
        injuries=_read_rows(paths["injuries"]),
    )


def import_manual_data(dry_run: bool = False, data_dir: Path = DATA_DIR, sample: bool = False, confirm: str | None = None) -> dict[str, Any]:
    if sample and not dry_run and confirm != SAMPLE_CONFIRM_TOKEN:
        raise ValueError(f"import --sample requires --confirm {SAMPLE_CONFIRM_TOKEN}")
    manual = load_manual_data(data_dir, sample=sample)
    counts = {
        "players": len(manual.squad),
        "player_season_stats": len(manual.player_stats),
        "injuries": len(manual.injuries),
    }
    if dry_run:
        return {"status": "dry_run", "sample": sample, "source": SOURCE, "would_write_db": False, **counts}
    with db.get_conn() as conn:
        written = _write_manual_data(conn, manual)
    return {"status": "imported", "sample": sample, "source": SOURCE, "would_write_db": True, **written}


def build_team_features(dry_run: bool = False, sample: bool = False) -> dict[str, Any]:
    if sample and dry_run:
        manual = load_manual_data(sample=True)
        snapshots = build_feature_snapshots_from_manual_data(manual, ratings={})
        return {
            "status": "dry_run",
            "sample": True,
            "teams": len(snapshots),
            "team_features": len(snapshots),
            "features": snapshots,
            "missing_indicators": _missing_indicators(snapshots),
        }
    with db.get_conn() as conn:
        players = _fetch_players(conn)
        stats = _fetch_player_stats(conn)
        injuries = _fetch_injuries(conn)
        ratings = db.fetch_team_ratings(conn)
        teams = sorted({str(row["team"]).strip() for row in players if str(row.get("team") or "").strip()})
        snapshots = [build_team_feature_snapshot(team, ratings, players, stats, injuries) for team in teams]
        if dry_run:
            return {"status": "dry_run", "sample": sample, "teams": len(teams), "team_features": len(snapshots), "features": snapshots, "missing_indicators": _missing_indicators(snapshots)}
        written = _write_team_features(conn, snapshots)
    return {"status": "built", "teams": len(teams), "team_features": written}


def build_feature_snapshots_from_manual_data(manual: ManualData, ratings: dict[str, float] | None = None) -> list[dict[str, Any]]:
    ratings = ratings or {}
    players = [{**row, "market_value": row.get("market_value")} for row in manual.squad]
    stats = [dict(row) for row in manual.player_stats]
    injuries = [dict(row) for row in manual.injuries]
    teams = sorted({str(row["team"]).strip() for row in players if str(row.get("team") or "").strip()})
    return [build_team_feature_snapshot(team, ratings, players, stats, injuries) for team in teams]


def validate_real(data_dir: Path = DATA_DIR, dry_run: bool = True) -> dict[str, Any]:
    paths = _real_paths(data_dir)
    real_csv_exists = _real_csv_exists(data_dir)
    details: dict[str, Any] = {}
    ok = True
    total_rows = 0
    for name, path in paths.items():
        if not path.exists():
            details[name] = {"ok": False, "rows": 0, "missing_columns": sorted(REAL_REQUIRED_COLUMNS), "errors": [f"missing file: {path}"]}
            ok = False
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(REAL_REQUIRED_COLUMNS - columns)
            rows = [dict(row) for row in reader]
        errors = [] if missing else _validate_real_rows(name, rows)
        total_rows += len(rows)
        details[name] = {"ok": not missing and not errors, "rows": len(rows), "missing_columns": missing, "errors": errors}
        ok = ok and not missing and not errors
    performance_details, performance_ok = _validate_performance_files(data_dir)
    details["performance"] = performance_details
    ok = ok and performance_ok
    status = "no_real_data_csv" if total_rows == 0 and ok else ("ok" if ok else "validation_failed")
    return {
        "ok": ok,
        "status": status,
        "result": "WAIT" if status == "no_real_data_csv" else ("PASS" if ok else "FAIL"),
        "dry_run": dry_run,
        "real_csv_exists": real_csv_exists,
        "rows_validated": total_rows,
        "performance_rows_validated": performance_details["rows"],
        "performance_files": performance_details["files"],
        "would_write_db": False,
        "retrieved_at_coverage": _coverage(details, "retrieved_at", data_dir),
        "confidence_valid": ok and not _confidence_errors(details),
        "details": details,
    }


def build_team_features_real(dry_run: bool = True, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    validation = validate_real(data_dir=data_dir, dry_run=True)
    if not validation["ok"] or validation["rows_validated"] == 0:
        return {
            "status": validation["status"],
            "result": validation["result"],
            "teams": [],
            "feature_preview": [],
            "missing_indicators": {},
            "would_write_db": False,
            "w_gbm": 0,
        }
    rows = _read_real_rows(data_dir)
    manual = _real_rows_to_manual_data(rows)
    snapshots = build_feature_snapshots_from_manual_data(manual, ratings={})
    performance_coverage = _performance_coverage(rows)
    gbm_ready = _gbm_coverage_ready(performance_coverage)
    return {
        "status": "dry_run" if dry_run else "not_enabled",
        "result": "PASS",
        "teams": [row["team"] for row in snapshots],
        "feature_preview": snapshots,
        "missing_indicators": _missing_indicators(snapshots),
        "would_write_db": False,
        "performance_coverage": performance_coverage,
        "gbm_ready": gbm_ready,
        "w_gbm": 0 if dry_run else (GBM_GRAY_WEIGHT if gbm_ready else 0),
    }


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


def _paths(data_dir: Path, sample: bool = False) -> dict[str, Path]:
    if sample:
        return {
            "squad": SAMPLE_SQUAD_FILE,
            "player_stats": SAMPLE_PLAYER_STATS_FILE,
            "injuries": SAMPLE_INJURIES_FILE,
        }
    return {
        "squad": data_dir / SQUAD_FILE.name,
        "player_stats": data_dir / PLAYER_STATS_FILE.name,
        "injuries": data_dir / INJURIES_FILE.name,
    }


def _real_paths(data_dir: Path) -> dict[str, Path]:
    data_paths = {
        "squad": data_dir / REAL_SQUAD_DATA_FILE.name,
        "player_stats": data_dir / REAL_PLAYER_STATS_DATA_FILE.name,
        "injuries": data_dir / REAL_INJURIES_DATA_FILE.name,
    }
    if any(path.exists() for path in data_paths.values()):
        return data_paths
    return {
        "squad": data_dir / REAL_SQUAD_FILE.name,
        "player_stats": data_dir / REAL_PLAYER_STATS_FILE.name,
        "injuries": data_dir / REAL_INJURIES_FILE.name,
    }


def _real_csv_exists(data_dir: Path) -> bool:
    return any(
        (data_dir / name).exists()
        for name in (
            REAL_SQUAD_DATA_FILE.name,
            REAL_PLAYER_STATS_DATA_FILE.name,
            REAL_INJURIES_DATA_FILE.name,
        )
    )


def _performance_paths(data_dir: Path) -> list[Path]:
    return sorted(data_dir.glob("real_performance_*.csv"))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _empty_to_none(value: Any) -> Any:
    value = "" if value is None else str(value).strip()
    return value or None


def _validate_rows(name: str, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        for column in REQUIRED_VALUES[name]:
            if not str(row.get(column) or "").strip():
                errors.append(f"{name}:{index}: missing required {column}")
        for column in NUMERIC_COLUMNS[name]:
            value = str(row.get(column) or "").strip()
            if value:
                try:
                    float(value)
                except ValueError:
                    errors.append(f"{name}:{index}: invalid numeric {column}")
    return errors


def _validate_real_rows(name: str, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        for column in REAL_REQUIRED_VALUES:
            if not str(row.get(column) or "").strip():
                errors.append(f"{name}:{index}: missing required {column}")
        confidence = str(row.get("confidence") or "").strip().lower()
        if confidence and confidence not in REAL_CONFIDENCE_VALUES:
            errors.append(f"{name}:{index}: confidence must be high, medium, or low")
        for column in REAL_NUMERIC_COLUMNS:
            value = str(row.get(column) or "").strip()
            if value:
                try:
                    float(value)
                except ValueError:
                    errors.append(f"{name}:{index}: invalid numeric {column}")
    return errors


def _validate_performance_files(data_dir: Path) -> tuple[dict[str, Any], bool]:
    paths = _performance_paths(data_dir)
    if not paths:
        return {"ok": True, "rows": 0, "files": [], "missing_columns": [], "errors": []}, True
    rows_total = 0
    errors: list[str] = []
    missing_columns: list[str] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(PERFORMANCE_REQUIRED_COLUMNS - columns)
            if missing:
                missing_columns.extend(f"{path.name}:{column}" for column in missing)
                continue
            rows = [dict(row) for row in reader]
        rows_total += len(rows)
        errors.extend(_validate_performance_rows(path.name, rows))
    ok = not missing_columns and not errors
    return {
        "ok": ok,
        "rows": rows_total,
        "files": [path.name for path in paths],
        "missing_columns": missing_columns,
        "errors": errors,
    }, ok


def _validate_performance_rows(filename: str, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        for column in PERFORMANCE_REQUIRED_VALUES:
            if not str(row.get(column) or "").strip():
                errors.append(f"{filename}:{index}: missing required {column}")
        confidence = str(row.get("confidence") or "").strip().lower()
        if confidence and confidence not in REAL_CONFIDENCE_VALUES:
            errors.append(f"{filename}:{index}: confidence must be high, medium, or low")
        for column in PERFORMANCE_NUMERIC_COLUMNS:
            value = str(row.get(column) or "").strip()
            if not value:
                errors.append(f"{filename}:{index}: missing required numeric {column}")
                continue
            try:
                float(value)
            except ValueError:
                errors.append(f"{filename}:{index}: invalid numeric {column}")
    return errors


def _coverage(details: dict[str, Any], column: str, data_dir: Path) -> dict[str, int]:
    coverage: dict[str, int] = {}
    for name, detail in details.items():
        if detail.get("missing_columns"):
            coverage[name] = 0
            continue
        path = _real_paths(data_dir).get(name)
        if not path or not path.exists():
            coverage[name] = 0
            continue
        rows = _read_rows(path)
        coverage[name] = sum(1 for row in rows if str(row.get(column) or "").strip())
    return coverage


def _confidence_errors(details: dict[str, Any]) -> bool:
    return any("confidence must be high, medium, or low" in error for detail in details.values() for error in detail.get("errors", []))


def _read_real_rows(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    paths = _real_paths(data_dir)
    rows = {name: _read_rows(path) for name, path in paths.items()}
    performance: list[dict[str, str]] = []
    for path in _performance_paths(data_dir):
        performance.extend(_read_rows(path))
    rows["performance"] = performance
    return rows


def _real_rows_to_manual_data(rows: dict[str, list[dict[str, str]]]) -> ManualData:
    squad = []
    stats = []
    injuries = []
    seen_players: set[str] = set()
    for section_rows in rows.values():
        for row in section_rows:
            player_key = _real_player_key(row)
            if not player_key:
                continue
            if player_key not in seen_players:
                seen_players.add(player_key)
                team = _project_team_name(row.get("team", ""))
                squad.append(
                    {
                        "player_key": player_key,
                        "name": row.get("player_name", ""),
                        "team": team,
                        "position": row.get("position", ""),
                        "birth_date": "",
                        "age": row.get("age", ""),
                        "height_cm": row.get("height_cm", ""),
                        "caps": row.get("caps", ""),
                        "national_team_goals": row.get("national_team_goals", ""),
                        "market_value": "",
                        "source": row.get("source", ""),
                    }
                )
            if _has_any_recent_performance(row):
                stats.append(
                    {
                        "player_key": player_key,
                        "season": "recent",
                        "club": row.get("club", ""),
                        "minutes": row.get("minutes_recent", ""),
                        "goals": row.get("goals_recent", ""),
                        "assists": row.get("assists_recent", ""),
                        "xg": row.get("xg_recent", ""),
                        "xa": row.get("xa_recent", ""),
                        "source": row.get("source", ""),
                    }
                )
            if str(row.get("injury_status") or "").strip():
                injuries.append(
                    {
                        "player_key": player_key,
                        "team": _project_team_name(row.get("team", "")),
                        "status": row.get("injury_status", ""),
                        "injury_type": "",
                        "expected_return": "",
                        "source": row.get("source", ""),
                    }
                )
    return ManualData(squad=squad, player_stats=stats, injuries=injuries)


def _real_player_key(row: dict[str, str]) -> str:
    team = _project_team_name(row.get("team", "")).lower().replace(" ", "_").replace("&", "and")
    player = str(row.get("player_name") or "").strip().lower().replace(" ", "_")
    return f"real_{team}_{player}" if team and player else ""


def _project_team_name(value: str | None) -> str:
    text = str(value or "").strip()
    return REAL_TEAM_NAME_ALIASES.get(text, text)


def _has_any_recent_performance(row: dict[str, str]) -> bool:
    return any(str(row.get(column) or "").strip() for column in PERFORMANCE_NUMERIC_COLUMNS)


def _has_complete_recent_performance(row: dict[str, str]) -> bool:
    return all(_parse_number(row.get(column)) is not None for column in PERFORMANCE_NUMERIC_COLUMNS)


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _performance_coverage(rows: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    squad_rows = rows.get("squad", [])
    performance_rows = [row for row in rows.get("performance", []) if _has_complete_recent_performance(row)]
    squad_by_team: dict[str, set[str]] = {}
    performance_by_team: dict[str, set[str]] = {}
    for row in squad_rows:
        team = _project_team_name(row.get("team", ""))
        player = _real_player_key(row)
        if team and player:
            squad_by_team.setdefault(team, set()).add(player)
    for row in performance_rows:
        team = _project_team_name(row.get("team", ""))
        player = _real_player_key(row)
        if team and player:
            performance_by_team.setdefault(team, set()).add(player)

    teams: dict[str, dict[str, Any]] = {}
    for team in sorted(squad_by_team):
        total = len(squad_by_team[team])
        complete = len(squad_by_team[team] & performance_by_team.get(team, set()))
        ratio = complete / total if total else 0.0
        teams[team] = {"players": total, "complete": complete, "ratio": ratio, "meets_threshold": ratio >= GBM_COVERAGE_THRESHOLD}
    ready_teams = sum(1 for row in teams.values() if row["meets_threshold"])
    return {
        "threshold": GBM_COVERAGE_THRESHOLD,
        "teams_total": len(teams),
        "teams_ready": ready_teams,
        "all_teams_ready": bool(teams) and ready_teams == len(teams),
        "teams": teams,
    }


def _gbm_coverage_ready(performance_coverage: dict[str, Any]) -> bool:
    return bool(performance_coverage.get("all_teams_ready"))


def _missing_indicators(snapshots: list[dict[str, Any]]) -> dict[str, list[str]]:
    indicators: dict[str, list[str]] = {}
    for snapshot in snapshots:
        indicators[str(snapshot["team"])] = sorted(key for key, value in snapshot.items() if key.startswith("missing_") and value is True)
    return indicators


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 manual CSV ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--sample", action="store_true")
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--sample", action="store_true")
    import_parser.add_argument("--confirm")
    build_parser = subparsers.add_parser("build-team-features")
    build_parser.add_argument("--dry-run", action="store_true")
    build_parser.add_argument("--sample", action="store_true")
    validate_real_parser = subparsers.add_parser("validate-real")
    validate_real_parser.add_argument("--dry-run", action="store_true")
    build_real_parser = subparsers.add_parser("build-team-features-real")
    build_real_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate(sample=args.sample)
    elif args.command == "import":
        result = import_manual_data(dry_run=args.dry_run, sample=args.sample, confirm=args.confirm)
    elif args.command == "build-team-features":
        result = build_team_features(dry_run=args.dry_run, sample=args.sample)
    elif args.command == "validate-real":
        result = validate_real(dry_run=args.dry_run)
    elif args.command == "build-team-features-real":
        result = build_team_features_real(dry_run=args.dry_run)
    else:
        parser.error(f"unknown command: {args.command}")
    print(json.dumps(result, ensure_ascii=True, default=str))
    return 0 if result.get("ok", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
