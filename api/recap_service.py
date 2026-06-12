from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from psycopg.rows import dict_row

from api.db import connect
from api.recap_models import RecapPayload, RecapResponse


OUTCOME_LABELS = {"3": "home", "1": "draw", "0": "away"}
OUTCOME_NAMES = {"home": "home win", "draw": "draw", "away": "away win"}


class RecapRepository(Protocol):
    def match(self, match_id: str) -> dict[str, Any] | None: ...
    def had_odds(self, match_id: str) -> list[dict[str, Any]]: ...
    def pre_kickoff_prediction(self, match_id: str, kickoff_at: Any) -> dict[str, Any] | None: ...
    def ev_signals(self, match_id: str) -> list[dict[str, Any]]: ...
    def settlement_summary(self, match_id: str) -> dict[str, int]: ...
    def finished_matches(self, limit: int) -> list[dict[str, Any]]: ...


class SqlRecapRepository:
    def match(self, match_id: str) -> dict[str, Any] | None:
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

    def had_odds(self, match_id: str) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, match_id, play_type, odds, fetched_at, source
                FROM odds_snapshots
                WHERE match_id = %s AND play_type = 'had'
                ORDER BY fetched_at ASC, id ASC
                """,
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def pre_kickoff_prediction(self, match_id: str, kickoff_at: Any) -> dict[str, Any] | None:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, match_id, model_version, p_home, p_draw, p_away,
                       score_matrix, lambda_home, lambda_away, created_at
                FROM predictions
                WHERE match_id = %s
                  AND created_at <= %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (match_id, kickoff_at),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def ev_signals(self, match_id: str) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, model_version, play_type, selection, model_prob, odds, ev,
                       research_only, reason, suggestion_eligible, created_at
                FROM ev_signals
                WHERE match_id = %s
                ORDER BY created_at DESC, ev DESC
                LIMIT 100
                """,
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def settlement_summary(self, match_id: str) -> dict[str, int]:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, count(*)
                FROM bets
                WHERE legs::text LIKE %s
                GROUP BY status
                """,
                (f"%{match_id}%",),
            )
            counts = {str(status): int(count) for status, count in cur.fetchall()}
        return _settlement_counts(counts)

    def finished_matches(self, limit: int) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, match_num, league, home_team, away_team, kickoff_at, status,
                       result_home, result_away, ht_home, ht_away
                FROM matches
                WHERE status IN ('finished', 'completed')
                  AND result_home IS NOT NULL
                  AND result_away IS NOT NULL
                ORDER BY kickoff_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]


def build_match_recap(match_id: str, repository: RecapRepository | None = None) -> RecapResponse:
    repo = repository or SqlRecapRepository()
    match = repo.match(match_id)
    if match is None:
        return {"available": False, "reason": "match_not_found"}
    if not _has_finished_result(match):
        return {"available": False, "reason": "match_not_finished_or_result_missing"}
    return {"available": True, "recap": _build_recap(match, repo)}


def recent_recaps(limit: int = 10, repository: RecapRepository | None = None) -> dict[str, Any]:
    repo = repository or SqlRecapRepository()
    rows = repo.finished_matches(max(1, min(limit, 50)))
    items = []
    for match in rows:
        recap = _build_recap(match, repo)
        items.append(
            {
                "match_id": recap["match_id"],
                "match_num": recap["match_num"],
                "home_team": recap["home_team"],
                "away_team": recap["away_team"],
                "scoreline": recap["result"]["scoreline"],
                "prediction_correct": recap["model"]["prediction_correct"],
                "title": recap["summary"]["title"],
            }
        )
    return {"items": items, "count": len(items)}


def recap_summary(repository: RecapRepository | None = None) -> dict[str, Any]:
    repo = repository or SqlRecapRepository()
    rows = repo.finished_matches(500)
    model_correct = 0
    model_wrong = 0
    model_missing = 0
    ev_signal_count = 0
    settled_bets = 0
    for match in rows:
        recap = _build_recap(match, repo)
        correct = recap["model"]["prediction_correct"]
        if correct is True:
            model_correct += 1
        elif correct is False:
            model_wrong += 1
        else:
            model_missing += 1
        ev_signal_count += recap["ev"]["total_ev_signals"]
        settled_bets += recap["settlement"]["settled_bets"]
    return {
        "finished_matches": len(rows),
        "recap_available_matches": len(rows),
        "model_correct_count": model_correct,
        "model_wrong_count": model_wrong,
        "model_missing_count": model_missing,
        "ev_signal_count": ev_signal_count,
        "settled_bets": settled_bets,
    }


def _build_recap(match: dict[str, Any], repo: RecapRepository) -> RecapPayload:
    warnings: list[str] = []
    result = _result(match)
    market = _market_section(match, repo.had_odds(str(match["match_id"])), warnings)
    model = _model_section(match, repo.pre_kickoff_prediction(str(match["match_id"]), match["kickoff_at"]), result["winner"])
    ev = _ev_section(repo.ev_signals(str(match["match_id"])), result, match)
    settlement = repo.settlement_summary(str(match["match_id"]))
    settlement_status = "no_public_bets" if settlement["settled_bets"] == 0 and settlement["open_bets"] == 0 else "has_bets"
    settlement["settlement_status"] = settlement_status
    data_quality = {
        "has_result": True,
        "has_had_odds": bool(market["had_open"] or market["had_close"]),
        "has_prediction": model["model_version"] is not None,
        "has_ev_signal": ev["total_ev_signals"] > 0,
        "has_settlement": settlement["settled_bets"] > 0 or settlement["open_bets"] > 0,
        "warnings": warnings,
    }
    return {
        "match_id": match["match_id"],
        "match_num": match.get("match_num"),
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "kickoff_at": _iso(match.get("kickoff_at")),
        "status": match.get("status"),
        "result": result,
        "data_quality": data_quality,
        "market": market,
        "model": model,
        "ev": ev,
        "settlement": settlement,
        "summary": _summary_section(match, result, market, model, ev, settlement_status),
    }


def _result(match: dict[str, Any]) -> dict[str, Any]:
    home = int(match["result_home"])
    away = int(match["result_away"])
    winner = "home" if home > away else "away" if away > home else "draw"
    return {"home": home, "away": away, "winner": winner, "scoreline": f"{home}-{away}", "had_selection": _winner_to_had(winner)}


def _market_section(match: dict[str, Any], odds_rows: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    if not odds_rows:
        warnings.append("missing_had_odds")
        return {"had_open": {}, "had_close": {}, "close_implied_probabilities": {}, "favorite": None, "market_result": None}
    opened = odds_rows[0]
    pre_kickoff = [row for row in odds_rows if _dt(row.get("fetched_at")) and _dt(row.get("fetched_at")) <= _dt(match["kickoff_at"])]
    if pre_kickoff:
        closed = pre_kickoff[-1]
    else:
        closed = odds_rows[-1]
        warnings.append("no_pre_kickoff_close_odds")
    open_odds = _odds_dict(opened.get("odds"))
    close_odds = _odds_dict(closed.get("odds"))
    implied = _normalized_implied(close_odds)
    favorite_selection = min((key for key in ("3", "1", "0") if key in close_odds), key=lambda key: close_odds[key], default=None)
    return {
        "had_open": open_odds,
        "had_close": close_odds,
        "close_implied_probabilities": implied,
        "favorite": OUTCOME_LABELS.get(favorite_selection) if favorite_selection else None,
        "market_result": OUTCOME_LABELS.get(favorite_selection) if favorite_selection else None,
    }


def _model_section(match: dict[str, Any], prediction: dict[str, Any] | None, actual_winner: str) -> dict[str, Any]:
    if prediction is None:
        return {
            "model_version": None,
            "created_at": None,
            "probs": {},
            "predicted_outcome": None,
            "confidence": None,
            "prediction_correct": None,
            "message": "no auditable pre-kickoff prediction",
        }
    probs = {
        "home": float(prediction["p_home"]),
        "draw": float(prediction["p_draw"]),
        "away": float(prediction["p_away"]),
    }
    predicted = max(probs, key=probs.get)
    return {
        "model_version": prediction.get("model_version"),
        "created_at": _iso(prediction.get("created_at")),
        "probs": probs,
        "predicted_outcome": predicted,
        "confidence": probs[predicted],
        "prediction_correct": predicted == actual_winner,
    }


def _ev_section(signals: list[dict[str, Any]], result: dict[str, Any], match: dict[str, Any]) -> dict[str, Any]:
    items = []
    hit_count = 0
    miss_count = 0
    for signal in signals:
        hit = _signal_hit(signal, result, match)
        if hit is True:
            hit_count += 1
        elif hit is False:
            miss_count += 1
        items.append(
            {
                "match_id": signal.get("match_id"),
                "model_version": signal.get("model_version"),
                "play_type": signal.get("play_type"),
                "selection": signal.get("selection"),
                "model_prob": _float_or_none(signal.get("model_prob")),
                "odds": _float_or_none(signal.get("odds")),
                "ev": _float_or_none(signal.get("ev")),
                "research_only": bool(signal.get("research_only")),
                "suggestion_eligible": bool(signal.get("suggestion_eligible")),
                "reason": signal.get("reason"),
                "hit": hit,
                "recommendation_label": "research_signal" if signal.get("research_only") else "value_signal",
            }
        )
    return {
        "signals": items,
        "total_ev_signals": len(items),
        "high_ev_count": sum(1 for item in items if (item["ev"] or 0) > 0.15),
        "research_only_count": sum(1 for item in items if item["research_only"]),
        "suggestion_eligible_count": sum(1 for item in items if item["suggestion_eligible"]),
        "hit_count": hit_count,
        "miss_count": miss_count,
    }


def _summary_section(
    match: dict[str, Any],
    result: dict[str, Any],
    market: dict[str, Any],
    model: dict[str, Any],
    ev: dict[str, Any],
    settlement_status: str,
) -> dict[str, Any]:
    home = str(match.get("home_team"))
    away = str(match.get("away_team"))
    model_text = "no auditable model prediction"
    if model["prediction_correct"] is True:
        model_text = "model direction hit"
    elif model["prediction_correct"] is False:
        model_text = "model direction missed"
    title = f"{home} {result['scoreline']} {away}: {model_text}"
    bullets = [
        f"Final result was {OUTCOME_NAMES[result['winner']]}.",
        f"Market favorite was {market['favorite'] or 'unavailable'}.",
        f"Model predicted {model['predicted_outcome'] or 'unavailable'}.",
        f"EV signals reviewed: {ev['total_ev_signals']}.",
        f"Settlement status: {settlement_status}.",
    ]
    return {"title": title, "bullets": bullets}


def _settlement_counts(counts: dict[str, int]) -> dict[str, int]:
    won = counts.get("won", 0)
    lost = counts.get("lost", 0)
    void = counts.get("void", 0)
    open_bets = counts.get("open", 0) + counts.get("pending", 0)
    return {"settled_bets": won + lost + void, "won_bets": won, "lost_bets": lost, "void_bets": void, "open_bets": open_bets}


def _signal_hit(signal: dict[str, Any], result: dict[str, Any], match: dict[str, Any]) -> bool | None:
    play_type = str(signal.get("play_type") or "")
    selection = str(signal.get("selection") or "")
    if play_type == "had":
        return selection == result["had_selection"]
    if play_type == "crs":
        return selection in {result["scoreline"], result["scoreline"].replace("-", ":")}
    if play_type == "ttg":
        total = result["home"] + result["away"]
        return selection == ("7" if total >= 7 else str(total))
    if play_type == "hafu":
        if match.get("ht_home") is None or match.get("ht_away") is None:
            return None
        ht_winner = "home" if int(match["ht_home"]) > int(match["ht_away"]) else "away" if int(match["ht_away"]) > int(match["ht_home"]) else "draw"
        return selection in {f"{_winner_to_had(ht_winner)}{result['had_selection']}", f"{_winner_to_had(ht_winner)}-{result['had_selection']}"}
    return None


def _winner_to_had(winner: str) -> str:
    return {"home": "3", "draw": "1", "away": "0"}[winner]


def _normalized_implied(odds: dict[str, float]) -> dict[str, float]:
    raw = {OUTCOME_LABELS[key]: 1.0 / float(odds[key]) for key in ("3", "1", "0") if key in odds and float(odds[key]) > 0}
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()} if total else {}


def _odds_dict(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(key): float(val) for key, val in value.items()}


def _has_finished_result(match: dict[str, Any]) -> bool:
    return str(match.get("status")) in {"finished", "completed"} and match.get("result_home") is not None and match.get("result_away") is not None


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    parsed = _dt(value)
    return parsed.isoformat() if parsed else None


def _float_or_none(value: Any) -> float | None:
    return None if value is None else float(value)
