from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status

from api.settlement import parlay_size, potential_payout
from api.schemas import BetCreate


BET_CUTOFF_SECONDS = 5 * 60


def place_bet(db: Any, user: dict[str, Any], request: BetCreate, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if request.stake <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="stake must be positive")
    user_balance = Decimal(str(user["balance"]))
    if request.stake > user_balance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient balance")

    expected_size = parlay_size(request.parlay)
    if expected_size != len(request.legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parlay does not match leg count")

    server_legs: list[dict[str, Any]] = []
    odds_values: list[Decimal] = []
    for leg in request.legs:
        match = db.get_match(leg.match_id)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
        kickoff = _as_aware_datetime(match["kickoff_at"])
        if kickoff <= now or (kickoff - now).total_seconds() < BET_CUTOFF_SECONDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="betting closed")

        snapshot = db.latest_odds(leg.match_id, leg.play_type)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="market not available")
        snapshot_odds = snapshot.get("odds") or {}
        if leg.selection not in snapshot_odds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selection not available")
        odds = Decimal(str(snapshot_odds[leg.selection]))
        odds_values.append(odds)
        server_legs.append(
            {
                "match_id": leg.match_id,
                "play_type": leg.play_type,
                "selection": leg.selection,
                "odds": str(odds),
                "snapshot_id": snapshot.get("id"),
                "goal_line": snapshot.get("goal_line"),
            }
        )

    payout = potential_payout(request.stake, odds_values)
    try:
        return db.create_bet(int(user["id"]), server_legs, request.parlay, request.stake, payout)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def suggested_stake(balance: Decimal, model_prob: float, odds: float) -> Decimal:
    if odds <= 1:
        return Decimal("0")
    fraction = (model_prob * odds - 1) / (odds - 1)
    stake = max(0.0, fraction / 4.0) * float(balance)
    cap = float(balance) * 0.05
    return Decimal(str(min(stake, cap))).quantize(Decimal("0.01"))


def _as_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
