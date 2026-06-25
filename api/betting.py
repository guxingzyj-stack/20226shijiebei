from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import os
from typing import Any

from fastapi import HTTPException, status

from api.settlement import parlay_size, potential_payout
from api.schemas import BetCreate


BET_CUTOFF_SECONDS = 5 * 60
BETTING_DISABLED_MESSAGE = "模拟投注功能即将开放，结算系统验收通过后开启。当前可查看预测、赔率走势和EV信号。"
PLAY_TYPE_ALIASES = {"correct_score": "crs"}
PLAN_DEFAULT_BUDGET = Decimal("100")
PLAN_DEFAULT_MAX_BETS = 5
PLAN_MAX_BETS = 8
PLAN_MIN_STAKE = Decimal("1")
PLAN_MONEY = Decimal("0.01")
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


def build_bet_plan(
    db: Any,
    user: dict[str, Any],
    budget: Decimal | int | float | str | None = None,
    max_bets: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    user_balance = _to_money(user["balance"])
    requested_budget = _to_money(budget if budget is not None else PLAN_DEFAULT_BUDGET)
    requested_budget = max(requested_budget, Decimal("0"))
    effective_budget = min(requested_budget, user_balance)
    max_bets = _normalize_max_bets(max_bets)
    blockers: list[str] = []
    warnings: list[str] = []

    if requested_budget > user_balance:
        warnings.append("budget_capped_to_balance")
    if effective_budget < PLAN_MIN_STAKE:
        blockers.append("budget_too_low")
        return _empty_plan(effective_budget, blockers, warnings)

    rows = db.plan_ev_candidates(limit=max(max_bets * 12, 50))
    best_by_match: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _plan_item_from_signal(db, row, user_balance, now)
        if item is None:
            continue
        match_id = str(item["match_id"])
        current = best_by_match.get(match_id)
        if current is None or _plan_sort_key(item) > _plan_sort_key(current):
            best_by_match[match_id] = item

    selected = sorted(best_by_match.values(), key=_plan_sort_key, reverse=True)[:max_bets]
    selected = _scale_plan_items_to_budget(selected, effective_budget)
    total_stake = sum((Decimal(str(item["stake"])) for item in selected), Decimal("0")).quantize(PLAN_MONEY)
    if not selected:
        blockers.append("no_eligible_signals")

    return {
        "available": bool(selected),
        "total_budget": effective_budget,
        "total_stake": total_stake,
        "items": selected,
        "blockers": blockers,
        "warnings": warnings,
    }


def place_bet_plan(
    db: Any,
    user: dict[str, Any],
    budget: Decimal | int | float | str | None = None,
    max_bets: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not is_betting_enabled():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BETTING_DISABLED_MESSAGE)

    plan = build_bet_plan(db, user, budget=budget, max_bets=max_bets, now=now)
    if not plan["items"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no eligible bet plan")

    planned_bets: list[dict[str, Any]] = []
    for item in plan["items"]:
        match = db.get_match(str(item["match_id"]))
        if match is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="match not found")
        stake = Decimal(str(item["stake"]))
        odds = Decimal(str(item["odds"]))
        leg = {
            "match_id": str(item["match_id"]),
            "play_type": str(item["play_type"]),
            "selection": str(item["selection"]),
            "odds": str(odds),
            "snapshot_id": item.get("snapshot_id"),
            "goal_line": item.get("goal_line"),
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "kickoff_at": match.get("kickoff_at").isoformat() if hasattr(match.get("kickoff_at"), "isoformat") else match.get("kickoff_at"),
            "label": f"{match.get('home_team')} vs {match.get('away_team')}",
        }
        planned_bets.append(
            {
                "legs": [leg],
                "parlay": "single",
                "stake": stake,
                "potential_payout": potential_payout(stake, [odds]),
            }
        )

    try:
        result = db.create_bets_batch(int(user["id"]), planned_bets)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "created_bets": result["created_bets"],
        "plan_snapshot": plan,
        "balance_after": result["balance_after"],
    }


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


