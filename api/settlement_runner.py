from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import sys
from typing import Any

from psycopg.rows import dict_row

from api.db import connect
from api.ops_log import record_ops_log, sanitize_error
from api.settlement import MatchResult, settle_parlay


@dataclass
class SettlementStats:
    open_bets_seen: int = 0
    settled_won: int = 0
    settled_lost: int = 0
    settled_void: int = 0
    skipped_not_ready: int = 0
    errors: int = 0


def run_settlement(repository: Any, dry_run: bool = False) -> SettlementStats:
    stats = SettlementStats()
    for bet in repository.open_bets():
        stats.open_bets_seen += 1
        try:
            outcome = settle_bet_if_ready(bet, repository.match_rows(_match_ids(bet)))
            if outcome is None:
                stats.skipped_not_ready += 1
                continue
            if not dry_run:
                applied = repository.apply_settlement(
                    int(bet["id"]),
                    str(outcome["status"]),
                    Decimal(str(outcome["payout"])),
                )
                if not applied:
                    continue
            status = str(outcome["status"])
            if status == "won":
                stats.settled_won += 1
            elif status == "lost":
                stats.settled_lost += 1
            elif status == "void":
                stats.settled_void += 1
        except Exception:
            stats.errors += 1
    return stats


def settle_bet_if_ready(bet: dict[str, Any], match_rows: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    legs = list(bet["legs"])
    results: dict[str, MatchResult] = {}
    for match_id in _match_ids(bet):
        row = match_rows.get(match_id)
        if row is None:
            return None
        status = str(row.get("status") or "")
        if status == "postponed":
            continue
        if status != "finished":
            return None
        if row.get("result_home") is None or row.get("result_away") is None:
            return None
        results[match_id] = MatchResult(
            int(row["result_home"]),
            int(row["result_away"]),
            ht_home=_optional_int(row.get("ht_home")),
            ht_away=_optional_int(row.get("ht_away")),
        )

    settled = settle_parlay(legs, results, Decimal(str(bet["stake"])))
    leg_statuses = list(settled.get("leg_statuses") or [])
    status = "void" if leg_statuses and all(item == "void" for item in leg_statuses) else str(settled["status"])
    return {"status": status, "payout": Decimal(str(settled["payout"])), "leg_statuses": leg_statuses}


class PostgresSettlementRepository:
    def open_bets(self) -> list[dict[str, Any]]:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, legs, parlay, stake
                FROM bets
                WHERE status = 'open'
                ORDER BY id
                """
            )
            return [dict(row) for row in cur.fetchall()]

    def match_rows(self, match_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not match_ids:
            return {}
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT match_id, status, result_home, result_away, ht_home, ht_away
                FROM matches
                WHERE match_id = ANY(%s)
                """,
                (match_ids,),
            )
            return {str(row["match_id"]): dict(row) for row in cur.fetchall()}

    def apply_settlement(self, bet_id: int, status: str, payout: Decimal) -> bool:
        with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE bets
                SET status = %s,
                    payout = %s,
                    settled_at = now()
                WHERE id = %s AND status = 'open'
                RETURNING user_id
                """,
                (status, payout, bet_id),
            )
            row = cur.fetchone()
            if not row:
                return False
            if payout > 0:
                cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (payout, row["user_id"]))
            return True


def print_stats(stats: SettlementStats) -> None:
    print("settlement_runner:")
    print(f"- open_bets_seen: {stats.open_bets_seen}")
    print(f"- settled_won: {stats.settled_won}")
    print(f"- settled_lost: {stats.settled_lost}")
    print(f"- settled_void: {stats.settled_void}")
    print(f"- skipped_not_ready: {stats.skipped_not_ready}")
    print(f"- errors: {stats.errors}")


def run_settlement_job(dry_run: bool = False, record_log: bool = False) -> SettlementStats:
    started_at = datetime.now(timezone.utc)
    try:
        stats = run_settlement(PostgresSettlementRepository(), dry_run=dry_run)
        if record_log:
            record_ops_log("settlement_runner", "ok" if stats.errors == 0 else "error", started_at, _stats_summary(stats), None if stats.errors == 0 else "settlement_runner row errors")
        return stats
    except Exception as exc:
        if record_log:
            record_ops_log("settlement_runner", "error", started_at, {}, sanitize_error(exc))
        raise


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "once"
    if command not in {"once", "dry-run"}:
        print("usage: python -m api.settlement_runner [once|dry-run]", file=sys.stderr)
        return 2
    try:
        stats = run_settlement_job(dry_run=command == "dry-run", record_log=False)
    except Exception:
        stats = SettlementStats(errors=1)
    print_stats(stats)
    return 0 if stats.errors == 0 else 1


def _stats_summary(stats: SettlementStats) -> dict[str, int]:
    return {
        "open_bets_seen": stats.open_bets_seen,
        "settled_won": stats.settled_won,
        "settled_lost": stats.settled_lost,
        "settled_void": stats.settled_void,
        "skipped_not_ready": stats.skipped_not_ready,
        "errors": stats.errors,
    }


def _match_ids(bet: dict[str, Any]) -> list[str]:
    return sorted({str(leg["match_id"]) for leg in bet["legs"]})


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


if __name__ == "__main__":
    raise SystemExit(main())
