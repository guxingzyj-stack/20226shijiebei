from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal


LegStatus = Literal["win", "lose", "void"]
BetStatus = Literal["won", "lost", "open"]

WIN_OTHER = "\u80dc\u5176\u4ed6"
WIN_OTHER_ALT = "\u80dc\u5176\u5b83"
DRAW_OTHER = "\u5e73\u5176\u4ed6"
DRAW_OTHER_ALT = "\u5e73\u5176\u5b83"
LOSE_OTHER = "\u8d1f\u5176\u4ed6"
LOSE_OTHER_ALT = "\u8d1f\u5176\u5b83"

STANDARD_CRS_SCORES = {
    "1:0",
    "2:0",
    "2:1",
    "3:0",
    "3:1",
    "3:2",
    "4:0",
    "4:1",
    "4:2",
    "5:0",
    "5:1",
    "5:2",
    "0:0",
    "1:1",
    "2:2",
    "3:3",
    "0:1",
    "0:2",
    "1:2",
    "0:3",
    "1:3",
    "2:3",
    "0:4",
    "1:4",
    "2:4",
    "0:5",
    "1:5",
    "2:5",
}


@dataclass(frozen=True)
class MatchResult:
    home_score: int
    away_score: int
    ht_home: int | None = None
    ht_away: int | None = None


def settle_leg(
    play_type: str,
    selection: str,
    result: MatchResult,
    goal_line: int | float | None = None,
) -> LegStatus:
    if play_type == "had":
        return _win_if(selection == _outcome(result.home_score, result.away_score))
    if play_type == "hhad":
        line = float(goal_line or 0)
        return _win_if(selection == _outcome(result.home_score + line, result.away_score))
    if play_type == "crs":
        return _settle_crs(selection, result)
    if play_type == "ttg":
        total_goals = result.home_score + result.away_score
        winning = "7" if total_goals >= 7 else str(total_goals)
        return _win_if(selection == winning)
    if play_type == "hafu":
        if result.ht_home is None or result.ht_away is None:
            return "void"
        winning = f"{_outcome(result.ht_home, result.ht_away)}{_outcome(result.home_score, result.away_score)}"
        return _win_if(selection == winning)
    raise ValueError(f"unsupported play_type: {play_type}")


def settle_parlay(
    legs: list[dict[str, Any]],
    results: dict[str, MatchResult],
    stake: Decimal,
) -> dict[str, Decimal | str | list[LegStatus]]:
    statuses: list[LegStatus] = []
    odds_product = Decimal("1")
    for leg in legs:
        match_id = str(leg["match_id"])
        if match_id not in results:
            statuses.append("void")
            continue
        status = settle_leg(
            str(leg["play_type"]),
            str(leg["selection"]),
            results[match_id],
            leg.get("goal_line"),
        )
        statuses.append(status)
        if status == "lose":
            return {"status": "lost", "payout": Decimal("0"), "leg_statuses": statuses}
        if status == "win":
            odds_product *= Decimal(str(leg["odds"]))
    return {"status": "won", "payout": stake * odds_product, "leg_statuses": statuses}


def parlay_size(parlay: str) -> int:
    if parlay == "single":
        return 1
    if parlay.endswith("x1") and parlay[:-2].isdigit():
        size = int(parlay[:-2])
        if 2 <= size <= 8:
            return size
    raise ValueError("unsupported parlay")


def potential_payout(stake: Decimal, odds_values: list[Decimal]) -> Decimal:
    product = Decimal("1")
    for odds in odds_values:
        product *= odds
    return stake * product


def _settle_crs(selection: str, result: MatchResult) -> LegStatus:
    normalized = _normalize_score_selection(selection)
    final_score = f"{result.home_score}:{result.away_score}"
    if normalized == final_score:
        return "win"
    if normalized in {WIN_OTHER, WIN_OTHER_ALT}:
        return _win_if(result.home_score > result.away_score and final_score not in STANDARD_CRS_SCORES)
    if normalized in {DRAW_OTHER, DRAW_OTHER_ALT}:
        return _win_if(result.home_score == result.away_score and final_score not in STANDARD_CRS_SCORES)
    if normalized in {LOSE_OTHER, LOSE_OTHER_ALT}:
        return _win_if(result.home_score < result.away_score and final_score not in STANDARD_CRS_SCORES)
    return "lose"


def _normalize_score_selection(selection: str) -> str:
    if ":" in selection:
        return selection
    if len(selection) == 2 and selection.isdigit():
        return f"{selection[0]}:{selection[1]}"
    return selection


def _outcome(home_score: int | float, away_score: int | float) -> str:
    if home_score > away_score:
        return "3"
    if home_score == away_score:
        return "1"
    return "0"


def _win_if(condition: bool) -> LegStatus:
    return "win" if condition else "lose"
