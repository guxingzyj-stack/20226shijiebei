from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
import os

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg.errors import UniqueViolation

from api.auth import create_access_token, current_user_claims, hash_password, verify_password
from api.betting import BETTING_DISABLED_MESSAGE, is_betting_enabled, place_bet, suggested_stake
from api.db import Database, get_db
from api import recap
from api.scheduler import start_api_scheduler, stop_api_scheduler
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
    return {
        "ok": True,
        "scheduler_last_seen": freshness["scheduler_last_seen"],
        "scheduler_last_seen_age_minutes": freshness["scheduler_last_seen_age_minutes"],
        "scheduler_stale": freshness["scheduler_stale"],
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
def list_matches(status: str = Query("upcoming"), db: Database = Depends(get_db)) -> list[dict]:
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
            "message": "prediction pending",
        }
    return {
        "available": False,
        "reason": "missing_current_market_odds",
        "message": "该场暂未开售胜平负，预测生成中",
    }
