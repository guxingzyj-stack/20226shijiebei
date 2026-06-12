from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.ops_health_check import run_ops_health_check


DEFAULT_HEALTH_URL = "https://fifa2026.zeabur.app/api/health"


def fetch_api_health(url: str = DEFAULT_HEALTH_URL, timeout_seconds: int = 20) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def run_daily_check(health_url: str = DEFAULT_HEALTH_URL) -> dict[str, Any]:
    if _enabled(os.getenv("BETTING_ENABLED", "false")):
        return {
            "status": "FAIL",
            "blockers": ["betting_enabled_true"],
            "health": {},
            "ops_health": {},
            "exit_code": 2,
        }
    health = _safe_fetch_health(health_url)
    ops_report = run_ops_health_check(record_log=True)
    overall = ops_report.get("overall", {})
    return {
        "status": overall.get("status", "FAIL"),
        "blockers": overall.get("blockers", []),
        "health": health,
        "ops_health": ops_report,
        "exit_code": 0 if overall.get("status") in {"OK", "WARN"} else 1,
    }


def print_daily_report(result: dict[str, Any]) -> None:
    ops_report = result.get("ops_health") or {}
    health = result.get("health") or {}
    odds = ops_report.get("odds") or {}
    consistency = ops_report.get("result_consistency") or {}
    settlement = ops_report.get("settlement") or {}
    p1c = ops_report.get("p1c_prime") or {}
    print("Daily Ops Check Report")
    print(f"- time_utc: {datetime.now(timezone.utc).isoformat()}")
    print(f"- BETTING_ENABLED: {os.getenv('BETTING_ENABLED', 'unset')}")
    print(f"- DATABASE_URL_SET: {bool(os.getenv('DATABASE_URL'))}")
    print(f"- api_health_ok: {health.get('ok')}")
    print(f"- latest_ops_health_check_at: {health.get('latest_ops_health_check_at')}")
    print(f"- scheduler_stale: {health.get('scheduler_stale')}")
    print(f"- overall_status: {result.get('status')}")
    print(f"- blockers: {result.get('blockers')}")
    print(f"- odds_stale: {odds.get('odds_stale')}")
    print(f"- finished_null_count: {consistency.get('finished_null_count')}")
    print(f"- non_finished_with_result_count: {consistency.get('non_finished_with_result_count')}")
    print(f"- open_pending_bets: {settlement.get('open_pending_bets')}")
    print(f"- evaluable_finished_matches: {p1c.get('evaluable_finished_matches')}")


def _safe_fetch_health(url: str) -> dict[str, Any]:
    try:
        return fetch_api_health(url)
    except Exception as exc:
        return {
            "ok": False,
            "error": _sanitize_text(f"{type(exc).__name__}: {exc}"),
        }


def _sanitize_text(text: str) -> str:
    value = text
    for marker in ("DATABASE_URL", "JWT_SECRET", "TOKEN", "PASSWORD", "SECRET", "KEY"):
        value = value.replace(marker, "[redacted]")
    return value[:500]


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    health_url = argv[0] if argv else os.getenv("OPS_HEALTH_API_URL", DEFAULT_HEALTH_URL)
    result = run_daily_check(health_url=health_url)
    print_daily_report(result)
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