def _empty_plan(total_budget: Decimal, blockers: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "available": False,
        "total_budget": total_budget,
        "total_stake": Decimal("0"),
        "items": [],
        "blockers": blockers,
        "warnings": warnings,
    }


def _normalize_max_bets(value: int | None) -> int:
    if value is None:
        return PLAN_DEFAULT_MAX_BETS
    return min(max(int(value), 1), PLAN_MAX_BETS)


def _to_money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(PLAN_MONEY)


def _plan_item_from_signal(db: Any, row: dict[str, Any], balance: Decimal, now: datetime) -> dict[str, Any] | None:
    play_type = _canonical_play_type(str(row.get("play_type") or "").lower())
    if play_type not in {"had", "hhad"}:
        return None
    try:
        ev = float(row.get("ev"))
        model_prob = float(row.get("model_prob"))
    except (TypeError, ValueError):
        return None
    if ev <= 0 or ev > 0.15:
        return None
    if row.get("suggestion_eligible") is False or bool(row.get("research_only")):
        return None

    match_id = str(row.get("match_id") or "")
    if not match_id:
        return None
    match = db.get_match(match_id)
    if match is None:
        return None
    if str(match.get("status") or "").lower() != "scheduled":
        return None
    if match.get("result_home") is not None or match.get("result_away") is not None:
        return None
    kickoff = _as_aware_datetime(match["kickoff_at"])
    if kickoff <= now or (kickoff - now).total_seconds() < BET_CUTOFF_SECONDS:
        return None

    snapshot = db.latest_odds(match_id, play_type)
    if snapshot is None:
        return None
    snapshot_odds = snapshot.get("odds") or {}
    selection = _canonical_selection(play_type, str(row.get("selection") or ""), snapshot_odds)
    if selection not in snapshot_odds:
        return None
    try:
        odds = Decimal(str(snapshot_odds[selection]))
    except Exception:
        return None
    stake = suggested_stake(balance, model_prob, float(odds))
    if stake < PLAN_MIN_STAKE:
        return None
    return {
        "match_id": match_id,
        "match_num": match.get("match_num"),
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "kickoff_at": match.get("kickoff_at"),
        "play_type": play_type,
        "selection": selection,
        "selection_label": _selection_label(play_type, selection),
        "model_prob": model_prob,
        "ev": ev,
        "odds": odds,
        "stake": stake,
        "potential_payout": potential_payout(stake, [odds]),
        "snapshot_id": snapshot.get("id"),
        "goal_line": snapshot.get("goal_line"),
    }


def _selection_label(play_type: str, selection: str) -> str:
    if play_type == "had":
        return {"3": "主胜", "1": "平局", "0": "客胜"}.get(selection, selection)
    if play_type == "hhad":
        return {"3": "让胜", "1": "让平", "0": "让负"}.get(selection, selection)
    return selection


def _plan_sort_key(item: dict[str, Any]) -> tuple[float, Decimal]:
    return (float(item.get("ev") or 0), Decimal(str(item.get("stake") or "0")))


def _scale_plan_items_to_budget(items: list[dict[str, Any]], budget: Decimal) -> list[dict[str, Any]]:
    total = sum((Decimal(str(item["stake"])) for item in items), Decimal("0"))
    if total <= budget:
        return items
    scale = budget / total
    scaled: list[dict[str, Any]] = []
    for item in items:
        stake = (Decimal(str(item["stake"])) * scale).quantize(PLAN_MONEY, rounding=ROUND_DOWN)
        if stake < PLAN_MIN_STAKE:
            continue
        odds = Decimal(str(item["odds"]))
        next_item = dict(item)
        next_item["stake"] = stake
        next_item["potential_payout"] = potential_payout(stake, [odds])
        scaled.append(next_item)
    return scaled
