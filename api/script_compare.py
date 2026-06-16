from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.result_source_mapping import normalize_team_name


COMPARED = "COMPARED"
PENDING = "PENDING"
NOT_YET = "NOT_YET"

COMMENT_EXACT = "剧本蒙对了比分——但这是运气，不是预言"
COMMENT_DIRECTION = "赢家猜对了，比分没中——方向易，比分难"
COMMENT_MISS = "剧本崩了——再合理的剧本，真实也不照着走"
COMMENT_PENDING = "剧本已预言，真实待揭晓"
COMMENT_NOT_YET = "即将开赛"
COMMENT_REAL_SAMPLE = "这场是已知赛果标注样本，不参与剧本能力统计"


def script_overview() -> dict[str, Any]:
    scripts, matches, predictions = _load_comparison_inputs()
    items = build_script_match_items(scripts, matches, predictions)
    return build_script_overview(items)


def script_matches(group: str | None = None, stage: str | None = None) -> dict[str, Any]:
    scripts, matches, predictions = _load_comparison_inputs(group=group, stage=stage)
    items = build_script_match_items(scripts, matches, predictions)
    return {
        "overview": build_script_overview(items),
        "matches": items,
    }


def build_script_match_items(
    script_rows: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
    prediction_rows_by_match: dict[str, dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    prediction_rows_by_match = prediction_rows_by_match or {}
    match_index = [_match_index_item(row) for row in match_rows]
    items: list[dict[str, Any]] = []
    for script in script_rows:
        script_home = normalize_team_name(script["home_team"])
        script_away = normalize_team_name(script["away_team"])
        script_pair = {script_home, script_away}
        matched = next((item for item in match_index if item["team_set"] == script_pair), None)
        item = _base_item(script, script_home, script_away)
        if matched is None:
            item.update(
                {
                    "status": NOT_YET,
                    "real_score": None,
                    "direction_hit": None,
                    "exact_hit": None,
                    "model_prob": None,
                    "comment": COMMENT_REAL_SAMPLE if item["is_real"] else COMMENT_NOT_YET,
                }
            )
            items.append(item)
            continue

        match = matched["row"]
        same_order = matched["home"] == script_home and matched["away"] == script_away
        real_home = match.get("result_home") if same_order else match.get("result_away")
        real_away = match.get("result_away") if same_order else match.get("result_home")
        match_id = str(match["match_id"])
        item.update(
            {
                "match_id": match_id,
                "match_num": match.get("match_num"),
                "kickoff_at": _json_value(match.get("kickoff_at")),
                "match_status": match.get("status"),
                "model_prob": extract_model_prob(prediction_rows_by_match.get(match_id)),
            }
        )
        if not _is_compared_match(match, real_home, real_away):
            item.update(
                {
                    "status": PENDING,
                    "real_score": None,
                    "direction_hit": None,
                    "exact_hit": None,
                    "comment": COMMENT_REAL_SAMPLE if item["is_real"] else COMMENT_PENDING,
                }
            )
            items.append(item)
            continue

        script_home_score = int(script["script_home"])
        script_away_score = int(script["script_away"])
        real_home_score = int(real_home)
        real_away_score = int(real_away)
        direction_hit = outcome(script_home_score, script_away_score) == outcome(real_home_score, real_away_score)
        exact_hit = script_home_score == real_home_score and script_away_score == real_away_score
        item.update(
            {
                "status": COMPARED,
                "real_score": f"{real_home_score}:{real_away_score}",
                "direction_hit": direction_hit,
                "exact_hit": exact_hit,
                "comment": COMMENT_REAL_SAMPLE if item["is_real"] else _comment(direction_hit, exact_hit),
            }
        )
        items.append(item)
    return items


def build_script_overview(items: list[dict[str, Any]]) -> dict[str, Any]:
    compared = [item for item in items if item.get("status") == COMPARED]
    real_compared = [item for item in compared if item.get("is_real") is True]
    script_compared = [item for item in compared if item.get("is_real") is not True]
    all_count = len(compared)
    all_direction_hits = _count_hits(compared, "direction_hit")
    all_exact_hits = _count_hits(compared, "exact_hit")
    real_count = len(real_compared)
    real_direction_hits = _count_hits(real_compared, "direction_hit")
    real_exact_hits = _count_hits(real_compared, "exact_hit")
    script_count = len(script_compared)
    script_direction_hits = _count_hits(script_compared, "direction_hit")
    script_exact_hits = _count_hits(script_compared, "exact_hit")
    return {
        "total_predictions": len(items),
        "compared_count": all_count,
        "pending_count": sum(1 for item in items if item.get("status") == PENDING),
        "not_yet_count": sum(1 for item in items if item.get("status") == NOT_YET),
        "all_direction_hits": all_direction_hits,
        "all_exact_hits": all_exact_hits,
        "all_direction_accuracy": _accuracy(all_direction_hits, all_count),
        "all_exact_accuracy": _accuracy(all_exact_hits, all_count),
        "real_count": real_count,
        "real_direction_hits": real_direction_hits,
        "real_exact_hits": real_exact_hits,
        "real_direction_accuracy": _accuracy(real_direction_hits, real_count),
        "real_exact_accuracy": _accuracy(real_exact_hits, real_count),
        "script_count": script_count,
        "script_direction_hits": script_direction_hits,
        "script_exact_hits": script_exact_hits,
        "script_direction_accuracy": _accuracy(script_direction_hits, script_count),
        "script_exact_accuracy": _accuracy(script_exact_hits, script_count),
        "direction_hits": script_direction_hits,
        "exact_hits": script_exact_hits,
        "direction_accuracy": _accuracy(script_direction_hits, script_count),
        "exact_accuracy": _accuracy(script_exact_hits, script_count),
    }


def outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if away_score > home_score:
        return "A"
    return "D"


def extract_model_prob(prediction: dict[str, Any] | None) -> dict[str, float] | None:
    if not prediction:
        return None
    direct = _extract_prob_triplet(
        prediction,
        [
            ("p_home", "p_draw", "p_away"),
            ("prob_home", "prob_draw", "prob_away"),
            ("home_prob", "draw_prob", "away_prob"),
        ],
    )
    if direct:
        return direct
    probabilities = prediction.get("probabilities")
    if isinstance(probabilities, dict):
        return _extract_prob_triplet(probabilities, [("home", "draw", "away"), ("p_home", "p_draw", "p_away")])
    return None


def _load_comparison_inputs(
    group: str | None = None,
    stage: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any] | None]]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        scripts = _load_script_rows(cur)
        if group:
            scripts = [row for row in scripts if _group_matches(str(row["grp"]), group)]
        if stage:
            scripts = [row for row in scripts if str(row["stage"]).lower() == stage.lower()]
        matches = _load_match_rows(cur)
        provisional = build_script_match_items(scripts, matches, {})
        match_ids = [str(item["match_id"]) for item in provisional if item.get("match_id")]
        predictions = _load_latest_predictions(cur, match_ids)
    return scripts, matches, predictions


