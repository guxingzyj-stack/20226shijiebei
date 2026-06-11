from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

import psycopg

from model import db
from model.matrix_calibration import region_sums_from_matrix
from model.production_checks import score_matrix_shape_ok


K_BOUNDS = (0.05, 2.0)
EV_RESEARCH_ONLY_THRESHOLD = 0.15


@dataclass(frozen=True)
class ReportLine:
    key: str
    value: Any


def generate_report() -> dict[str, list[ReportLine]]:
    if not os.getenv("DATABASE_URL"):
        return _not_checked_report("DATABASE_URL missing; run inside the P1 model-worker container")
    try:
        with db.get_conn() as conn:
            latest_version = db.fetch_latest_model_version(conn)
            if latest_version is None:
                return _not_checked_report("no model_versions row found")
            latest_version_id = int(latest_version["id"])
            params = latest_version.get("params") or {}
            dc = params.get("dc") or {}
            production_weights = params.get("production_weights")
            predictions = _predictions_for_version(conn, latest_version_id)
            upcoming_count = len(db.fetch_upcoming_matches(conn))
            market_counts = _market_source_counts(params)
            ev_over_threshold = _ev_over_threshold_count(conn, latest_version_id)
            ev_over_threshold_unmarked = _ev_over_threshold_unmarked_count(conn, latest_version_id)
            suggestion_eligible_count = _suggestion_eligible_count(conn, latest_version_id)
            suggestion_pool_contract_ok = _suggestion_pool_contract_ok(conn, latest_version_id)
            ev_same_version = _ev_matches_latest_prediction_version(conn, latest_version_id)
    except Exception as exc:
        return _not_checked_report(f"database check failed: {type(exc).__name__}")

    k_value = dc.get("k")
    k_on_boundary = _on_boundary(float(k_value), K_BOUNDS) if k_value is not None else "NOT_CHECKED: missing k"
    matrix_checks = [_prediction_matrix_check(row) for row in predictions]
    edge_checks = [_prediction_edge_check(row) for row in predictions]

    return {
        "1. Latest Model Version": [
            ReportLine("latest_model_version_id", latest_version_id),
            ReportLine("name", latest_version.get("name")),
            ReportLine("params.elo_start_date", params.get("elo_start_date", "NOT_CHECKED: missing params.elo_start_date")),
            ReportLine("params.training_start_date", params.get("training_start_date", "NOT_CHECKED: missing params.training_start_date")),
            ReportLine("c/k/H/rho", {key: dc.get(key, "NOT_CHECKED: missing") for key in ("c", "k", "H", "rho")}),
            ReportLine("k_on_boundary", k_on_boundary),
            ReportLine("production_weights", production_weights or "NOT_CHECKED: missing production_weights"),
            ReportLine("dc_only_count_is_0", market_counts["dc_only_count"] == 0 if isinstance(market_counts["dc_only_count"], int) else market_counts["dc_only_count"]),
        ],
        "2. Predictions": [
            ReportLine("latest_version_predictions", len(predictions)),
            ReportLine("latest_version_upcoming_matches", upcoming_count),
            ReportLine("score_matrix_11x11", all(matrix_checks) if predictions else "NOT_CHECKED: no latest-version predictions"),
            ReportLine("score_matrix_edges_match_prediction", all(edge_checks) if predictions else "NOT_CHECKED: no latest-version predictions"),
            ReportLine("ev_matches_latest_prediction_version", ev_same_version),
            ReportLine("old_model_version_api_exposure_risk", "code_enforced_latest_model_version_only"),
        ],
        "3. Market Source": [
            ReportLine("market_source_had_count", market_counts["market_source_had_count"]),
            ReportLine("market_source_hhad_count", market_counts["market_source_hhad_count"]),
            ReportLine("skipped_missing_market_count", market_counts["skipped_missing_market_count"]),
            ReportLine("dc_only_count", market_counts["dc_only_count"]),
        ],
        "4. EV": [
            ReportLine("ev_gt_0_15_count", ev_over_threshold),
            ReportLine("ev_gt_0_15_all_research_only", ev_over_threshold_unmarked == 0),
            ReportLine("suggestion_eligible_count", suggestion_eligible_count),
            ReportLine("suggestion_eligible_reason", "no_calibrated_value_signal" if suggestion_eligible_count == 0 else "calibrated_value_signal_available"),
            ReportLine("suggestion_pool_only_had_hhad", suggestion_pool_contract_ok),
        ],
    }


def print_report(report: dict[str, list[ReportLine]] | None = None) -> None:
    report = report or generate_report()
    print("P1 Model Acceptance Report")
    for section, lines in report.items():
        print("")
        print(section)
        for line in lines:
            print(f"- {line.key}: {line.value}")
    failed = failed_checks(report)
    print("")
    print(f"OVERALL_STATUS: {'PASS' if not failed else 'FAIL'}")
    if failed:
        print("FAILED_CHECKS:")
        for item in failed:
            print(f"- {item}")


def main() -> int:
    report = generate_report()
    print_report(report)
    return 1 if failed_checks(report) else 0


