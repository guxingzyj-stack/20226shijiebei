from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from model.dixon_coles import lambdas_from_elo, score_matrix, three_way_probs
from model.fit_dc import DCParams
from model.historical_odds import FOOTBALL_DATA_ODDS_URLS, HistoricalOddsMatch, load_historical_odds_sources, match_validation_game_to_odds
from model.market import shin_devig_three_way
from model.metrics import rps_three_way
from model.market import normalize_probs


VALIDATION_TOURNAMENTS = {"FIFA World Cup", "UEFA Euro", "Copa América"}


@dataclass(frozen=True)
class BacktestResult:
    market_rps: float | None
    dc_rps: float
    blended_rps: float
    best_w_dc: float
    matches: int


@dataclass(frozen=True)
class MarketBacktestReport:
    validation_target: str
    odds_sources: list[str]
    total_validation_matches: int
    matched_odds_matches: int
    unmatched_matches: int
    market_rps: float | None
    dc_rps: float | None
    blended_rps: float | None
    best_w_dc: float | None
    best_w_market: float | None
    status: str
    unmatched_reasons: dict[str, int]


def outcome_from_score(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "3"
    if home_score == away_score:
        return "1"
    return "0"


def dc_probs_for_row(row, params: DCParams) -> dict[str, float]:
    lambda_home, lambda_away = lambdas_from_elo(
        float(row.elo_home_pre),
        float(row.elo_away_pre),
        params.c,
        params.k,
        params.H,
        not bool(row.neutral),
    )
    p_home, p_draw, p_away = three_way_probs(score_matrix(lambda_home, lambda_away, params.rho, params.max_goals))
    return normalize_probs({"3": p_home, "1": p_draw, "0": p_away})


def validation_frame(matches_with_elo: pd.DataFrame) -> pd.DataFrame:
    years = matches_with_elo["date"].dt.year
    is_validation = (
        ((years == 2022) & (matches_with_elo["tournament"] == "FIFA World Cup"))
        | ((years == 2024) & (matches_with_elo["tournament"] == "UEFA Euro"))
        | ((years == 2024) & (matches_with_elo["tournament"] == "Copa América"))
    )
    return matches_with_elo[is_validation].copy()


def rps_for_probs(probs: dict[str, float], outcome: str) -> float:
    return rps_three_way(probs["3"], probs["1"], probs["0"], outcome)


def choose_blend_weight(
    dc_probs: list[dict[str, float]],
    market_probs: list[dict[str, float]],
    outcomes: list[str],
) -> tuple[float, float]:
    best_weight = 1.0
    best_rps = math.inf
    for step in range(0, 21):
        w_dc = step / 20
        scores = []
        for dc, market, outcome in zip(dc_probs, market_probs, outcomes):
            blended = normalize_probs({key: w_dc * dc[key] + (1 - w_dc) * market[key] for key in ("3", "1", "0")})
            scores.append(rps_for_probs(blended, outcome))
        mean_rps = sum(scores) / len(scores)
        if mean_rps < best_rps:
            best_weight = w_dc
            best_rps = mean_rps
    return best_weight, best_rps


def backtest_dc_only(matches_with_elo: pd.DataFrame, params: DCParams) -> BacktestResult:
    frame = validation_frame(matches_with_elo)
    if frame.empty:
        raise ValueError("validation set is empty")
    scores = []
    for row in frame.itertuples(index=False):
        probs = dc_probs_for_row(row, params)
        scores.append(rps_for_probs(probs, outcome_from_score(int(row.home_score), int(row.away_score))))
    dc_rps = sum(scores) / len(scores)
    return BacktestResult(market_rps=None, dc_rps=dc_rps, blended_rps=dc_rps, best_w_dc=1.0, matches=len(frame))


def backtest_with_market_odds(
    matches_with_elo: pd.DataFrame,
    params: DCParams,
    odds_rows: list[HistoricalOddsMatch] | None = None,
) -> MarketBacktestReport:
    frame = validation_frame(matches_with_elo)
    odds_rows = odds_rows if odds_rows is not None else load_historical_odds_sources()
    dc_probs: list[dict[str, float]] = []
    market_probs: list[dict[str, float]] = []
    outcomes: list[str] = []
    unmatched = 0
    for row in frame.itertuples(index=False):
        matched = match_validation_game_to_odds(row, odds_rows)
        if matched is None:
            unmatched += 1
            continue
        dc_probs.append(dc_probs_for_row(row, params))
        market_probs.append(shin_devig_three_way(matched.odds))
        outcomes.append(outcome_from_score(int(row.home_score), int(row.away_score)))
    if not outcomes:
        return MarketBacktestReport(
            validation_target="2022 World Cup + 2024 Euro + 2024 Copa America",
            odds_sources=FOOTBALL_DATA_ODDS_URLS,
            total_validation_matches=len(frame),
            matched_odds_matches=0,
            unmatched_matches=len(frame),
            market_rps=None,
            dc_rps=None,
            blended_rps=None,
            best_w_dc=None,
            best_w_market=None,
            status="insufficient_historical_odds",
            unmatched_reasons={"no_matching_odds": len(frame)},
        )
    market_scores = [rps_for_probs(probs, outcome) for probs, outcome in zip(market_probs, outcomes)]
    dc_scores = [rps_for_probs(probs, outcome) for probs, outcome in zip(dc_probs, outcomes)]
    best_w_dc, blended_rps = choose_blend_weight(dc_probs, market_probs, outcomes)
    status = "ok" if len(outcomes) >= 30 else "insufficient_historical_odds"
    return MarketBacktestReport(
        validation_target="2022 World Cup + 2024 Euro + 2024 Copa America",
        odds_sources=FOOTBALL_DATA_ODDS_URLS,
        total_validation_matches=len(frame),
        matched_odds_matches=len(outcomes),
        unmatched_matches=unmatched,
        market_rps=sum(market_scores) / len(market_scores),
        dc_rps=sum(dc_scores) / len(dc_scores),
        blended_rps=blended_rps,
        best_w_dc=best_w_dc,
        best_w_market=1 - best_w_dc,
        status=status,
        unmatched_reasons={"no_matching_odds": unmatched},
    )


def print_market_backtest_report(report: MarketBacktestReport) -> None:
    print("P1 Market Backtest Report")
    print(f"- validation_target: {report.validation_target}")
    print(f"- odds_sources: {report.odds_sources}")
    print(f"- total_validation_matches: {report.total_validation_matches}")
    print(f"- matched_odds_matches: {report.matched_odds_matches}")
    print(f"- unmatched_matches: {report.unmatched_matches}")
    print(f"- market_rps: {report.market_rps}")
    print(f"- dc_rps: {report.dc_rps}")
    print(f"- blended_rps: {report.blended_rps}")
    print(f"- best_w_dc: {report.best_w_dc}")
    print(f"- best_w_market: {report.best_w_market}")
    print(f"- status: {report.status}")
