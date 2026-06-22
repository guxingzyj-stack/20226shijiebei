from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BetLegIn(BaseModel):
    match_id: str
    play_type: str
    selection: str
    odds: Decimal | None = None


class BetCreate(BaseModel):
    legs: list[BetLegIn] | None = None
    match_id: str | None = None
    play_type: str | None = None
    selection: str | None = None
    parlay: str
    stake: Decimal = Field(gt=0)

    def bet_legs(self) -> list[BetLegIn]:
        if self.legs is not None:
            return self.legs
        if self.match_id and self.play_type and self.selection:
            return [BetLegIn(match_id=self.match_id, play_type=self.play_type, selection=self.selection)]
        return []


class BetResponse(BaseModel):
    id: int
    legs: list[dict[str, Any]]
    parlay: str
    stake: Decimal
    potential_payout: Decimal
    status: str
    balance: Decimal | None = None


class SuggestionResponse(BaseModel):
    match_id: str
    play_type: str | None = None
    selection: str | None = None
    model_prob: float | None = None
    odds: float | None = None
    ev: float | None = None
    suggested_stake: Decimal
    reason: str | None = None