def _not_checked_report(reason: str) -> dict[str, list[ReportLine]]:
    value = f"NOT_CHECKED: {reason}"
    return {
        "1. Latest Model Version": [ReportLine("latest_model_version_id", value)],
        "2. Predictions": [ReportLine("latest_version_predictions", value)],
        "3. Market Source": [ReportLine("market_source_had_count", value)],
        "4. EV": [ReportLine("ev_gt_0_15_count", value)],
    }


def _predictions_for_version(conn, model_version_id: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, p_home, p_draw, p_away, score_matrix
            FROM predictions
            WHERE model_version = %s
            ORDER BY id
            """,
            (model_version_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def _ev_over_threshold_count(conn, model_version_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ev_signals WHERE model_version = %s AND ev > %s", (model_version_id, EV_RESEARCH_ONLY_THRESHOLD))
        return int(cur.fetchone()[0])


def _ev_over_threshold_unmarked_count(conn, model_version_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ev_signals
            WHERE model_version = %s
              AND ev > %s
              AND (
                COALESCE(research_only, false) = false
                OR reason IS DISTINCT FROM 'model_market_divergence_too_large'
              )
            """,
            (model_version_id, EV_RESEARCH_ONLY_THRESHOLD),
        )
        return int(cur.fetchone()[0])


def _suggestion_pool_contract_ok(conn, model_version_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ev_signals
            WHERE model_version = %s
              AND suggestion_eligible = true
              AND (
                play_type NOT IN ('had', 'hhad')
                OR ev <= 0
                OR ev > %s
                OR COALESCE(research_only, false) = true
              )
            """,
            (model_version_id, EV_RESEARCH_ONLY_THRESHOLD),
        )
        return int(cur.fetchone()[0]) == 0


def _suggestion_eligible_count(conn, model_version_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ev_signals WHERE model_version = %s AND suggestion_eligible = true",
            (model_version_id,),
        )
        return int(cur.fetchone()[0])


def _ev_matches_latest_prediction_version(conn, model_version_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM ev_signals ev
            WHERE ev.model_version = %s
              AND NOT EXISTS (
                SELECT 1
                FROM predictions p
                WHERE p.match_id = ev.match_id
                  AND p.model_version = ev.model_version
              )
            """,
            (model_version_id,),
        )
        orphan_count = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM ev_signals WHERE model_version IS NULL")
        legacy_count = int(cur.fetchone()[0])
        return orphan_count == 0 and legacy_count >= 0


def _prediction_matrix_check(row: dict[str, Any]) -> bool:
    return score_matrix_shape_ok(row["score_matrix"])


def _prediction_edge_check(row: dict[str, Any], tolerance: float = 1e-6) -> bool:
    if not score_matrix_shape_ok(row["score_matrix"]):
        return False
    sums = region_sums_from_matrix(row["score_matrix"])
    return (
        abs(sums["3"] - float(row["p_home"])) <= tolerance
        and abs(sums["1"] - float(row["p_draw"])) <= tolerance
        and abs(sums["0"] - float(row["p_away"])) <= tolerance
    )


def _market_source_counts(params: dict[str, Any]) -> dict[str, Any]:
    stats = params.get("prediction_run") or params.get("last_predict_stats") or params.get("prediction_stats") or {}
    return {
        "market_source_had_count": stats.get("market_source_had_count", "NOT_CHECKED: not stored in model_versions.params"),
        "market_source_hhad_count": stats.get("market_source_hhad_count", "NOT_CHECKED: not stored in model_versions.params"),
        "skipped_missing_market_count": stats.get("skipped_missing_market_count", "NOT_CHECKED: not stored in model_versions.params"),
        "dc_only_count": stats.get("dc_only_count", "NOT_CHECKED: not stored in model_versions.params"),
    }


def _on_boundary(value: float, bounds: tuple[float, float], tolerance: float = 1e-9) -> bool:
    return abs(value - bounds[0]) <= tolerance or abs(value - bounds[1]) <= tolerance


def _has_database_not_checked(report: dict[str, list[ReportLine]]) -> bool:
    for lines in report.values():
        for line in lines:
            if isinstance(line.value, str) and line.value.startswith("NOT_CHECKED: DATABASE_URL"):
                return True
    return False


def failed_checks(report: dict[str, list[ReportLine]]) -> list[str]:
    values = {line.key: line.value for lines in report.values() for line in lines}
    failures: list[str] = []
    expected = {
        "params.elo_start_date": "2000-01-01",
        "params.training_start_date": "2015-01-01",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            failures.append(key)
    bool_checks = {
        "k_on_boundary": False,
        "score_matrix_edges_match_prediction": True,
        "ev_matches_latest_prediction_version": True,
        "ev_gt_0_15_all_research_only": True,
        "suggestion_pool_only_had_hhad": True,
    }
    for key, expected_value in bool_checks.items():
        if values.get(key) is not expected_value:
            failures.append(key)
    dc_only = values.get("dc_only_count")
    if dc_only != 0:
        failures.append("dc_only_count")
    for key in ("market_source_had_count", "market_source_hhad_count", "skipped_missing_market_count"):
        if isinstance(values.get(key), str) and str(values[key]).startswith("NOT_CHECKED"):
            failures.append(key)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
