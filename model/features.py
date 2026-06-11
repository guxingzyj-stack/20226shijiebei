from __future__ import annotations

from datetime import date, datetime, timezone
from math import log1p
from statistics import median
from typing import Any


FEATURE_KEYS = (
    "elo",
    "squad_value_total",
    "squad_value_median",
    "core_minutes_share",
    "core_xg_xa_per90",
    "avg_age",
    "injured_core_count",
)


def build_team_feature_snapshot(
    team: str,
    ratings: dict[str, float],
    players: list[dict[str, Any]],
    stats: list[dict[str, Any]],
    injuries: list[dict[str, Any]],
) -> dict[str, Any]:
    team_players = [row for row in players if _same_team(row.get("team"), team)]
    player_keys = {str(row.get("player_key")) for row in team_players if row.get("player_key")}
    team_stats = [row for row in stats if str(row.get("player_key")) in player_keys]
    team_injuries = [row for row in injuries if _same_team(row.get("team"), team) or str(row.get("player_key")) in player_keys]

    values = [_number(row.get("market_value")) for row in team_players if _number(row.get("market_value")) is not None]
    minutes_by_player = _sum_by_key(team_stats, "minutes")
    total_minutes = sum(minutes_by_player.values())
    core_keys = {key for key, minutes in minutes_by_player.items() if total_minutes > 0 and minutes / total_minutes >= 0.05}
    core_minutes = sum(minutes_by_player.get(key, 0.0) for key in core_keys)
    core_stats = [row for row in team_stats if str(row.get("player_key")) in core_keys]
    core_minutes_for_rate = sum(_number(row.get("minutes")) or 0.0 for row in core_stats)
    core_xg_xa = sum((_number(row.get("xg")) or 0.0) + (_number(row.get("xa")) or 0.0) for row in core_stats)
    ages = [_age(row.get("birth_date")) for row in team_players if _age(row.get("birth_date")) is not None]

    feature_values = {
        "elo": float(ratings.get(team, 1500.0)),
        "squad_value_total": sum(values) if values else None,
        "squad_value_median": median(values) if values else None,
        "core_minutes_share": core_minutes / total_minutes if total_minutes > 0 else None,
        "core_xg_xa_per90": core_xg_xa / core_minutes_for_rate * 90 if core_minutes_for_rate > 0 else None,
        "avg_age": sum(ages) / len(ages) if ages else None,
        "injured_core_count": _injured_core_count(team_injuries, core_keys),
    }
    output: dict[str, Any] = {"team": team}
    for key in FEATURE_KEYS:
        missing = feature_values[key] is None
        output[key] = 0.0 if missing else feature_values[key]
        output[f"missing_{key}"] = missing
    return output


def build_match_features(
    home_team: str,
    away_team: str,
    home_features: dict[str, Any],
    away_features: dict[str, Any],
) -> dict[str, Any]:
    home = _filled_features(home_features)
    away = _filled_features(away_features)
    features = {
        "home_team": home_team,
        "away_team": away_team,
        "elo_diff": home["elo"] - away["elo"],
        "squad_value_log_diff": log1p(home["squad_value_total"]) - log1p(away["squad_value_total"]),
        "core_minutes_share_diff": home["core_minutes_share"] - away["core_minutes_share"],
        "core_xg_xa_per90_diff": home["core_xg_xa_per90"] - away["core_xg_xa_per90"],
        "avg_age_diff": home["avg_age"] - away["avg_age"],
        "injured_core_count_diff": home["injured_core_count"] - away["injured_core_count"],
        "is_home": 1,
    }
    for key in FEATURE_KEYS:
        features[f"home_missing_{key}"] = bool(home_features.get(f"missing_{key}", True))
        features[f"away_missing_{key}"] = bool(away_features.get(f"missing_{key}", True))
    return features


def _filled_features(features: dict[str, Any]) -> dict[str, float]:
    return {key: float(features.get(key) or 0.0) for key in FEATURE_KEYS}


def _same_team(value: Any, team: str) -> bool:
    return str(value or "").strip() == team


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_by_key(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        key = row.get("player_key")
        if not key:
            continue
        totals[str(key)] = totals.get(str(key), 0.0) + (_number(row.get(field)) or 0.0)
    return totals


def _age(value: Any) -> float | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            born = date.fromisoformat(value)
        except ValueError:
            return None
    elif isinstance(value, datetime):
        born = value.date()
    elif isinstance(value, date):
        born = value
    else:
        return None
    today = datetime.now(timezone.utc).date()
    return (today - born).days / 365.25


def _injured_core_count(injuries: list[dict[str, Any]], core_keys: set[str]) -> int:
    active_statuses = {"out", "injured", "doubtful", "suspended", "unavailable"}
    count = 0
    for row in injuries:
        if str(row.get("player_key")) in core_keys and str(row.get("status") or "").lower() in active_statuses:
            count += 1
    return count
