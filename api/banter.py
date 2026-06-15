from __future__ import annotations

import hashlib
from typing import Any


DRAW_POOL = [
    "模型觉得这场可能闷平，进球别期待太多。",
    "平局是最容易被忽略、又最常发生的结果。",
]

BALANCED_POOL = [
    "这场五五开，猜对了算你眼光好。",
    "势均力敌，这种球最难猜，看个热闹。",
    "模型自己都拿不准，你就别太较真了。",
]

FAVORITE_POOL = [
    "赔率一边倒，但大热门翻车也不是新鲜事。",
    "{strong_team}赢面很大，不过球是圆的。",
    "看着稳，庄家可没打算让你轻松赚钱。",
]

BASE_POOL = [
    "看球图乐，赔率背后庄家早算好了账。",
    "预测仅供参考，足球的魅力就在于没有“一定”。",
]

HISTORICAL_MEMES = [
    ("japan", ("日本", "japan"), "日本是出了名的“巨人杀手”，2022 年德国、西班牙都栽在它手里。"),
    ("morocco", ("摩洛哥", "morocco"), "摩洛哥 2022 年杀进四强，别拿老眼光看非洲球队。"),
    ("saudi", ("沙特", "saudi"), "沙特 2022 年爆冷赢过阿根廷，什么都可能发生。"),
    ("korea", ("韩国", "南韩", "korea", "southkorea"), "韩国的拼劲一向不好惹，东亚球队从不好对付。"),
]

LEANING_TYPES = {"strong_home", "strong_away", "lean_home", "lean_away"}


def build_banter(
    match_id: str | None,
    home_team: str | None,
    away_team: str | None,
    p_home: float | int | str | None,
    p_draw: float | int | str | None,
    p_away: float | int | str | None,
    verdict_type: str | None,
) -> dict[str, str]:
    home = str(home_team or "主队").strip() or "主队"
    away = str(away_team or "客队").strip() or "客队"
    stable_id = str(match_id or f"{home}-{away}")

    if verdict_type == "draw_favored":
        return _from_pool(stable_id, "draw_favored", DRAW_POOL)
    if verdict_type == "balanced":
        return _from_pool(stable_id, "balanced", BALANCED_POOL)

    probs = {"home": _prob(p_home), "draw": _prob(p_draw), "away": _prob(p_away)}
    if verdict_type in LEANING_TYPES:
        meme = _historical_meme(home, away)
        if meme:
            meme_type, text = meme
            return {"banter_type": f"historical_{meme_type}", "banter": text}
        strongest = _strongest_team(home, away, probs)
        if strongest and max(v for v in probs.values() if v is not None) >= 0.65:
            text = _pick(stable_id, "favorite", FAVORITE_POOL).format(strong_team=strongest)
            return {"banter_type": "favorite", "banter": text}

    return _from_pool(stable_id, "base", BASE_POOL)


def _from_pool(match_id: str, banter_type: str, pool: list[str]) -> dict[str, str]:
    return {"banter_type": banter_type, "banter": _pick(match_id, banter_type, pool)}


def _pick(match_id: str, banter_type: str, pool: list[str]) -> str:
    digest = hashlib.sha256(f"{match_id}:{banter_type}".encode("utf-8")).hexdigest()
    return pool[int(digest[:8], 16) % len(pool)]


def _historical_meme(home_team: str, away_team: str) -> tuple[str, str] | None:
    text = _normalize_team_text(f"{home_team} {away_team}")
    for key, aliases, copy in HISTORICAL_MEMES:
        if any(_normalize_team_text(alias) in text for alias in aliases):
            return key, copy
    return None


def _strongest_team(home_team: str, away_team: str, probs: dict[str, float | None]) -> str | None:
    values: list[tuple[str, float]] = []
    for key, value in probs.items():
        if value is not None:
            values.append((key, value))
    if not values:
        return None
    key = max(values, key=lambda item: item[1])[0]
    if key == "home":
        return home_team
    if key == "away":
        return away_team
    return None


def _normalize_team_text(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _prob(value: float | int | str | None) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 1 else None
