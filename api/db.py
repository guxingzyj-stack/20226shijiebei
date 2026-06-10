from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv


DATABASE_URL_MESSAGE = "DATABASE_URL is required"


def get_database_url() -> str:
    load_dotenv()
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError(DATABASE_URL_MESSAGE)
    return value


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(get_database_url()) as conn:
        yield conn


class Database:
    def create_user(self, username: str, password_hash: str) -> dict[str, Any]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id, username, password_hash, balance
                """,
                (username, password_hash),
            )
            return dict(cur.fetchone())

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, username, password_hash, balance FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, username, balance FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_matches(self, status: str = "upcoming") -> list[dict[str, Any]]:
        status_filter = "scheduled" if status == "upcoming" else status
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status, ht_home, ht_away
                FROM matches
                WHERE status = %s
                ORDER BY kickoff_at
                """,
                (status_filter,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status, ht_home, ht_away
                FROM matches
                WHERE match_id = %s
                """,
                (match_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def latest_odds_by_match(self, match_id: str) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
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

    def latest_prediction(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, match_id, model_version, p_home, p_draw, p_away,
                       score_matrix, lambda_home, lambda_away, created_at
                FROM predictions
                WHERE match_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (match_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def latest_ev_signals(self, match_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, play_type, selection, model_prob, odds, ev, snapshot_id, created_at
                FROM ev_signals
                WHERE match_id = %s
                ORDER BY ev DESC, created_at DESC
                LIMIT %s
                """,
                (match_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def odds_history(self, match_id: str, play_type: str | None = None) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if play_type:
                cur.execute(
                    """
                    SELECT id, match_id, play_type, goal_line, odds, source, fetched_at
                    FROM odds_snapshots
                    WHERE match_id = %s AND play_type = %s
                    ORDER BY fetched_at
                    """,
                    (match_id, play_type),
                )
            else:
                cur.execute(
                    """
                    SELECT id, match_id, play_type, goal_line, odds, source, fetched_at
                    FROM odds_snapshots
                    WHERE match_id = %s
                    ORDER BY fetched_at
                    """,
                    (match_id,),
                )
            return [dict(row) for row in cur.fetchall()]

    def latest_odds(self, match_id: str, play_type: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, match_id, play_type, goal_line, odds, source, fetched_at
                FROM odds_snapshots
                WHERE match_id = %s AND play_type = %s
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (match_id, play_type),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_bet(
        self,
        user_id: int,
        legs: list[dict[str, Any]],
        parlay: str,
        stake: Decimal,
        potential_payout: Decimal,
    ) -> dict[str, Any]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("user not found")
            balance = Decimal(str(row["balance"]))
            if balance < stake:
                raise ValueError("insufficient balance")
            cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (stake, user_id))
            cur.execute(
                """
                INSERT INTO bets (user_id, legs, parlay, stake, potential_payout)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, legs, parlay, stake, potential_payout, status
                """,
                (user_id, Jsonb(legs), parlay, stake, potential_payout),
            )
            bet = dict(cur.fetchone())
            cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            bet["balance"] = cur.fetchone()["balance"]
            return bet

    def list_user_bets(self, user_id: int) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, legs, parlay, stake, potential_payout, status, payout, placed_at, settled_at
                FROM bets
                WHERE user_id = %s
                ORDER BY placed_at DESC
                """,
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def leaderboard(self) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, balance
                FROM users
                ORDER BY balance DESC, id
                LIMIT 50
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def best_ev_signal(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, play_type, selection, model_prob, odds, ev
                FROM ev_signals
                WHERE match_id = %s AND ev > 0
                ORDER BY ev DESC, created_at DESC
                LIMIT 1
                """,
                (match_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_db() -> Database:
    return Database()
