from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from api.db import connect
from api.ops_log import record_ops_log, sanitize_error
from api.settlement_runner import run_settlement_job


CONFIRM_CODE = "RUN_SETTLEMENT_E2E_PROBE"
JOB_NAME = "settlement_e2e_probe"
PROBE_USERNAME = "__internal_settlement_probe__"
PROBE_LABEL = "__internal_settlement_probe_bet__"
DEFAULT_MATCH_ID = "500-1359172"
DEFAULT_STAKE = Decimal("1")


@dataclass(frozen=True)
class ProbePlan:
    match_id: str
    stake: Decimal
    target_match: dict[str, Any] | None
    latest_odds: Decimal | None
    selected_outcome: str
    expected_status: str | None
    expected_payout: Decimal | None
    blockers: list[str]


def dry_run(match_id: str = DEFAULT_MATCH_ID, stake: Decimal = DEFAULT_STAKE) -> dict[str, Any]:
    plan = build_plan(match_id, stake)
    return _dry_run_report(plan)


def confirm_probe(match_id: str = DEFAULT_MATCH_ID, stake: Decimal = DEFAULT_STAKE, confirm: str | None = None) -> dict[str, Any]:
    if confirm != CONFIRM_CODE:
        raise ValueError(f"confirm code required: {CONFIRM_CODE}")
    if _betting_enabled():
        raise ValueError("BETTING_ENABLED=true detected")

    plan = build_plan(match_id, stake)
    if plan.blockers:
        raise ValueError(f"preflight blockers: {', '.join(plan.blockers)}")
    if plan.latest_odds is None or plan.expected_payout is None or plan.expected_status is None:
        raise ValueError("probe plan is incomplete")

    started_at = datetime.now(timezone.utc)
    bet_id: int | None = None
    report: dict[str, Any] | None = None
    try:
        setup = _create_probe_bet(plan)
        bet_id = setup["bet_id"]
        first_stats = run_settlement_job(dry_run=False, record_log=True)
        first_bet = _probe_bet_snapshot(bet_id)
        balance_after_first = _probe_user_balance()
        second_stats = run_settlement_job(dry_run=False, record_log=True)
        second_bet = _probe_bet_snapshot(bet_id)
        balance_after_second = _probe_user_balance()
        cleanup = _cleanup_probe_data()
        leaderboard = _leaderboard_safety()

        balance_delta = balance_after_first - setup["balance_after_bet"]
        idempotency_pass = balance_after_second == balance_after_first and second_bet == first_bet
        balance_delta_correct = balance_delta == Decimal(str(first_bet.get("payout") or 0))
        settlement_status_ok = str(first_bet.get("status")) == plan.expected_status
        report = {
            "mode": "confirm",
            "ok": bool(
                settlement_status_ok
                and balance_delta_correct
                and idempotency_pass
                and cleanup["cleanup_success"]
                and leaderboard["leaderboard_no_internal_id"] is True
                and leaderboard["leaderboard_no_probe_user_pollution"]
            ),
            "probe_user": PROBE_USERNAME,
            "probe_bet_id": bet_id,
            "stake": str(plan.stake),
            "odds": str(plan.latest_odds),
            "expected_result": plan.expected_status,
            "expected_payout": str(plan.expected_payout),
            "before_balance": str(setup["balance_after_bet"]),
            "after_balance": str(balance_after_first),
            "bet_status_after_first_runner": first_bet.get("status"),
            "payout_after_first_runner": str(first_bet.get("payout")),
            "balance_delta": str(balance_delta),
            "balance_delta_correct": balance_delta_correct,
            "settlement_runner_first_run": _stats_dict(first_stats),
            "settlement_runner_second_run": _stats_dict(second_stats),
            "second_runner_executed": True,
            "idempotency_pass": idempotency_pass,
            "cleanup": cleanup,
            "cleanup_success": cleanup["cleanup_success"],
            "leaderboard": leaderboard,
            "ops_log_written": True,
            "recommend_open_betting": False,
        }
        record_ops_log(JOB_NAME, "ok" if report["ok"] else "error", started_at, summary=report, error=None if report["ok"] else "probe checks failed")
        return report
    except Exception as exc:
        cleanup = _cleanup_probe_data()
        error = sanitize_error(exc)
        summary = {"mode": "confirm", "ok": False, "probe_bet_id": bet_id, "cleanup": cleanup}
        try:
            record_ops_log(JOB_NAME, "error", started_at, summary=summary, error=error)
        except Exception:
            pass
        raise


