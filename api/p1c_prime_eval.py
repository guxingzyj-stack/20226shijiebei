from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import math
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from api.db import connect


CURRENT_W_DC = 0.3
CURRENT_W_MARKET = 0.7
CANDIDATE_W_DC = [0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]
OUTCOMES = ("3", "1", "0")
REPORT_PATH = Path("docs/reports/P1C_PRIME_30_MATCH_EVAL.md")


@dataclass(frozen=True)
class EvalRow:
    match_id: str
    match_num: str | None
    home_team: str
    away_team: str
    kickoff_at: datetime
    result_home: int
    result_away: int
    actual_outcome: str
    prediction_id: int
    prediction_created_at: datetime
    model_version: int
    dc: dict[str, float]
    market: dict[str, float]


def generate_report() -> dict[str, Any]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        counts = _load_counts(cur)
        rows, excluded = _load_eval_rows(cur)
    evaluation = evaluate_rows(rows)
    recommendation = recommend_weight(evaluation, len(rows))
    return {
        "mode": "read-only",
        "writes_db": False,
        "sample": {
            **counts,
            "included_matches": len(rows),
            "excluded_matches": excluded,
            "p1c_ready": int(counts["usable_finished_matches"]) >= 30,
        },
        "current_weights": {"w_dc": CURRENT_W_DC, "w_market": CURRENT_W_MARKET},
        "evaluation": evaluation,
        "recommendation": recommendation,
        "matches": [row_to_dict(row) for row in rows],
    }


def evaluate_rows(rows: list[EvalRow]) -> dict[str, Any]:
    schemes: dict[str, list[dict[str, float]]] = {
        "market-only": [row.market for row in rows],
        "dc-only": [row.dc for row in rows],
        "current 0.3/0.7": [blend_probs(row.dc, row.market, CURRENT_W_DC) for row in rows],
    }
    for weight in CANDIDATE_W_DC:
        schemes[f"candidate {weight:g}/{1 - weight:g}"] = [blend_probs(row.dc, row.market, weight) for row in rows]
    outcomes = [row.actual_outcome for row in rows]
    metric_table = {name: metrics_for(probs, outcomes) for name, probs in schemes.items()}
    current_probs = schemes["current 0.3/0.7"]
    return {
        "metrics": metric_table,
        "candidate_weights": {weight: metric_table[f"candidate {weight:g}/{1 - weight:g}"] for weight in CANDIDATE_W_DC},
        "calibration": calibration_table(current_probs, outcomes),
        "strata": strata_table(rows, current_probs),
    }


def recommend_weight(evaluation: dict[str, Any], sample_size: int) -> dict[str, Any]:
    if sample_size < 30:
        return {
            "choice": "C",
            "recommended_weight": None,
            "change_now": False,
            "reason": "样本不足 30 场，不建议调整生产权重。",
        }
    metrics = evaluation["metrics"]
    current = metrics["current 0.3/0.7"]
    candidate_items = [(name, value) for name, value in metrics.items() if name.startswith("candidate ")]
    best_name, best_metrics = min(candidate_items, key=lambda item: (item[1]["rps"], item[1]["brier"], item[0]))
    rps_gain = current["rps"] - best_metrics["rps"]
    if best_name == "candidate 0.3/0.7" or rps_gain < 0.005:
        return {
            "choice": "A",
            "recommended_weight": "0.3/0.7",
            "change_now": False,
            "reason": "候选权重相对当前权重的 RPS 改善不足 0.005；30 场小样本下优先稳定，不建议立即调整。",
        }
    if best_metrics["logloss"] <= current["logloss"] and best_metrics["brier"] <= current["brier"]:
        return {
            "choice": "B",
            "recommended_weight": best_name.replace("candidate ", ""),
            "change_now": False,
            "reason": "候选权重在 RPS/Brier/LogLoss 上均不劣于当前值，但仍需人工确认后才能修改生产权重。",
        }
    return {
        "choice": "A",
        "recommended_weight": "0.3/0.7",
        "change_now": False,
        "reason": "指标存在冲突，按稳定性原则继续保持当前生产权重。",
    }


