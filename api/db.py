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
EV_RESEARCH_ONLY_THRESHOLD = 0.15


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

    def list_matches(self, status: str = "all") -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if status == "upcoming":
                cur.execute(
                    """
                    SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                           result_home, result_away, ht_home, ht_away
                    FROM matches
                    WHERE status IN ('scheduled', 'closed', 'no_market')
                      AND result_home IS NULL
                      AND result_away IS NULL
                    ORDER BY kickoff_at
                    """
                )
            elif status == "finished":
                cur.execute(
                    """
                    SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                           result_home, result_away, ht_home, ht_away
                    FROM matches
                    WHERE status IN ('finished', 'completed')
                    ORDER BY kickoff_at
                    """
                )
            elif status == "all":
                cur.execute(
                    """
                    SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                           result_home, result_away, ht_home, ht_away
                    FROM matches
                    ORDER BY kickoff_at
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                           result_home, result_away, ht_home, ht_away
                    FROM matches
                    WHERE status = %s
                    ORDER BY kickoff_at
                    """,
                    (status,),
                )
            return [dict(row) for row in cur.fetchall()]

    def prediction_history(self, match_id: str) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.match_id,
                       p.created_at,
                       p.model_version,
                       COALESCE(mv.name, p.model_version::text) AS model_version_name,
                       p.p_home,
                       p.p_draw,
                       p.p_away
                FROM predictions p
                LEFT JOIN model_versions mv ON mv.id = p.model_version
                WHERE p.match_id = %s
                ORDER BY p.created_at, p.id
                """,
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                       result_home, result_away, ht_home, ht_away
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
                SELECT match_id, model_version, play_type, selection, model_prob, odds, ev, snapshot_id, research_only, reason, suggestion_eligible, created_at
                FROM (
                  SELECT DISTINCT ON (play_type, selection)
                         match_id, model_version, play_type, selection, model_prob, odds, ev, snapshot_id, research_only, reason, suggestion_eligible, created_at
                  FROM ev_signals
                  WHERE match_id = %s
                    AND model_version = (
                      SELECT p.model_version
                      FROM predictions p
                      WHERE p.match_id = %s
                      ORDER BY p.created_at DESC, p.id DESC
                      LIMIT 1
                    )
                  ORDER BY play_type, selection, created_at DESC
                ) deduped
                ORDER BY ev DESC, created_at DESC
                LIMIT %s
                """,
                (match_id, match_id, limit),
            )
            return _mark_research_only(_dedupe_and_sort_ev_signals([dict(row) for row in cur.fetchall()], limit))

    def plan_ev_candidates(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, model_version, play_type, selection, model_prob, odds, ev,
                       snapshot_id, research_only, suggestion_eligible, created_at
                FROM (
                  SELECT DISTINCT ON (e.match_id, e.play_type, e.selection)
                         e.match_id,
                         e.model_version,
                         e.play_type,
                         e.selection,
                         e.model_prob,
                         e.odds,
                         e.ev,
                         e.snapshot_id,
                         e.research_only,
                         e.suggestion_eligible,
                         e.created_at
                  FROM ev_signals e
                  WHERE e.model_version = (
                      SELECT p.model_version
                      FROM predictions p
                      WHERE p.match_id = e.match_id
                      ORDER BY p.created_at DESC, p.id DESC
                      LIMIT 1
                    )
                    AND e.suggestion_eligible = true
                    AND e.ev > 0
                    AND e.ev <= %s
                    AND e.play_type IN ('had', 'hhad')
                    AND COALESCE(e.research_only, false) = false
                  ORDER BY e.match_id, e.play_type, e.selection, e.created_at DESC
                ) deduped
                ORDER BY ev DESC, created_at DESC
                LIMIT %s
                """,
                (EV_RESEARCH_ONLY_THRESHOLD, limit),
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

    def create_bets_batch(self, user_id: int, planned_bets: list[dict[str, Any]]) -> dict[str, Any]:
        if not planned_bets:
            raise ValueError("no bets to create")
        total_stake = sum((Decimal(str(item["stake"])) for item in planned_bets), Decimal("0"))
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT balance FROM users WHERE id = %s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("user not found")
            balance = Decimal(str(row["balance"]))
            if balance < total_stake:
                raise ValueError("insufficient balance")
            cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_stake, user_id))
            created_bets: list[dict[str, Any]] = []
            for item in planned_bets:
                cur.execute(
                    """
                    INSERT INTO bets (user_id, legs, parlay, stake, potential_payout)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, legs, parlay, stake, potential_payout, status
                    """,
                    (
                        user_id,
                        Jsonb(item["legs"]),
                        item.get("parlay", "single"),
                        item["stake"],
                        item["potential_payout"],
                    ),
                )
                created_bets.append(dict(cur.fetchone()))
            cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
            balance_after = cur.fetchone()["balance"]
            for bet in created_bets:
                bet["balance"] = balance_after
            return {"created_bets": created_bets, "balance_after": balance_after}

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
                SELECT u.username,
                       u.balance,
                       0::numeric AS roi,
                       COALESCE(count(b.id) FILTER (WHERE b.status IN ('won', 'lost', 'void')), 0) AS settled_bets
                FROM users u
                LEFT JOIN bets b ON b.user_id = u.id
                GROUP BY u.id, u.username, u.balance
                ORDER BY u.balance DESC, u.id
                LIMIT 50
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def best_ev_signal(self, match_id: str) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, model_version, play_type, selection, model_prob, odds, ev, suggestion_eligible
                FROM (
                  SELECT DISTINCT ON (play_type, selection)
                         match_id, model_version, play_type, selection, model_prob, odds, ev, suggestion_eligible, created_at
                  FROM ev_signals
                  WHERE match_id = %s
                    AND model_version = (
                      SELECT p.model_version
                      FROM predictions p
                      WHERE p.match_id = %s
                      ORDER BY p.created_at DESC, p.id DESC
                      LIMIT 1
                    )
                    AND suggestion_eligible = true
                    AND ev > 0
                    AND ev <= %s
                    AND play_type IN ('had', 'hhad')
                    AND COALESCE(research_only, false) = false
                  ORDER BY play_type, selection, created_at DESC
                ) deduped
                ORDER BY ev DESC, created_at DESC
                LIMIT 1
                """,
                (match_id, match_id, EV_RESEARCH_ONLY_THRESHOLD),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _dedupe_and_sort_ev_signals(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    latest_by_selection: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["play_type"]), str(row["selection"]))
        current = latest_by_selection.get(key)
        if current is None or str(row.get("created_at") or "") > str(current.get("created_at") or ""):
            latest_by_selection[key] = row
    return sorted(
        latest_by_selection.values(),
        key=lambda row: (float(row.get("ev") or 0), str(row.get("created_at") or "")),
        reverse=True,
    )[:limit]


def _mark_research_only(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        research_only = bool(row.get("research_only")) or float(row.get("ev") or 0) > EV_RESEARCH_ONLY_THRESHOLD
        row["research_only"] = research_only
        row["reason"] = row.get("reason") or ("model_market_divergence_too_large" if research_only else None)
    return rows


def get_db() -> Database:
    return Database()