def _load_script_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, grp, stage, home_team, away_team, script_home, script_away, narrative, is_real
        FROM script_predictions
        ORDER BY grp, id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _load_match_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT match_id, match_num, home_team, away_team, kickoff_at, status, result_home, result_away
        FROM matches
        ORDER BY kickoff_at, match_id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def _load_latest_predictions(cur: Any, match_ids: list[str]) -> dict[str, dict[str, Any] | None]:
    rows: dict[str, dict[str, Any] | None] = {}
    for match_id in dict.fromkeys(match_ids):
        cur.execute(
            """
            SELECT id, match_id, model_version, p_home, p_draw, p_away, created_at
            FROM predictions
            WHERE match_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (match_id,),
        )
        row = cur.fetchone()
        rows[match_id] = dict(row) if row else None
    return rows


def _base_item(script: dict[str, Any], home_team: str, away_team: str) -> dict[str, Any]:
    is_real = bool(script.get("is_real", False))
    return {
        "group": script["grp"],
        "stage": script["stage"],
        "home_team": home_team,
        "away_team": away_team,
        "script_score": f"{int(script['script_home'])}:{int(script['script_away'])}",
        "narrative": script.get("narrative"),
        "match_id": None,
        "match_num": None,
        "kickoff_at": None,
        "match_status": None,
        "is_real": is_real,
        "sample_type": "known_result_seed" if is_real else "script_projection",
        "excluded_from_prediction_metrics": is_real,
    }


def _match_index_item(row: dict[str, Any]) -> dict[str, Any]:
    home = normalize_team_name(row["home_team"])
    away = normalize_team_name(row["away_team"])
    return {
        "row": row,
        "home": home,
        "away": away,
        "team_set": {home, away},
    }


def _is_compared_match(match: dict[str, Any], real_home: Any, real_away: Any) -> bool:
    return (
        str(match.get("status") or "").lower() in {"finished", "completed"}
        and real_home is not None
        and real_away is not None
    )


def _comment(direction_hit: bool, exact_hit: bool) -> str:
    if exact_hit:
        return COMMENT_EXACT
    if direction_hit:
        return COMMENT_DIRECTION
    return COMMENT_MISS


def _count_hits(items: list[dict[str, Any]], field: str) -> int:
    return sum(1 for item in items if item.get(field) is True)


def _accuracy(hits: int, total: int) -> float | None:
    return hits / total if total else None


def _extract_prob_triplet(source: dict[str, Any], key_sets: list[tuple[str, str, str]]) -> dict[str, float] | None:
    for home_key, draw_key, away_key in key_sets:
        if home_key not in source or draw_key not in source or away_key not in source:
            continue
        values = [_to_float(source.get(home_key)), _to_float(source.get(draw_key)), _to_float(source.get(away_key))]
        if all(value is not None for value in values):
            return {"home": values[0], "draw": values[1], "away": values[2]}  # type: ignore[index]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _group_matches(value: str, query: str) -> bool:
    value = value.upper()
    query = query.strip().upper()
    if "-" not in query:
        return value == query
    start, end = [part.strip() for part in query.split("-", 1)]
    if len(start) != 1 or len(end) != 1:
        return value == query
    return start <= value <= end
