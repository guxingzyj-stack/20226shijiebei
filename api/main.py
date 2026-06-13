from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
import csv
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg.errors import UniqueViolation

from api.auth import create_access_token, current_user_claims, hash_password, verify_password
from api.betting import BETTING_DISABLED_MESSAGE, is_betting_enabled, place_bet, suggested_stake
from api.db import Database, get_db
from api.ops_health_check import latest_ops_health_status
from api import recap
from api.recap_service import build_match_recap, recent_recaps, recap_summary as build_recap_summary
from api.scheduler import scheduler_startup_error, start_api_scheduler, stop_api_scheduler
from api.scheduler_health import scheduler_freshness
from api.schemas import BetCreate, BetResponse, SuggestionResponse, TokenResponse, UserCreate, UserLogin


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_api_scheduler()
    try:
        yield
    finally:
        stop_api_scheduler()


app = FastAPI(title="World Cup Jingcai Simulation API", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5174").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_current_user(
    claims: dict[str, str] = Depends(current_user_claims),
    db: Database = Depends(get_db),
) -> dict:
    user = db.get_user_by_id(int(claims["id"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


@app.get("/api/health")
def health() -> dict:
    freshness = scheduler_freshness()
    startup_error = scheduler_startup_error()
    payload = {
        "ok": startup_error is None,
        "scheduler_last_seen": freshness["scheduler_last_seen"],
        "scheduler_last_seen_age_minutes": freshness["scheduler_last_seen_age_minutes"],
        "scheduler_stale": True if startup_error else freshness["scheduler_stale"],
        "scheduler_startup_error": startup_error,
    }
    payload.update(latest_ops_health_status())
    if startup_error:
        payload["ops_health_status"] = "FAIL"
        blockers = list(payload.get("ops_health_blockers") or [])
        if "scheduler_startup_error" not in blockers:
            blockers.append("scheduler_startup_error")
        payload["ops_health_blockers"] = blockers
    result_sync = _result_sync_health_summary()
    payload.update(result_sync)
    if result_sync.get("latest_results_sync_status") == "error":
        blockers = list(payload.get("ops_health_blockers") or [])
        if "results_sync_error" not in blockers:
            blockers.append("results_sync_error")
        payload["ops_health_blockers"] = blockers
        if payload.get("ops_health_status") not in {"FAIL"}:
            payload["ops_health_status"] = "WARN"
    if result_sync.get("result_overdue_closed_count"):
        blockers = list(payload.get("ops_health_blockers") or [])
        if "result_overdue_closed_matches" not in blockers:
            blockers.append("result_overdue_closed_matches")
        payload["ops_health_blockers"] = blockers
    payload.update(_p3_fifa_health_summary())
    payload.update(_betting_open_gate_health_summary())
    return payload


def _result_sync_health_summary() -> dict:
    try:
        from api.result_overdue_report import health_summary

        return health_summary()
    except Exception:
        return {
            "latest_results_sync_at": None,
            "latest_results_sync_status": None,
            "latest_results_sync_source": None,
            "latest_results_sync_finished_updated": None,
            "latest_results_sync_skipped": None,
            "latest_results_sync_skipped_reasons": {},
            "result_overdue_closed_count": None,
            "result_overdue_closed_matches": [],
        }


def _p3_fifa_health_summary() -> dict:
    try:
        from model.p3_fifa_readiness import health_summary

        return health_summary()
    except Exception:
        return {
            "p3_mode": "fifa_matchdata",
            "p3_status": "WAIT",
            "p3_candidate_w": 0,
            "p3_production_w": 0,
            "p3_blockers": ["p3_fifa_readiness_unavailable"],
        }


def _betting_open_gate_health_summary() -> dict:
    try:
        from api.betting_open_gate import health_summary

        return health_summary()
    except Exception:
        return {
            "betting_open_gate_status": "WAIT",
            "recommend_open_betting": False,
            "betting_open_blockers": ["betting_open_gate_unavailable"],
            "betting_open_warnings": [],
        }


def _match_has_had_odds(match: dict) -> bool:
    for snapshot in match.get("latest_odds") or []:
        if str(snapshot.get("play_type") or "").lower() != "had":
            continue
        odds = snapshot.get("odds") or {}
        if isinstance(odds, dict) and {"3", "1", "0"}.issubset(set(odds)):
            return True
    return False


@app.post("/api/auth/register", response_model=TokenResponse)
def register(payload: UserCreate, db: Database = Depends(get_db)) -> TokenResponse:
    try:
        user = db.create_user(payload.username, hash_password(payload.password))
    except UniqueViolation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists") from exc
    token = create_access_token(int(user["id"]), str(user["username"]))
    return TokenResponse(access_token=token)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Database = Depends(get_db)) -> TokenResponse:
    user = db.get_user_by_username(payload.username)
    if user is None or not verify_password(payload.password, str(user["password_hash"])):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return TokenResponse(access_token=create_access_token(int(user["id"]), str(user["username"])))


@app.get("/api/matches")
def list_matches(status: str = Query("all"), db: Database = Depends(get_db)) -> list[dict]:
    matches = db.list_matches(status=status)
    for match in matches:
        prediction = db.latest_prediction(str(match["match_id"]))
        match["latest_prediction"] = prediction
        match["prediction_status"] = _prediction_status(prediction, match)
        match["ev_signals"] = db.latest_ev_signals(str(match["match_id"])) if prediction else []
    return matches


@app.get("/api/matches/{match_id}")
def match_detail(match_id: str, db: Database = Depends(get_db)) -> dict:
    match = db.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
    prediction = db.latest_prediction(match_id)
    match["latest_odds"] = db.latest_odds_by_match(match_id)
    match["latest_prediction"] = prediction
    match["prediction_status"] = _prediction_status(prediction, match)
    match["ev_signals"] = db.latest_ev_signals(match_id) if prediction else []
    return match


@app.get("/api/matches/{match_id}/odds-history")
def odds_history(match_id: str, play_type: str | None = Query(None), db: Database = Depends(get_db)) -> list[dict]:
    return db.odds_history(match_id, play_type=play_type)


@app.get("/api/matches/{match_id}/prediction-history")
def prediction_history(match_id: str, db: Database = Depends(get_db)) -> dict:
    match = db.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
    points = [
        {
            "created_at": row.get("created_at"),
            "model_version": row.get("model_version"),
            "model_version_name": row.get("model_version_name"),
            "p_home": row.get("p_home"),
            "p_draw": row.get("p_draw"),
            "p_away": row.get("p_away"),
        }
        for row in db.prediction_history(match_id)
    ]
    return {
        "match_id": match_id,
        "data_status": "ok" if points else "insufficient_data",
        "points": points,
    }


@app.get("/api/matches/{match_id}/team-form")
def team_form(match_id: str, db: Database = Depends(get_db)) -> dict:
    match = db.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
    return _team_form_for_match(match)


@app.post("/api/bets", response_model=BetResponse)
def create_bet(
    payload: BetCreate,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict:
    if not is_betting_enabled():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BETTING_DISABLED_MESSAGE)
    return place_bet(db, user, payload)


@app.get("/api/bets/me")
def my_bets(user: dict = Depends(get_current_user), db: Database = Depends(get_db)) -> list[dict]:
    return db.list_user_bets(int(user["id"]))


@app.get("/api/leaderboard")
def leaderboard(db: Database = Depends(get_db)) -> list[dict]:
    return db.leaderboard()


@app.get("/api/model/suggestion", response_model=SuggestionResponse)
def model_suggestion(
    match_id: str,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> SuggestionResponse:
    signal = db.best_ev_signal(match_id)
    balance = Decimal(str(user["balance"]))
    if signal is None:
        return SuggestionResponse(
            match_id=match_id,
            suggested_stake=Decimal("0"),
            reason="no_calibrated_value_signal",
        )
    stake = suggested_stake(balance, float(signal["model_prob"]), float(signal["odds"]))
    return SuggestionResponse(
        match_id=match_id,
        play_type=str(signal["play_type"]),
        selection=str(signal["selection"]),
        model_prob=float(signal["model_prob"]),
        odds=float(signal["odds"]),
        ev=float(signal["ev"]),
        suggested_stake=stake,
    )


@app.get("/api/recap/status")
def recap_status() -> dict:
    return recap.recap_status()


@app.get("/api/recap/calibration")
def recap_calibration() -> dict:
    return recap.recap_calibration()


@app.get("/api/recap/funds")
def recap_funds() -> dict:
    return recap.recap_funds()


@app.get("/api/recap/plays")
def recap_plays() -> dict:
    return recap.recap_plays()


@app.get("/api/recaps/matches/{match_id}")
def match_recap(match_id: str) -> dict:
    return build_match_recap(match_id)


@app.get("/api/recaps/recent")
def recent_match_recaps(limit: int = Query(10, ge=1, le=50)) -> dict:
    return recent_recaps(limit=limit)


@app.get("/api/recaps/summary")
def recaps_summary() -> dict:
    return build_recap_summary()


def _prediction_status(prediction: dict | None, match: dict | None = None) -> dict:
    match = match or {}
    match_status = str(match.get("status") or "").lower()
    if match_status in {"finished", "completed"}:
        if match.get("result_home") is None or match.get("result_away") is None:
            return {
                "available": prediction is not None,
                "reason": "finished_missing_result",
                "message": "已标记完赛，但赛果尚未回填",
            }
        return {"available": prediction is not None, "reason": None, "message": "已完赛"}
    if prediction is not None:
        return {"available": True, "reason": None, "message": None}
    if match_status == "no_market":
        return {
            "available": False,
            "reason": "no_market",
            "message": "暂未开售，等待竞彩赔率",
        }
    if match_status in {"scheduled", "closed"} and _match_has_had_odds(match):
        return {
            "available": False,
            "reason": "prediction_pending",
            "message": "模型预测生成中",
        }
    return {
        "available": False,
        "reason": "missing_current_market_odds",
        "message": "该场暂未开售胜平负，预测生成中",
    }


def _team_form_for_match(match: dict) -> dict:
    home_team = str(match.get("home_team") or "").strip()
    away_team = str(match.get("away_team") or "").strip()
    cutoff = _parse_date(match.get("kickoff_at"))
    home_form = _team_form_from_history(home_team, cutoff)
    away_form = _team_form_from_history(away_team, cutoff)
    return {
        "match_id": match.get("match_id"),
        "data_status": "ok" if home_form or away_form else "insufficient_data",
        "source": "local_historical_results",
        "home_team": home_team,
        "away_team": away_team,
        "home_form": home_form,
        "away_form": away_form,
    }


def _team_form_from_history(team_name: str, cutoff: date | None, limit: int = 5) -> list[dict]:
    path = _history_results_path()
    if path is None or not path.exists():
        return []
    english_name = _to_english_team_name_safe(team_name)
    if not english_name:
        return []
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                match_date = _parse_date(row.get("date"))
                if match_date is None or (cutoff is not None and match_date >= cutoff):
                    continue
                home = str(row.get("home_team") or "").strip()
                away = str(row.get("away_team") or "").strip()
                if english_name not in {home, away}:
                    continue
                home_score = _parse_int(row.get("home_score"))
                away_score = _parse_int(row.get("away_score"))
                if home_score is None or away_score is None:
                    continue
                is_home = home == english_name
                goals_for = home_score if is_home else away_score
                goals_against = away_score if is_home else home_score
                outcome = "W" if goals_for > goals_against else "D" if goals_for == goals_against else "L"
                rows.append(
                    {
                        "date": match_date.isoformat(),
                        "opponent": away if is_home else home,
                        "score": f"{home_score}-{away_score}",
                        "home_away": "home" if is_home else "away",
                        "outcome": outcome,
                        "tournament": row.get("tournament"),
                    }
                )
    except (OSError, csv.Error, UnicodeDecodeError):
        return []
    rows.sort(key=lambda item: str(item["date"]), reverse=True)
    return rows[:limit]


def _history_results_path() -> Path | None:
    try:
        from model.history import DEFAULT_RESULTS_PATH

        return Path(DEFAULT_RESULTS_PATH)
    except Exception:
        return Path(__file__).resolve().parents[1] / "data" / "international_results.csv"


def _to_english_team_name_safe(team_name: str) -> str | None:
    clean = team_name.replace(" ", "").strip()
    if not clean:
        return None
    try:
        from model.team_names import to_english_team_name

        return to_english_team_name(clean)
    except Exception:
        return clean


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _parse_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
