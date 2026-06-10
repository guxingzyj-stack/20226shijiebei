from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from sources.common import MatchOdds, OddsEntry


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_database_url() -> str:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def start_run(conn: psycopg.Connection, source: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO crawl_runs (started_at, source) VALUES (%s, %s) RETURNING id",
            (datetime.now(timezone.utc), source),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return int(run_id)


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    source: str | None,
    matches_seen: int,
    rows_written: int,
    ok: bool,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE crawl_runs
        SET finished_at = %s, source = %s, matches_seen = %s, rows_written = %s, ok = %s, error = %s
        WHERE id = %s
        """,
        (datetime.now(timezone.utc), source, matches_seen, rows_written, ok, error, run_id),
    )
    conn.commit()


def upsert_matches(conn: psycopg.Connection, matches: Iterable[MatchOdds]) -> None:
    with conn.cursor() as cur:
        for match in matches:
            cur.execute(
                """
                INSERT INTO matches (
                  match_id, match_num, league, home_team, away_team, kickoff_at, stage, group_name,
                  result_home, result_away, status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (match_id) DO UPDATE SET
                  match_num = EXCLUDED.match_num,
                  league = EXCLUDED.league,
                  home_team = EXCLUDED.home_team,
                  away_team = EXCLUDED.away_team,
                  kickoff_at = EXCLUDED.kickoff_at,
                  stage = EXCLUDED.stage,
                  group_name = EXCLUDED.group_name,
                  result_home = EXCLUDED.result_home,
                  result_away = EXCLUDED.result_away,
                  status = EXCLUDED.status,
                  updated_at = now()
                """,
                (
                    match.match_id,
                    match.match_num,
                    match.league,
                    match.home_team,
                    match.away_team,
                    match.kickoff_at,
                    match.stage,
                    match.group_name,
                    match.result_home,
                    match.result_away,
                    match.status,
                ),
            )
    conn.commit()


def write_odds_snapshots(conn: psycopg.Connection, matches: Iterable[MatchOdds], source: str) -> int:
    written = 0
    with conn.cursor() as cur:
        for match in matches:
            for entry in match.odds:
                odds_hash = odds_md5(entry.odds)
                cur.execute(
                    """
                    SELECT odds_hash, fetched_at
                    FROM odds_snapshots
                    WHERE match_id = %s AND play_type = %s
                    ORDER BY fetched_at DESC
                    LIMIT 1
                    """,
                    (match.match_id, entry.play_type),
                )
                latest = cur.fetchone()
                should_insert = latest is None
                if latest is not None:
                    latest_hash, latest_time = latest
                    age_seconds = (datetime.now(timezone.utc) - latest_time).total_seconds()
                    should_insert = latest_hash != odds_hash or age_seconds >= 3600
                if should_insert:
                    _insert_snapshot(cur, match.match_id, entry, odds_hash, source)
                    written += 1
    conn.commit()
    return written


def odds_md5(odds: dict[str, object]) -> str:
    canonical = json.dumps(odds, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()


def _insert_snapshot(cur: psycopg.Cursor, match_id: str, entry: OddsEntry, odds_hash: str, source: str) -> None:
    cur.execute(
        """
        INSERT INTO odds_snapshots (match_id, play_type, goal_line, odds, odds_hash, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (match_id, entry.play_type, entry.goal_line, Jsonb(entry.odds), odds_hash, source),
    )