def build_plan(match_id: str, stake: Decimal) -> ProbePlan:
    blockers: list[str] = []
    if _betting_enabled():
        blockers.append("betting_enabled_true")
    if not os.getenv("DATABASE_URL"):
        blockers.append("database_url_missing")
    if stake <= 0:
        blockers.append("invalid_stake")

    target_match = _target_match(match_id)
    if target_match is None:
        blockers.append("target_match_missing")
    else:
        if str(target_match["status"]) not in {"finished", "completed"}:
            blockers.append("target_match_not_finished")
        if target_match["result_home"] is None or target_match["result_away"] is None:
            blockers.append("target_match_result_missing")

    if _result_consistency_counts() != {"finished_null": 0, "non_finished_with_result": 0}:
        blockers.append("result_consistency_not_pass")
    if _non_probe_open_pending_count() > 0:
        blockers.append("existing_open_pending_bets")
    if _probe_artifact_count() > 0:
        blockers.append("existing_probe_artifacts")

    latest_odds = _latest_had_home_odds(match_id)
    if latest_odds is None:
        blockers.append("missing_latest_had_home_odds")

    expected_status = None
    expected_payout = None
    if (
        target_match is not None
        and latest_odds is not None
        and target_match.get("result_home") is not None
        and target_match.get("result_away") is not None
    ):
        expected_status = "won" if int(target_match["result_home"]) > int(target_match["result_away"]) else "lost"
        expected_payout = stake * latest_odds if expected_status == "won" else Decimal("0")

    return ProbePlan(
        match_id=match_id,
        stake=stake,
        target_match=target_match,
        latest_odds=latest_odds,
        selected_outcome="had:3",
        expected_status=expected_status,
        expected_payout=expected_payout,
        blockers=blockers,
    )


def print_report(report: dict[str, Any]) -> None:
    print("Settlement E2E Probe Report")
    for key, value in report.items():
        if isinstance(value, (dict, list)):
            print(f"- {key}: {json.dumps(value, ensure_ascii=False, default=str)}")
        else:
            print(f"- {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="production internal settlement E2E probe")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--confirm")
    parser.add_argument("--match-id", default=DEFAULT_MATCH_ID)
    parser.add_argument("--stake", default=str(DEFAULT_STAKE))
    args = parser.parse_args(argv)

    try:
        stake = Decimal(str(args.stake))
        report = dry_run(args.match_id, stake) if args.dry_run else confirm_probe(args.match_id, stake, args.confirm)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    return 0 if report.get("ok") or args.dry_run else 1


def _dry_run_report(plan: ProbePlan) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "ok": not plan.blockers,
        "target_match": _safe_match(plan.target_match),
        "target_result": _target_result(plan.target_match),
        "latest_odds": str(plan.latest_odds) if plan.latest_odds is not None else None,
        "selected_outcome": plan.selected_outcome,
        "expected_settlement_result": plan.expected_status,
        "expected_payout": str(plan.expected_payout) if plan.expected_payout is not None else None,
        "probe_user_would_create": PROBE_USERNAME,
        "probe_bet_would_create": True,
        "would_run_settlement_runner": True,
        "would_verify_idempotency": True,
        "would_cleanup": True,
        "would_write_db": False,
        "blockers": plan.blockers,
        "recommend_open_betting": False,
    }


def _create_probe_bet(plan: ProbePlan) -> dict[str, Any]:
    assert plan.latest_odds is not None
    potential_payout = plan.stake * plan.latest_odds
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, balance)
            VALUES (%s, 'settlement-e2e-probe-only', 10000)
            RETURNING id, balance
            """,
            (PROBE_USERNAME,),
        )
        user = cur.fetchone()
        user_id = int(user["id"])
        cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (plan.stake, user_id))
        legs = [
            {
                "label": PROBE_LABEL,
                "match_id": plan.match_id,
                "play_type": "had",
                "selection": "3",
                "odds": str(plan.latest_odds),
            }
        ]
        cur.execute(
            """
            INSERT INTO bets (user_id, legs, parlay, stake, potential_payout, status)
            VALUES (%s, %s, 'single', %s, %s, 'open')
            RETURNING id
            """,
            (user_id, Jsonb(legs), plan.stake, potential_payout),
        )
        bet_id = int(cur.fetchone()["id"])
        cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        balance_after_bet = Decimal(str(cur.fetchone()["balance"]))
    return {"user_id": user_id, "bet_id": bet_id, "balance_after_bet": balance_after_bet}


def _cleanup_probe_data() -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bets
            WHERE user_id IN (SELECT id FROM users WHERE username = %s)
               OR legs::text LIKE %s
            """,
            (PROBE_USERNAME, f"%{PROBE_LABEL}%"),
        )
        deleted_bets = cur.rowcount
        cur.execute("DELETE FROM users WHERE username = %s", (PROBE_USERNAME,))
        deleted_users = cur.rowcount
    return {
        "deleted_bets": deleted_bets,
        "deleted_users": deleted_users,
        "cleanup_success": _probe_artifact_count() == 0,
    }


