from __future__ import annotations

from random import Random
from typing import Any

from api.db import connect


INSUFFICIENT = {
    "status": "insufficient_finished_matches",
    "message": "完赛场次不足，复盘将在小组赛进行后生成。",
}


def compute_user_balance_curve(user_id: int) -> list[dict[str, Any]] | dict[str, str]:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT placed_at, settled_at, stake, payout, status
                FROM bets
                WHERE user_id = %s AND status IN ('won', 'lost', 'void')
                ORDER BY COALESCE(settled_at, placed_at), id
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    except Exception:
        return INSUFFICIENT
    if len(rows) < 3:
        return INSUFFICIENT
    balance = 10000.0
    curve = []
    for placed_at, settled_at, stake, payout, status in rows:
        balance -= float(stake or 0)
        balance += float(payout or 0)
        curve.append({"at": str(settled_at or placed_at), "balance": balance, "status": status})
    return curve


def compute_model_follow_curve() -> list[dict[str, Any]] | dict[str, str]:
    return INSUFFICIENT if _finished_matches_count() < 8 else []


def compute_random_baseline_stub(seed: int = 2026) -> dict[str, Any]:
    rng = Random(seed)
    return {"status": "stub", "seed": seed, "sample": rng.random()}


def calibration_curve_from_finished_matches() -> dict[str, Any]:
    count = _finished_matches_count()
    if count < 8:
        return {**INSUFFICIENT, "finished_matches": count}
    return {"status": "not_implemented", "finished_matches": count, "buckets": []}


def _finished_matches_count() -> int:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM matches WHERE status = 'finished'")
            return int(cur.fetchone()[0])
    except Exception:
        return 0
