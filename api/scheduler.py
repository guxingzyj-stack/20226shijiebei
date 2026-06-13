from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from api.ops_log import sanitize_error
from api.ops_health_check import run_ops_health_check
from api.results_sync import run_results_sync_job
from api.settlement_runner import run_settlement_job


_scheduler: BackgroundScheduler | None = None
_scheduler_startup_error: str | None = None


def scheduler_enabled() -> bool:
    return os.getenv("ENABLE_API_SCHEDULER", "false").strip().lower() in {"1", "true", "yes", "on"}


def run_on_startup_enabled() -> bool:
    return os.getenv("RUN_SCHEDULER_ON_STARTUP", "false").strip().lower() in {"1", "true", "yes", "on"}


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    results_interval = _env_int("RESULTS_SYNC_INTERVAL_MINUTES", 60)
    settlement_interval = _env_int("SETTLEMENT_RUNNER_INTERVAL_MINUTES", 30)
    ops_health_interval = _env_int("OPS_HEALTH_CHECK_INTERVAL_MINUTES", 30)
    now = datetime.now(timezone.utc)
    results_next_run_time: Any = now + timedelta(minutes=results_interval)
    settlement_next_run_time: Any = now + timedelta(minutes=settlement_interval)
    ops_health_next_run_time: Any = now + timedelta(minutes=ops_health_interval)
    scheduler.add_job(
        results_sync_job,
        "interval",
        minutes=results_interval,
        id="results_sync_job",
        max_instances=1,
        coalesce=True,
        next_run_time=results_next_run_time,
    )
    scheduler.add_job(
        settlement_runner_job,
        "interval",
        minutes=settlement_interval,
        id="settlement_runner_job",
        max_instances=1,
        coalesce=True,
        next_run_time=settlement_next_run_time,
    )
    scheduler.add_job(
        ops_health_check_job,
        "interval",
        minutes=ops_health_interval,
        id="ops_health_check_job",
        max_instances=1,
        coalesce=True,
        next_run_time=ops_health_next_run_time,
    )
    return scheduler


def start_api_scheduler() -> None:
    global _scheduler, _scheduler_startup_error
    _scheduler_startup_error = None
    if not scheduler_enabled():
        print({"event": "api_scheduler_skipped", "scheduler_enabled": False})
        return
    if _scheduler is not None and _scheduler.running:
        return
    try:
        _scheduler = create_scheduler()
        _scheduler.start()
        print({"event": "api_scheduler_started", "jobs": [job.id for job in _scheduler.get_jobs()]})
        if run_on_startup_enabled():
            _run_startup_jobs()
    except Exception as exc:
        _scheduler_startup_error = sanitize_error(exc)
        print({"event": "api_scheduler_start_error", "error": _scheduler_startup_error})
        _scheduler = None


def stop_api_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print({"event": "api_scheduler_stopped"})
    _scheduler = None


def results_sync_job() -> None:
    try:
        stats = run_results_sync_job(dry_run=False, record_log=True)
        print({"event": "scheduler_job_finished", "job_name": "results_sync", "status": "ok", "summary": stats.__dict__})
    except Exception as exc:
        print({"event": "scheduler_job_finished", "job_name": "results_sync", "status": "error", "error": sanitize_error(exc)})


def settlement_runner_job() -> None:
    try:
        stats = run_settlement_job(dry_run=False, record_log=True)
        print({"event": "scheduler_job_finished", "job_name": "settlement_runner", "status": "ok", "summary": stats.__dict__})
    except Exception as exc:
        print({"event": "scheduler_job_finished", "job_name": "settlement_runner", "status": "error", "error": sanitize_error(exc)})


def ops_health_check_job() -> None:
    try:
        report = run_ops_health_check(record_log=True)
        print({"event": "scheduler_job_finished", "job_name": "ops_health_check", "status": report["overall"]["status"].lower(), "summary": report["summary"]})
    except Exception as exc:
        print({"event": "scheduler_job_finished", "job_name": "ops_health_check", "status": "error", "error": sanitize_error(exc)})


def scheduler_startup_error() -> str | None:
    return _scheduler_startup_error


def _run_startup_jobs() -> None:
    global _scheduler_startup_error
    errors: list[str] = []
    for job_name, runner in (
        ("results_sync", _run_results_sync_startup),
        ("settlement_runner", _run_settlement_runner_startup),
        ("ops_health_check", _run_ops_health_check_startup),
    ):
        try:
            runner()
        except Exception as exc:
            error = sanitize_error(exc)
            errors.append(f"{job_name} startup failed: {error}")
            print({"event": "scheduler_startup_job_error", "job_name": job_name, "error": error})
    if errors:
        _scheduler_startup_error = "; ".join(errors)[:500]


def _run_results_sync_startup() -> None:
    stats = run_results_sync_job(dry_run=False, record_log=True)
    print({"event": "scheduler_job_finished", "job_name": "results_sync", "status": "ok", "startup": True, "summary": stats.__dict__})


def _run_settlement_runner_startup() -> None:
    stats = run_settlement_job(dry_run=False, record_log=True)
    print({"event": "scheduler_job_finished", "job_name": "settlement_runner", "status": "ok", "startup": True, "summary": stats.__dict__})


def _run_ops_health_check_startup() -> None:
    report = run_ops_health_check(record_log=True)
    print({"event": "scheduler_job_finished", "job_name": "ops_health_check", "status": report["overall"]["status"].lower(), "startup": True, "summary": report["summary"]})


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