def _target_match(match_id: str) -> dict[str, Any] | None:
    if not os.getenv("DATABASE_URL"):
        return None
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT match_id, match_num, home_team, away_team, status, result_home, result_away, ht_home, ht_away
            FROM matches
            WHERE match_id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _latest_had_home_odds(match_id: str) -> Decimal | None:
    if not os.getenv("DATABASE_URL"):
        return None
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT odds
            FROM odds_snapshots
            WHERE match_id = %s AND play_type = 'had'
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (match_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    odds = row["odds"]
    if isinstance(odds, str):
        odds = json.loads(odds)
    value = odds.get("3") if isinstance(odds, dict) else None
    return Decimal(str(value)) if value is not None else None


def _result_consistency_counts() -> dict[str, int]:
    if not os.getenv("DATABASE_URL"):
        return {"finished_null": 1, "non_finished_with_result": 1}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM matches
            WHERE status IN ('finished','completed')
              AND (result_home IS NULL OR result_away IS NULL)
            """
        )
        finished_null = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*)
            FROM matches
            WHERE status NOT IN ('finished','completed')
              AND (result_home IS NOT NULL OR result_away IS NOT NULL)
            """
        )
        non_finished = int(cur.fetchone()[0])
    return {"finished_null": finished_null, "non_finished_with_result": non_finished}


def _non_probe_open_pending_count() -> int:
    if not os.getenv("DATABASE_URL"):
        return 1
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM bets b
            JOIN users u ON u.id = b.user_id
            WHERE b.status IN ('open','pending')
              AND u.username <> %s
            """,
            (PROBE_USERNAME,),
        )
        return int(cur.fetchone()[0])


def _probe_artifact_count() -> int:
    if not os.getenv("DATABASE_URL"):
        return 0
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM users WHERE username = %s", (PROBE_USERNAME,))
        users = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM bets WHERE legs::text LIKE %s", (f"%{PROBE_LABEL}%",))
        bets = int(cur.fetchone()[0])
    return users + bets


def _probe_bet_snapshot(bet_id: int) -> dict[str, Any]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, status, payout, settled_at FROM bets WHERE id = %s", (bet_id,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"probe bet missing: {bet_id}")
        return dict(row)


def _probe_user_balance() -> Decimal:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT balance FROM users WHERE username = %s", (PROBE_USERNAME,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("probe user missing")
        return Decimal(str(row[0]))


def _leaderboard_safety() -> dict[str, Any]:
    probe_count = _probe_artifact_count()
    api_result = _public_leaderboard_safety()
    return {
        "leaderboard_no_probe_user_pollution": probe_count == 0 and api_result.get("test_user_count", 0) == 0,
        "leaderboard_no_internal_id": api_result.get("leaderboard_no_internal_id"),
        "public_leaderboard_checked": api_result.get("checked"),
        "public_leaderboard_error": api_result.get("error"),
        "probe_artifact_count": probe_count,
    }


def _public_leaderboard_safety() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("https://fifa2026.zeabur.app/api/leaderboard", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"checked": False, "leaderboard_no_internal_id": None, "test_user_count": 0, "error": repr(exc)}
    rows = payload if isinstance(payload, list) else payload.get("items", [])
    keys = set().union(*(row.keys() for row in rows)) if rows else set()
    return {
        "checked": True,
        "leaderboard_no_internal_id": not bool({"id", "user_id", "password_hash"} & keys),
        "test_user_count": sum(1 for row in rows if str(row.get("username", "")).startswith("__internal_")),
        "error": None,
    }


def _safe_match(match: dict[str, Any] | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {key: match.get(key) for key in ("match_id", "match_num", "home_team", "away_team", "status", "result_home", "result_away", "ht_home", "ht_away")}


def _target_result(match: dict[str, Any] | None) -> str | None:
    if match is None or match.get("result_home") is None or match.get("result_away") is None:
        return None
    return f"{match['result_home']}-{match['result_away']}"


def _stats_dict(stats: Any) -> dict[str, int]:
    return {
        "open_bets_seen": int(stats.open_bets_seen),
        "settled_won": int(stats.settled_won),
        "settled_lost": int(stats.settled_lost),
        "settled_void": int(stats.settled_void),
        "skipped_not_ready": int(stats.skipped_not_ready),
        "errors": int(stats.errors),
    }


def _betting_enabled() -> bool:
    return str(os.getenv("BETTING_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
