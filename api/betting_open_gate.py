from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.scheduler_health import scheduler_freshness


DEFAULT_ODDS_STALE_THRESHOLD_MINUTES = 30


def generate_report() -> dict[str, Any]:
    try:
        with connect() as conn:
            evidence = collect_evidence(conn)
    except Exception as exc:
        evidence = _unknown_evidence()
        evidence["collection_error"] = type(exc).__name__
        return {
            "status": "WAIT",
            "betting_open_gate_status": "WAIT",
            "recommend_open_betting": False,
            "blockers": ["betting_open_gate_unavailable"],
            "warnings": [],
            "betting_open_blockers": ["betting_open_gate_unavailable"],
            "betting_open_warnings": [],
            **evidence,
        }
    result = evaluate_gate(**evidence)
    return {**result, **evidence}


def health_summary() -> dict[str, Any]:
    try:
        report = generate_report()
    except Exception:
        return {
            "betting_open_gate_status": "WAIT",
            "recommend_open_betting": False,
            "betting_open_blockers": ["betting_open_gate_unavailable"],
            "betting_open_warnings": [],
        }
    return {
        "betting_open_gate_status": report["status"],
        "recommend_open_betting": report["recommend_open_betting"],
        "betting_open_blockers": report["blockers"],
        "betting_open_warnings": report["warnings"],
    }


