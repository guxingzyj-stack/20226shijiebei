from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from model.config import get_database_url


def get_conn() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


def fetch_latest_odds_snapshots(conn: psycopg.Connection, limit: int = 5) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, match_id, play_type, odds, source, fetched_at
            FROM odds_snapshots
            ORDER BY fetched_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def fetch_upcoming_matches(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status
            FROM matches
            WHERE status = 'scheduled' AND kickoff_at >= now()
            ORDER BY kickoff_at
            """
        )
        return list(cur.fetchall())


def insert_model_version(conn: psycopg.Connection, name: str, params: dict[str, Any] | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO model_versions (name, params) VALUES (%s, %s) RETURNING id",
            (name, Jsonb(params or {})),
        )
        model_version_id = cur.fetchone()[0]
    conn.commit()
    return int(model_version_id)


def upsert_team_ratings(conn: psycopg.Connection, ratings: dict[str, float]) -> int:
    with conn.cursor() as cur:
        for team, elo in ratings.items():
            cur.execute(
                """
                INSERT INTO team_ratings (team, elo, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (team) DO UPDATE SET elo = EXCLUDED.elo, updated_at = now()
                """,
                (team, elo),
            )
    conn.commit()
    return len(ratings)


def fetch_team_ratings(conn: psycopg.Connection) -> dict[str, float]:
    with conn.cursor() as cur:
        cur.execute("SELECT team, elo FROM team_ratings")
        return {team: float(elo) for team, elo in cur.fetchall()}


def fetch_latest_model_version(conn: psycopg.Connection) -> dict[str, Any] | None:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT id, name, params, trained_at
            FROM model_versions
            ORDER BY trained_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_latest_snapshots_for_match(conn: psycopg.Connection, match_id: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (play_type) id, match_id, play_type, goal_line, odds, source, fetched_at
            FROM odds_snapshots
            WHERE match_id = %s
            ORDER BY play_type, fetched_at DESC
            """,
            (match_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def insert_prediction(
    conn: psycopg.Connection,
    match_id: str,
    model_version: int,
    p_home: float,
    p_draw: float,
    p_away: float,
    score_matrix: list[list[float]],
    lambda_home: float,
    lambda_away: float,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions (
              match_id, model_version, p_home, p_draw, p_away, score_matrix, lambda_home, lambda_away
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (match_id, model_version, p_home, p_draw, p_away, Jsonb(score_matrix), lambda_home, lambda_away),
        )
        prediction_id = cur.fetchone()[0]
    conn.commit()
    return int(prediction_id)


def insert_ev_signal(
    conn: psycopg.Connection,
    match_id: str,
    play_type: str,
    selection: str,
    model_prob: float,
    odds: float,
    ev: float,
    snapshot_id: int | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ev_signals (match_id, play_type, selection, model_prob, odds, ev, snapshot_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (match_id, play_type, selection, model_prob, odds, ev, snapshot_id),
        )
        signal_id = cur.fetchone()[0]
    conn.commit()
    return int(signal_id)


def table_count(conn: psycopg.Connection, table: str) -> int:
    allowed = {"matches", "odds_snapshots", "crawl_runs", "team_ratings", "model_versions", "predictions", "ev_signals"}
    if table not in allowed:
        raise ValueError(f"unsupported table: {table}")
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
