from __future__ import annotations

from collections import Counter
from typing import Any

import psycopg

from model import db


PLAY_TYPES = ("had", "hhad", "crs", "ttg", "hafu")


def probability_sum_ok(row: dict[str, Any], tolerance: float = 1e-6) -> bool:
    return abs(float(row["p_home"]) + float(row["p_draw"]) + float(row["p_away"]) - 1.0) <= tolerance


def score_matrix_shape_ok(matrix: Any, expected: int = 11) -> bool:
    return isinstance(matrix, list) and len(matrix) == expected and all(isinstance(row, list) and len(row) == expected for row in matrix)


def missing_ev_play_types(signals: list[dict[str, Any]]) -> set[str]:
    present = {signal["play_type"] for signal in signals}
    return set(PLAY_TYPES) - present


def production_check() -> int:
    try:
        with db.get_conn() as conn:
            counts = {table: db.table_count(conn, table) for table in ("team_ratings", "model_versions", "predictions", "ev_signals")}
            latest_version = db.fetch_latest_model_version(conn)
            upcoming = db.fetch_upcoming_matches(conn)
            latest_predictions = _latest_predictions(conn)
            latest_signals = _latest_signals(conn)
            first_match = upcoming[0] if upcoming else None
            first_prediction = _latest_prediction_for_match(conn, first_match["match_id"]) if first_match else None
            first_signals = _signals_for_match(conn, first_match["match_id"]) if first_match else []
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: production check failed: {exc}")
        return 1

    print("P1 Production Check")
    print("")
    print("1. Database")
    for table, count in counts.items():
        print(f"- {table}: {count}")
    print("")
    print("2. Latest Model Version")
    print(f"- id: {latest_version['id'] if latest_version else None}")
    print(f"- name: {latest_version['name'] if latest_version else None}")
    print(f"- params: {latest_version['params'] if latest_version else None}")
    print("")
    print("3. Predictions")
    print(f"- upcoming_matches: {len(upcoming)}")
    print(f"- predictions_latest_batch: {len(latest_predictions)}")
    print(f"- probability_sum_check: {all(probability_sum_ok(row) for row in latest_predictions)}")
    print(f"- score_matrix_shape_check: {all(score_matrix_shape_ok(row['score_matrix']) for row in latest_predictions)}")
    print("")
    print("4. EV Signals")
    play_counts = Counter(signal["play_type"] for signal in latest_signals)
    for play_type in PLAY_TYPES:
        value = play_counts.get(play_type, 0)
        print(f"- {play_type}: {value if value else 'missing odds'}")
    print("")
    print("5. Opening Match / First Upcoming Match")
    print(f"- match_id: {first_match['match_id'] if first_match else None}")
    print(f"- home_team: {first_match['home_team'] if first_match else None}")
    print(f"- away_team: {first_match['away_team'] if first_match else None}")
    print(f"- kickoff_at: {first_match['kickoff_at'] if first_match else None}")
    print(f"- has_prediction: {first_prediction is not None}")
    print(f"- score_matrix_shape: {score_matrix_shape_ok(first_prediction['score_matrix']) if first_prediction else False}")
    print(f"- ev_signal_play_types: {sorted({signal['play_type'] for signal in first_signals})}")
    return 0


def _latest_predictions(conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, p_home, p_draw, p_away, score_matrix, lambda_home, lambda_away, created_at
            FROM predictions
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _latest_signals(conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, play_type, selection, model_prob, odds, ev, created_at
            FROM ev_signals
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _latest_prediction_for_match(conn, match_id: str) -> dict[str, Any] | None:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, p_home, p_draw, p_away, score_matrix, lambda_home, lambda_away, created_at
            FROM predictions
            WHERE match_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _signals_for_match(conn, match_id: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, play_type, selection, model_prob, odds, ev, created_at
            FROM ev_signals
            WHERE match_id = %s
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (match_id,),
        )
        return [dict(row) for row in cur.fetchall()]


if __name__ == "__main__":
    raise SystemExit(production_check())