def collect_evidence(conn) -> dict[str, Any]:
    scheduler = scheduler_freshness()
    latest_odds = _scalar(conn, "SELECT max(fetched_at) FROM odds_snapshots")
    latest_odds_age = _age_minutes(latest_odds)
    latest_settlement = _latest_ops_log(conn, "settlement_runner")
    latest_probe = _latest_ops_log(conn, "settlement_e2e_probe")
    probe = _settlement_probe_evidence(latest_probe)
    leaderboard = _leaderboard_safety(conn)
    p3_status = _safe_p3_status()
    evaluable_finished_matches = int(
        _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
            """,
        )
        or 0
    )
    finished_null_count = int(
        _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND (result_home IS NULL OR result_away IS NULL)
            """,
        )
        or 0
    )
    non_finished_with_result_count = int(
        _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status NOT IN ('finished', 'completed')
              AND (result_home IS NOT NULL OR result_away IS NOT NULL)
            """,
        )
        or 0
    )
    return {
        "scheduler_stale": bool(scheduler.get("scheduler_stale")),
        "odds_stale": latest_odds_age is None or latest_odds_age > _env_int("ODDS_STALE_THRESHOLD_MINUTES", DEFAULT_ODDS_STALE_THRESHOLD_MINUTES),
        "finished_null_count": finished_null_count,
        "non_finished_with_result_count": non_finished_with_result_count,
        "settlement_runner_error": bool((latest_settlement or {}).get("error")) or str((latest_settlement or {}).get("status") or "").lower() == "error",
        "settlement_probe_pass": probe["settlement_probe_pass"],
        "settlement_idempotency_pass": probe["settlement_idempotency_pass"],
        "leaderboard_safe": leaderboard["leaderboard_safe"] and probe["leaderboard_safety"],
        "leaderboard_exposes_internal_id": leaderboard["leaderboard_exposes_internal_id"],
        "leaderboard_test_user_count": leaderboard["leaderboard_test_user_count"],
        "two_matchdays_auto_result_sync": _two_matchdays_auto_result_sync(conn),
        "betting_enabled": _enabled(os.getenv("BETTING_ENABLED", "false")),
        "p1c_prime_ready": evaluable_finished_matches >= 30,
        "p3_status": p3_status,
        "latest_odds_snapshot_age_minutes": latest_odds_age,
        "latest_settlement_probe_at": _iso((latest_probe or {}).get("started_at")),
    }


def evaluate_gate(
    *,
    scheduler_stale: bool | None,
    odds_stale: bool | None,
    finished_null_count: int | None,
    non_finished_with_result_count: int | None,
    settlement_runner_error: bool | None,
    settlement_probe_pass: bool | None,
    settlement_idempotency_pass: bool | None,
    leaderboard_safe: bool | None,
    leaderboard_exposes_internal_id: bool | None = None,
    leaderboard_test_user_count: int | None = 0,
    two_matchdays_auto_result_sync: bool | None,
    betting_enabled: bool,
    p1c_prime_ready: bool | None = None,
    p3_status: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    if scheduler_stale is True or scheduler_stale is None:
        blockers.append("scheduler_stale")
    if odds_stale is True or odds_stale is None:
        blockers.append("odds_stale")
    if int(finished_null_count or 0) > 0:
        blockers.append("finished_null_count")
    if int(non_finished_with_result_count or 0) > 0:
        blockers.append("non_finished_with_result_count")
    if settlement_runner_error is True or settlement_runner_error is None:
        blockers.append("settlement_runner_error")
    if leaderboard_safe is False or leaderboard_safe is None:
        blockers.append("leaderboard_unsafe")
    if leaderboard_exposes_internal_id:
        blockers.append("leaderboard_exposes_internal_id")
    if int(leaderboard_test_user_count or 0) > 0:
        blockers.append("leaderboard_test_user_pollution")

    wait_blockers: list[str] = []
    if not settlement_probe_pass:
        wait_blockers.append("settlement_e2e_probe_not_passed")
    if not settlement_idempotency_pass:
        wait_blockers.append("settlement_idempotency_not_passed")
    if not two_matchdays_auto_result_sync:
        wait_blockers.append("need_two_matchdays_auto_result_sync")
    if p1c_prime_ready is False:
        warnings.append("p1c_prime_insufficient_samples")
    if str(p3_status or "").upper() in {"WAIT", ""}:
        warnings.append("p3_wait")

    if betting_enabled and (blockers or wait_blockers):
        blockers.append("betting_enabled_true_before_gate_ready")
    elif betting_enabled:
        blockers.append("betting_enabled_already_true")

    if blockers:
        status = "BLOCKED"
        recommend = False
        final_blockers = _dedupe(blockers + wait_blockers)
    elif wait_blockers:
        status = "WAIT"
        recommend = False
        final_blockers = _dedupe(wait_blockers)
    else:
        status = "READY"
        recommend = True
        final_blockers = []

    return {
        "status": status,
        "betting_open_gate_status": status,
        "recommend_open_betting": recommend,
        "blockers": final_blockers,
        "warnings": _dedupe(warnings),
        "betting_open_blockers": final_blockers,
        "betting_open_warnings": _dedupe(warnings),
    }


def print_report(report: dict[str, Any]) -> None:
    print("Betting Open Gate Report")
    print("")
    for key in (
        "status",
        "recommend_open_betting",
        "blockers",
        "warnings",
        "scheduler_stale",
        "odds_stale",
        "finished_null_count",
        "non_finished_with_result_count",
        "settlement_probe_pass",
        "settlement_idempotency_pass",
        "leaderboard_safe",
        "two_matchdays_auto_result_sync",
        "betting_enabled",
    ):
        print(f"- {key}: {report.get(key)}")


def _settlement_probe_evidence(row: dict[str, Any] | None) -> dict[str, bool]:
    summary = row.get("summary") if row else {}
    if not isinstance(summary, dict):
        summary = {}
    leaderboard = summary.get("leaderboard") if isinstance(summary.get("leaderboard"), dict) else {}
    return {
        "settlement_probe_pass": str((row or {}).get("status") or "").lower() == "ok" and bool(summary.get("ok")),
        "settlement_idempotency_pass": bool(summary.get("idempotency_pass")),
        "leaderboard_safety": bool(leaderboard.get("leaderboard_no_internal_id")) and bool(leaderboard.get("leaderboard_no_probe_user_pollution")),
    }


def _leaderboard_safety(conn) -> dict[str, Any]:
    rows = _rows(
        conn,
        """
        SELECT username
        FROM users
        WHERE username LIKE 'test_user_%'
           OR username LIKE 'codex_blocker_%'
           OR username = '__internal_settlement_probe__'
        LIMIT 50
        """,
    )
    exposed_keys = {"id", "user_id", "internal_id", "password_hash"}
    public_row_keys = {"username", "balance", "roi", "settled_bets"}
    exposes_internal_id = bool(exposed_keys & public_row_keys)
    test_count = len(rows)
    return {
        "leaderboard_safe": not exposes_internal_id and test_count == 0,
        "leaderboard_exposes_internal_id": exposes_internal_id,
        "leaderboard_test_user_count": test_count,
    }


def _two_matchdays_auto_result_sync(conn) -> bool:
    matchday_rows = _rows(
        conn,
        """
        SELECT kickoff_at::date AS matchday, count(*) AS finished_count
        FROM matches
        WHERE status IN ('finished', 'completed')
          AND result_home IS NOT NULL
          AND result_away IS NOT NULL
        GROUP BY kickoff_at::date
        ORDER BY kickoff_at::date DESC
        LIMIT 2
        """,
    )
    if len(matchday_rows) < 2:
        return False
    results_ok_count = int(
        _scalar(
            conn,
            """
            SELECT count(*)
            FROM ops_log
            WHERE job_name = 'results_sync'
              AND status = 'ok'
            """,
        )
        or 0
    )
    fallback_ok_count = int(
        _scalar(
            conn,
            """
            SELECT count(*)
            FROM ops_log
            WHERE job_name = 'official_result_fallback'
              AND status = 'ok'
            """,
        )
        or 0
    )
    return results_ok_count >= 2 and fallback_ok_count == 0


def _latest_ops_log(conn, job_name: str) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT job_name, status, started_at, finished_at, summary, error
            FROM ops_log
            WHERE job_name = %s
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (job_name,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _safe_p3_status() -> str:
    try:
        from model.p3_fifa_readiness import health_summary

        return str(health_summary().get("p3_status") or "WAIT")
    except Exception:
        return "WAIT"


def _unknown_evidence() -> dict[str, Any]:
    return {
        "scheduler_stale": None,
        "odds_stale": None,
        "finished_null_count": 0,
        "non_finished_with_result_count": 0,
        "settlement_runner_error": None,
        "settlement_probe_pass": False,
        "settlement_idempotency_pass": False,
        "leaderboard_safe": None,
        "leaderboard_exposes_internal_id": None,
        "leaderboard_test_user_count": 0,
        "two_matchdays_auto_result_sync": False,
        "betting_enabled": _enabled(os.getenv("BETTING_ENABLED", "false")),
        "p1c_prime_ready": False,
        "p3_status": "WAIT",
    }


def _scalar(conn, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    return row[0] if row else None


def _rows(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def _age_minutes(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() // 60)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="betting open gate")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0 if report["status"] in {"READY", "WAIT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
