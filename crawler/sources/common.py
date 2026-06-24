from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


PLAY_TYPES = ("had", "hhad", "crs", "ttg", "hafu")
WORLD_CUP_KEYWORDS = ("世界杯", "世界盃", "World Cup", "WORLD CUP")


@dataclass
class OddsEntry:
    play_type: str
    odds: dict[str, float | int | str]
    goal_line: Decimal | None = None


@dataclass
class MatchOdds:
    match_id: str
    match_num: str | None
    league: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    stage: str | None = None
    group_name: str | None = None
    result_home: int | None = None
    result_away: int | None = None
    status: str = "scheduled"
    odds: list[OddsEntry] = field(default_factory=list)
    match_id_source: str | None = None
    persistence_skip_reason: str | None = None


class SourceError(RuntimeError):
    pass


def is_world_cup_league(value: Any) -> bool:
    text = str(value or "")
    return any(keyword.lower() in text.lower() for keyword in WORLD_CUP_KEYWORDS)


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]
    normalized = text.replace("T", " ").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in candidates:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clean_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
