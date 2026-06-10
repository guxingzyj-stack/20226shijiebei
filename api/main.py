from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from psycopg.errors import UniqueViolation

from api.auth import create_access_token, current_user_claims, hash_password, verify_password
from api.betting import place_bet, suggested_stake
from api.db import Database, get_db
from api.schemas import BetCreate, BetResponse, SuggestionResponse, TokenResponse, UserCreate, UserLogin


app = FastAPI(title="World Cup Jingcai Simulation API")


def get_current_user(
    claims: dict[str, str] = Depends(current_user_claims),
    db: Database = Depends(get_db),
) -> dict:
    user = db.get_user_by_id(int(claims["id"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


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
    return db.list_matches(status=status)


@app.get("/api/matches/{match_id}")
def match_detail(match_id: str, db: Database = Depends(get_db)) -> dict:
    match = db.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="match not found")
    prediction = db.latest_prediction(match_id)
    ev_signals = db.latest_ev_signals(match_id)
    match["latest_odds"] = db.latest_odds_by_match(match_id)
    match["latest_prediction"] = prediction
    match["score_matrix"] = prediction.get("score_matrix") if prediction else None
    match["ev_signals"] = ev_signals
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
        return SuggestionResponse(match_id=match_id, suggested_stake=Decimal("0"))
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
