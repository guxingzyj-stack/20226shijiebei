from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib import request

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import record_ops_log, sanitize_error
from api.scheduler_health import scheduler_freshness


DEFAULT_OPS_STALE_THRESHOLD_MINUTES = 90
DEFAULT_ODDS_STALE_THRESHOLD_MINUTES = 30


def run_ops_health_check(record_log: bool = True) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    try:
        report = generate_report()
        if record_log:
            status = str(report["overall"]["status"]).lower()
            record_ops_log("ops_health_check", status, started_at, summary=report["summary"], error=None)
        _maybe_send_alert(report)
        return report
    except Exception as exc:
        error = sanitize_error(exc)
        report = _error_report(error)
        if record_log:
            try:
                record_ops_log("ops_health_check", "fail", started_at, summary=report["summary"], error=error)
            except Exception:
                pass
        return report


def generate_report(
    ops_stale_threshold_minutes: int | None = None,
    odds_stale_threshold_minutes: int | None = None,
) -> dict[str, Any]:
    ops_threshold = ops_stale_threshold_minutes or _env_int(
        "OPS_HEALTH_STALE_THRESHOLD_MINUTES", DEFAULT_OPS_STALE_THRESHOLD_MINUTES
    )
    odds_threshold = odds_stale_threshold_minutes or _env_int(
        "ODDS_STALE_THRESHOLD_MINUTES", DEFAULT_ODDS_STALE_THRESHOLD_MINUTES
    )
    scheduler = scheduler_freshness(threshold_minutes=ops_threshold)
    with connect() as conn:
        latest_results = _latest_ops_log(conn, "results_sync")
        latest_settlement = _latest_ops_log(conn, "settlement_runner")
        latest_odds = _scalar(conn, "SELECT max(fetched_at) FROM odds_snapshots")
        finished_null_count = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND (result_home IS NULL OR result_away IS NULL)
            """,
        )
        non_finished_with_result_count = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status NOT IN ('finished', 'completed')
              AND (result_home IS NOT NULL OR result_away IS NOT NULL)
            """,
        )
        open_pending_bets = _scalar(conn, "SELECT count(*) FROM bets WHERE status IN ('open', 'pending')")
        evaluable_finished_matches = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished', 'completed')
              AND result_home IS NOT NULL
              AND result_away IS NOT NULL
            """,
        )
        closed_pending_count = _scalar(
            conn,
            """
            SELECT count(*)
            FROM matches m
            WHERE m.status = 'closed'
              AND m.result_home IS NULL
              AND m.result_away IS NULL
            """,
        )
        overdue_closed_rows = _rows(
            conn,
            """
            SELECT match_id
            FROM matches
            WHERE status IN ('closed', 'scheduled')
              AND kickoff_at <= now() - interval '3 hours'
              AND result_home IS NULL
              AND result_away IS NULL
            ORDER BY kickoff_at
            LIMIT 20
            """,
        )

    latest_results_age = _age_minutes(latest_results.get("started_at") if latest_results else None)
    latest_settlement_age = _age_minutes(latest_settlement.get("started_at") if latest_settlement else None)
    latest_odds_age = _age_minutes(latest_odds)
    result_overdue_match_ids = [str(row["match_id"]) for row in overdue_closed_rows]
    status, blockers = evaluate_status(
        scheduler_stale=scheduler.get("scheduler_stale"),
        latest_results_sync_age_minutes=latest_results_age,
        latest_settlement_runner_age_minutes=latest_settlement_age,
        latest_odds_snapshot_age_minutes=latest_odds_age,
        finished_null_count=finished_null_count,
        non_finished_with_result_count=non_finished_with_result_count,
        latest_settlement_runner_status=latest_settlement.get("status") if latest_settlement else None,
        latest_settlement_runner_error=latest_settlement.get("error") if latest_settlement else None,
        open_pending_bets=open_pending_bets,
        evaluable_finished_matches=evaluable_finished_matches,
        closed_prediction_pending_count=closed_pending_count,
        result_overdue_closed_count=len(result_overdue_match_ids),
        stale_threshold_minutes=ops_threshold,
        odds_stale_threshold_minutes=odds_threshold,
    )
    summary = {
        "scheduler_stale": scheduler.get("scheduler_stale"),
        "latest_results_sync_age_minutes": latest_results_age,
        "latest_settlement_runner_age_minutes": latest_settlement_age,
        "latest_odds_snapshot_age_minutes": latest_odds_age,
        "finished_null_count": finished_null_count,
        "non_finished_with_result_count": non_finished_with_result_count,
        "open_pending_bets": open_pending_bets,
        "evaluable_finished_matches": evaluable_finished_matches,
        "result_overdue_closed_matches": result_overdue_match_ids,
        "overall_status": status,
        "blockers": blockers,
    }
    return {
        "scheduler": {
            "scheduler_stale": scheduler.get("scheduler_stale"),
            "scheduler_last_seen": scheduler.get("scheduler_last_seen"),
            "scheduler_last_seen_age_minutes": scheduler.get("scheduler_last_seen_age_minutes"),
            "latest_results_sync_at": _iso(latest_results.get("started_at") if latest_results else None),
            "latest_settlement_runner_at": _iso(latest_settlement.get("started_at") if latest_settlement else None),
        },
        "odds": {
            "latest_odds_snapshot": _iso(latest_odds),
            "odds_stale": latest_odds_age is None or latest_odds_age > odds_threshold,
            "threshold_minutes": odds_threshold,
            "latest_odds_snapshot_age_minutes": latest_odds_age,
        },
        "result_consistency": {
            "finished_null_count": finished_null_count,
            "non_finished_with_result_count": non_finished_with_result_count,
            "result_consistency_pass": finished_null_count == 0 and non_finished_with_result_count == 0,
        },
        "settlement": {
            "open_pending_bets": open_pending_bets,
            "latest_settlement_runner_status": latest_settlement.get("status") if latest_settlement else None,
            "latest_settlement_runner_error": latest_settlement.get("error") if latest_settlement else None,
        },
        "p1c_prime": {
            "evaluable_finished_matches": evaluable_finished_matches,
            "p1c_ready": evaluable_finished_matches >= 30,
        },
        "closed_matches": {
            "closed_prediction_pending_count": closed_pending_count,
            "result_overdue_closed_matches": result_overdue_match_ids,
            "result_overdue_closed_count": len(result_overdue_match_ids),
        },
        "overall": {
            "status": status,
            "blockers": blockers,
        },
        "summary": summary,
    }


def evaluate_status(
    *,
    scheduler_stale: Any,
    latest_results_sync_age_minutes: int | None,
    latest_settlement_runner_age_minutes: int | None,
    latest_odds_snapshot_age_minutes: int | None,
    finished_null_count: int,
    non_finished_with_result_count: int,
    latest_settlement_runner_status: str | None,
    latest_settlement_runner_error: str | None,
    open_pending_bets: int,
    evaluable_finished_matches: int,
    closed_prediction_pending_count: int = 0,
    result_overdue_closed_count: int = 0,
    stale_threshold_minutes: int = DEFAULT_OPS_STALE_THRESHOLD_MINUTES,
    odds_stale_threshold_minutes: int = DEFAULT_ODDS_STALE_THRESHOLD_MINUTES,
) -> tuple[str, list[str]]:
    fail: list[str] = []
    warn: list[str] = []
    if scheduler_stale is True or scheduler_stale is None:
        fail.append("scheduler_stale")
    if latest_results_sync_age_minutes is None or latest_results_sync_age_minutes > stale_threshold_minutes:
        fail.append("results_sync_stale")
    if latest_settlement_runner_age_minutes is None or latest_settlement_runner_age_minutes > stale_threshold_minutes:
        fail.append("settlement_runner_stale")
    if latest_odds_snapshot_age_minutes is None or latest_odds_snapshot_age_minutes > odds_stale_threshold_minutes:
        fail.append("odds_snapshot_stale")
    if finished_null_count > 0:
        fail.append("finished_null_recurred")
    if non_finished_with_result_count > 0:
        fail.append("non_finished_with_result")
    if latest_settlement_runner_status == "error" or latest_settlement_runner_error:
        fail.append("settlement_runner_error")
    if open_pending_bets == 0:
        warn.append("no_open_bets_to_settle")
    if evaluable_finished_matches < 30:
        warn.append("insufficient_finished_matches")
    if closed_prediction_pending_count > 0:
        warn.append("closed_prediction_pending")
    if result_overdue_closed_count > 0:
        warn.append("result_overdue_closed_matches")
    if fail:
        return "FAIL", fail + warn
    if warn:
        return "WARN", warn
    return "OK", []


def print_report(report: dict[str, Any]) -> None:
    print("Ops Health Check Report")
    print("")
    print("1. Scheduler")
    for key in ("scheduler_stale", "scheduler_last_seen", "latest_results_sync_at", "latest_settlement_runner_at"):
        print(f"- {key}: {report['scheduler'].get(key)}")
    print("")
    print("2. Odds freshness")
    for key in ("latest_odds_snapshot", "odds_stale", "threshold_minutes"):
        print(f"- {key}: {report['odds'].get(key)}")
    print("")
    print("3. Result consistency")
    for key in ("finished_null_count", "non_finished_with_result_count", "result_consistency_pass"):
        print(f"- {key}: {report['result_consistency'].get(key)}")
    print("")
    print("4. Settlement")
    for key in ("open_pending_bets", "latest_settlement_runner_status", "latest_settlement_runner_error"):
        print(f"- {key}: {report['settlement'].get(key)}")
    print("")
    print("5. P1-C Prime")
    for key in ("evaluable_finished_matches", "p1c_ready"):
        print(f"- {key}: {report['p1c_prime'].get(key)}")
    print("")
    print("6. Closed / scheduled result overdue")
    for key in ("result_overdue_closed_count", "result_overdue_closed_matches"):
        print(f"- {key}: {report['closed_matches'].get(key)}")
    print("")
    print("7. Overall")
    print(f"- status: {report['overall'].get('status')}")
    print(f"- blockers: {report['overall'].get('blockers')}")


def latest_ops_health_status() -> dict[str, Any]:
    try:
        with connect() as conn:
            row = _latest_ops_log(conn, "ops_health_check")
    except Exception:
        return {
            "latest_ops_health_check_at": None,
            "ops_health_status": None,
            "ops_health_blockers": [],
        }
    summary = row.get("summary") if row else None
    if not isinstance(summary, dict):
        summary = {}
    return {
        "latest_ops_health_check_at": _iso(row.get("started_at") if row else None),
        "ops_health_status": summary.get("overall_status") or (str(row.get("status")).upper() if row else None),
        "ops_health_blockers": summary.get("blockers") or [],
    }


def _maybe_send_alert(report: dict[str, Any]) -> None:
    if str(os.getenv("OPS_ALERT_ENABLED", "false")).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    webhook = os.getenv("OPS_ALERT_WEBHOOK_URL", "").strip()
    if not webhook or report["overall"]["status"] != "FAIL":
        return
    body = json.dumps(
        {
            "text": "WorldCup Ops Health FAIL",
            "scheduler_stale": report["scheduler"].get("scheduler_stale"),
            "odds_stale": report["odds"].get("odds_stale"),
            "result_consistency": report["result_consistency"].get("result_consistency_pass"),
            "latest_results_sync": report["scheduler"].get("latest_results_sync_at"),
            "latest_settlement_runner": report["scheduler"].get("latest_settlement_runner_at"),
            "blockers": report["overall"].get("blockers"),
        }
    ).encode("utf-8")
    req = request.Request(webhook, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        request.urlopen(req, timeout=5).close()
    except Exception:
        pass


def _error_report(error: str) -> dict[str, Any]:
    return {
        "scheduler": {"scheduler_stale": None, "scheduler_last_seen": None, "latest_results_sync_at": None, "latest_settlement_runner_at": None},
        "odds": {"latest_odds_snapshot": None, "odds_stale": None, "threshold_minutes": _env_int("ODDS_STALE_THRESHOLD_MINUTES", DEFAULT_ODDS_STALE_THRESHOLD_MINUTES)},
        "result_consistency": {"finished_null_count": None, "non_finished_with_result_count": None, "result_consistency_pass": False},
        "settlement": {"open_pending_bets": None, "latest_settlement_runner_status": None, "latest_settlement_runner_error": error},
        "p1c_prime": {"evaluable_finished_matches": None, "p1c_ready": False},
        "closed_matches": {
            "closed_prediction_pending_count": None,
            "result_overdue_closed_count": None,
            "result_overdue_closed_matches": [],
        },
        "overall": {"status": "FAIL", "blockers": ["ops_health_check_error"]},
        "summary": {"overall_status": "FAIL", "blockers": ["ops_health_check_error"]},
    }


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="production ops health check")
    parser.add_argument("--no-record-log", action="store_true")
    args = parser.parse_args(argv)
    report = run_ops_health_check(record_log=not args.no_record_log)
    print_report(report)
    return 0 if report["overall"]["status"] in {"OK", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
