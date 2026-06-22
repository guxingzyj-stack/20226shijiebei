from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Any

from fastapi import HTTPException, status

from api.settlement import parlay_size, potential_payout
from api.schemas import BetCreate


BET_CUTOFF_SECONDS = 5 * 60
BETTING_DISABLED_MESSAGE = "模拟投注功能即将开放，结算系统验收通过后开启。当前可查看预测、赔率走势和EV信号。"
PLAY_TYPE_ALIASES = {"correct_score": "crs"}
CRS_SELECTION_ALIASES = {
    "other_home_win": ["胜其他", "胜其它"],
    "other_draw": ["平其他", "平其它"],
    "other_away_win": ["负其他", "负其它"],
}


def is_betting_enabled() -> bool:
    return os.getenv("BETTING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def place_bet(db: Any, user: dict[str, Any], request: BetCreate, now: datetime | None = None) -> dict[str, Any]:
    if not is_betting_enabled():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BETTING_DISABLED_MESSAGE)

    now = now or datetime.now(timezone.utc)
    if request.stake <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="stake must be positive")
    user_balance = Decimal(str(user["balance"]))
    if request.stake > user_balance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient balance")

    request_legs = request.bet_legs()
    if not request_legs or len(request_legs) > 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid bet legs")

    expected_size = parlay_size(request.parlay)
    if expected_size != len(request_legs):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parlay does not match leg count")

    server_legs: list[dict[str, Any]] = []
    odds_values: list[Decimal] = []
    for leg in request_legs:
        play_type = _canonical_play_type(leg.play_type)
        match = db.get_match(leg.match_id)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
        kickoff = _as_aware_datetime(match["kickoff_at"])
        if kickoff <= now or (kickoff - now).total_seconds() < BET_CUTOFF_SECONDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="betting closed")

        snapshot = db.latest_odds(leg.match_id, play_type)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="market not available")
        snapshot_odds = snapshot.get("odds") or {}
        selection = _canonical_selection(play_type, leg.selection, snapshot_odds)
        if selection not in snapshot_odds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selection not available")
        odds = Decimal(str(snapshot_odds[selection]))
        odds_values.append(odds)
        server_legs.append(
            {
                "match_id": leg.match_id,
                "play_type": play_type,
                "selection": selection,
                "odds": str(odds),
                "snapshot_id": snapshot.get("id"),
                "goal_line": snapshot.get("goal_line"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "kickoff_at": match.get("kickoff_at").isoformat() if hasattr(match.get("kickoff_at"), "isoformat") else match.get("kickoff_at"),
                "label": f"{match.get('home_team')} vs {match.get('away_team')}",
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


def _canonical_play_type(play_type: str) -> str:
    return PLAY_TYPE_ALIASES.get(play_type, play_type)


def _canonical_selection(play_type: str, selection: str, odds: dict[str, Any]) -> str:
    if play_type != "crs":
        return selection
    normalized = selection.replace("-", ":")
    if normalized in odds:
        return normalized
    for candidate in CRS_SELECTION_ALIASES.get(selection, []):
        if candidate in odds:
            return candidate
    return normalized