def _load_counts(cur: Any) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          count(*) FILTER (
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
          ) AS usable_finished_matches,
          count(*) FILTER (
            WHERE status IN ('finished', 'completed')
              AND (result_home IS NULL OR result_away IS NULL)
          ) AS finished_missing_result,
          count(*) FILTER (
            WHERE status NOT IN ('finished', 'completed')
              AND (result_home IS NOT NULL OR result_away IS NOT NULL)
          ) AS non_finished_with_result
        FROM matches
        """
    )
    row = dict(cur.fetchone())
    return {key: int(row.get(key) or 0) for key in row}


def _load_eval_rows(cur: Any) -> tuple[list[EvalRow], dict[str, int]]:
    cur.execute(
        """
        SELECT
          m.match_id,
          m.match_num,
          m.home_team,
          m.away_team,
          m.kickoff_at,
          m.result_home,
          m.result_away,
          p.id AS prediction_id,
          p.created_at AS prediction_created_at,
          p.model_version,
          p.p_home,
          p.p_draw,
          p.p_away,
          o.odds AS market_odds,
          o.fetched_at AS market_fetched_at
        FROM matches m
        LEFT JOIN LATERAL (
          SELECT id, created_at, model_version, p_home, p_draw, p_away
          FROM predictions
          WHERE predictions.match_id = m.match_id
            AND predictions.created_at <= m.kickoff_at
          ORDER BY created_at DESC, id DESC
          LIMIT 1
        ) p ON true
        LEFT JOIN LATERAL (
          SELECT id, odds, fetched_at
          FROM odds_snapshots
          WHERE odds_snapshots.match_id = m.match_id
            AND play_type = 'had'
            AND fetched_at <= m.kickoff_at
          ORDER BY fetched_at DESC, id DESC
          LIMIT 1
        ) o ON true
        WHERE m.status IN ('finished', 'completed')
          AND m.result_home IS NOT NULL
          AND m.result_away IS NOT NULL
        ORDER BY m.kickoff_at, m.match_id
        """
    )
    rows: list[EvalRow] = []
    excluded = {"missing_prediction": 0, "missing_market": 0, "invalid_market": 0}
    for record in cur.fetchall():
        if record["prediction_id"] is None:
            excluded["missing_prediction"] += 1
            continue
        odds = dict(record.get("market_odds") or {})
        if not odds:
            excluded["missing_market"] += 1
            continue
        if set(map(str, odds)) < set(OUTCOMES):
            excluded["invalid_market"] += 1
            continue
        market = shin_devig_three_way({key: float(odds[key]) for key in OUTCOMES})
        dc = normalize_probs({"3": float(record["p_home"]), "1": float(record["p_draw"]), "0": float(record["p_away"])})
        result_home = int(record["result_home"])
        result_away = int(record["result_away"])
        rows.append(
            EvalRow(
                match_id=str(record["match_id"]),
                match_num=record.get("match_num"),
                home_team=str(record.get("home_team") or ""),
                away_team=str(record.get("away_team") or ""),
                kickoff_at=record["kickoff_at"],
                result_home=result_home,
                result_away=result_away,
                actual_outcome=actual_outcome(result_home, result_away),
                prediction_id=int(record["prediction_id"]),
                prediction_created_at=record["prediction_created_at"],
                model_version=int(record["model_version"]),
                dc=dc,
                market=market,
            )
        )
    return rows, excluded


def row_to_dict(row: EvalRow) -> dict[str, Any]:
    return {
        "match_id": row.match_id,
        "match_num": row.match_num,
        "home_team": row.home_team,
        "away_team": row.away_team,
        "kickoff_at": row.kickoff_at.isoformat(),
        "result_home": row.result_home,
        "result_away": row.result_away,
        "actual_outcome": row.actual_outcome,
        "prediction_id": row.prediction_id,
        "prediction_created_at": row.prediction_created_at.isoformat(),
        "model_version": row.model_version,
        "p_home": row.dc["3"],
        "p_draw": row.dc["1"],
        "p_away": row.dc["0"],
        "market_home": row.market["3"],
        "market_draw": row.market["1"],
        "market_away": row.market["0"],
    }


def metrics_for(probs_list: list[dict[str, float]], outcomes: list[str]) -> dict[str, float]:
    if not probs_list:
        return {"brier": math.nan, "rps": math.nan, "logloss": math.nan, "top1_accuracy": math.nan}
    return {
        "brier": sum(brier_score(probs, outcome) for probs, outcome in zip(probs_list, outcomes)) / len(probs_list),
        "rps": sum(rps_score(probs, outcome) for probs, outcome in zip(probs_list, outcomes)) / len(probs_list),
        "logloss": sum(logloss(probs, outcome) for probs, outcome in zip(probs_list, outcomes)) / len(probs_list),
        "top1_accuracy": sum(1 for probs, outcome in zip(probs_list, outcomes) if top_outcome(probs) == outcome) / len(probs_list),
    }


def brier_score(probs: dict[str, float], outcome: str) -> float:
    return sum((probs[key] - (1.0 if key == outcome else 0.0)) ** 2 for key in OUTCOMES) / 3


def rps_score(probs: dict[str, float], outcome: str) -> float:
    observed = {key: 1.0 if key == outcome else 0.0 for key in OUTCOMES}
    score = 0.0
    p_cum = 0.0
    y_cum = 0.0
    for key in OUTCOMES[:-1]:
        p_cum += probs[key]
        y_cum += observed[key]
        score += (p_cum - y_cum) ** 2
    return score / (len(OUTCOMES) - 1)


def logloss(probs: dict[str, float], outcome: str, epsilon: float = 1e-12) -> float:
    return -math.log(max(float(probs[outcome]), epsilon))


def blend_probs(dc: dict[str, float], market: dict[str, float], w_dc: float) -> dict[str, float]:
    return normalize_probs({key: w_dc * dc[key] + (1.0 - w_dc) * market[key] for key in OUTCOMES})


def calibration_table(probs_list: list[dict[str, float]], outcomes: list[str]) -> list[dict[str, Any]]:
    bins = [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.01)]
    rows: list[dict[str, Any]] = []
    for lo, hi in bins:
        bucket = [(max(probs.values()), top_outcome(probs) == outcome) for probs, outcome in zip(probs_list, outcomes) if lo <= max(probs.values()) < hi]
        rows.append(
            {
                "bin": f"{lo:.2f}-{hi if hi < 1 else '1.00'}",
                "count": len(bucket),
                "avg_confidence": sum(item[0] for item in bucket) / len(bucket) if bucket else None,
                "hit_rate": sum(1 for _, hit in bucket if hit) / len(bucket) if bucket else None,
                "note": "不稳定，仅参考" if len(bucket) < 5 else "",
            }
        )
    return rows


def strata_table(rows: list[EvalRow], current_probs: list[dict[str, float]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[tuple[dict[str, float], str]]] = {"favorite": [], "balanced": [], "underdog": []}
    for row, probs in zip(rows, current_probs):
        label = stratum(row)
        grouped[label].append((probs, row.actual_outcome))
    return {key: {"count": len(values), **metrics_for([p for p, _ in values], [o for _, o in values])} for key, values in grouped.items()}


def stratum(row: EvalRow) -> str:
    actual_market_prob = row.market[row.actual_outcome]
    max_market_prob = max(row.market.values())
    if actual_market_prob < 0.30:
        return "underdog"
    if max_market_prob < 0.45:
        return "balanced"
    return "favorite"


def actual_outcome(home: int, away: int) -> str:
    if home > away:
        return "3"
    if home == away:
        return "1"
    return "0"


def top_outcome(probs: dict[str, float]) -> str:
    return max(OUTCOMES, key=lambda key: (probs[key], key))


def normalize_probs(probs: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(value)) for value in probs.values())
    if total <= 0:
        raise ValueError("probabilities must sum to a positive value")
    return {key: max(0.0, float(value)) / total for key, value in probs.items()}


def shin_devig_three_way(odds: dict[str, float]) -> dict[str, float]:
    if set(odds) != set(OUTCOMES):
        raise ValueError("Shin devig requires exactly 3/1/0 odds")
    if any(float(value) <= 0 for value in odds.values()):
        raise ValueError("odds must be positive")
    best_z = 0.0
    best_error = float("inf")
    best_probs: dict[str, float] | None = None
    for step in range(501):
        z = step / 10000
        raw = _shin_raw_probs(odds, z)
        error = abs(sum(raw.values()) - 1.0)
        if error < best_error:
            best_error = error
            best_z = z
            best_probs = raw
    _ = best_z
    return normalize_probs(best_probs or {})


def _shin_raw_probs(odds: dict[str, float], z: float) -> dict[str, float]:
    implied = {key: 1.0 / float(value) for key, value in odds.items()}
    beta = sum(implied.values())
    if z >= 1:
        raise ValueError("z must be below 1")
    return {
        key: (math.sqrt(z * z + 4 * (1 - z) * pi * pi / beta) - z) / (2 * (1 - z))
        for key, pi in implied.items()
    }


def render_markdown(report: dict[str, Any]) -> str:
    sample = report["sample"]
    rec = report["recommendation"]
    lines = [
        "# P1-C′ 30场样本权重定案评估报告",
        "",
        "## 1. 样本概况",
        f"- usable_finished_matches: {sample['usable_finished_matches']}",
        f"- included_matches: {sample['included_matches']}",
        f"- excluded_matches: {sample['excluded_matches']}",
        f"- finished_missing_result: {sample['finished_missing_result']}",
        f"- non_finished_with_result: {sample['non_finished_with_result']}",
        f"- p1c_ready: {sample['p1c_ready']}",
        "",
        "## 2. 当前生产权重",
        f"- w_dc: {CURRENT_W_DC}",
        f"- w_market: {CURRENT_W_MARKET}",
        "- 注意：本报告不修改生产权重。",
        "",
        "## 3. 评估指标总表",
        "| 方案 | Brier | RPS | LogLoss | Top1 Accuracy | 备注 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, metrics in report["evaluation"]["metrics"].items():
        note = "当前生产权重" if name == "current 0.3/0.7" else ""
        lines.append(f"| {name} | {_fmt(metrics['brier'])} | {_fmt(metrics['rps'])} | {_fmt(metrics['logloss'])} | {_fmt(metrics['top1_accuracy'])} | {note} |")
    lines += [
        "",
        "## 4. 候选权重表现",
        "候选权重仅在内存中评估，没有写入 `model_versions`、`predictions` 或任何生产表。",
        "",
        "## 5. 市场 vs DC vs 融合",
        "- market-only 代表纯市场去水概率。",
        "- dc-only 代表赛前 DC 模型概率。",
        "- fusion 使用 `p_final = w_dc * p_dc + w_market * p_market` 后归一化。",
        "",
        "## 6. 分层表现",
        "| 分层 | 样本数 | Brier | RPS | LogLoss | Top1 Accuracy |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in report["evaluation"]["strata"].items():
        lines.append(f"| {name} | {metrics['count']} | {_fmt(metrics['brier'])} | {_fmt(metrics['rps'])} | {_fmt(metrics['logloss'])} | {_fmt(metrics['top1_accuracy'])} |")
    lines += [
        "",
        "## 7. 校准观察",
        "| 置信度分档 | 样本数 | 平均置信度 | 实际命中率 | 备注 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in report["evaluation"]["calibration"]:
        lines.append(f"| {row['bin']} | {row['count']} | {_fmt(row['avg_confidence'])} | {_fmt(row['hit_rate'])} | {row['note']} |")
    lines += [
        "",
        "## 8. 风险与限制",
        "- 样本只有约 30 场，仍然不足以证明长期优势。",
        "- 小组赛阶段分布有限，不应为短期命中率过拟合。",
        "- 本报告不用于真实投注开放。",
        "",
        "## 9. 建议",
        f"- 选择: {rec['choice']}",
        f"- 推荐权重: {rec['recommended_weight']}",
        f"- 是否建议立即改生产: {rec['change_now']}",
        f"- 原因: {rec['reason']}",
        "",
        "## 10. 后续动作",
        "- 建议在 45/60 场后再做二次评估。",
        "- BETTING_ENABLED 继续保持 false，除非投注开放闸门另行通过。",
        "- 若人工确认调整权重，应单独开生产变更任务。",
    ]
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and math.isnan(value):
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C′ 30-match read-only weight evaluation")
    parser.add_argument("--read-only", action="store_true", help="required safety flag; no production table is written")
    parser.add_argument("--no-write-report", action="store_true", help="print only; do not write markdown report")
    args = parser.parse_args(argv)
    if not args.read_only:
        parser.error("--read-only is required")
    report = generate_report()
    path = None if args.no_write_report else write_report(report)
    print("P1-C Prime 30 Match Eval")
    print(f"- mode: {report['mode']}")
    print(f"- writes_db: {report['writes_db']}")
    print(f"- included_matches: {report['sample']['included_matches']}")
    print(f"- recommendation: {report['recommendation']['recommended_weight']}")
    print(f"- change_now: {report['recommendation']['change_now']}")
    print(f"- report_path: {path or 'not_written'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
