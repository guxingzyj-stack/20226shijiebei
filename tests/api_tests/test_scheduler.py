from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api import acceptance_report, main, ops_log, scheduler
from api.ops_log import sanitize_error


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    scheduler._scheduler = None
    scheduler._scheduler_startup_error = None
    yield
    scheduler._scheduler = None
    scheduler._scheduler_startup_error = None


def test_scheduler_default_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_API_SCHEDULER", raising=False)

    assert scheduler.scheduler_enabled() is False


def test_scheduler_enabled_creates_jobs(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.delenv("ENABLE_RESULT_INGEST_MONITOR", raising=False)
    monkeypatch.setenv("RESULTS_SYNC_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("SETTLEMENT_RUNNER_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("OPS_HEALTH_CHECK_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("RUN_SCHEDULER_ON_STARTUP", "false")

    created = scheduler.create_scheduler()
    jobs = {job.id: job for job in created.get_jobs()}

    assert set(jobs) == {"results_sync_job", "settlement_runner_job", "ops_health_check_job"}
    assert all(job.max_instances == 1 for job in jobs.values())
    assert all(job.coalesce is True for job in jobs.values())


def test_result_ingest_monitor_job_created_only_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setenv("ENABLE_RESULT_INGEST_MONITOR", "true")
    monkeypatch.setenv("RESULT_INGEST_MONITOR_INTERVAL_MINUTES", "30")

    created = scheduler.create_scheduler()
    jobs = {job.id: job for job in created.get_jobs()}

    assert "result_ingest_monitor_job" in jobs
    assert jobs["result_ingest_monitor_job"].max_instances == 1
    assert jobs["result_ingest_monitor_job"].coalesce is True


def test_run_on_startup_schedules_first_interval(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setenv("RUN_SCHEDULER_ON_STARTUP", "true")
    before = datetime.now(timezone.utc)

    created = scheduler.create_scheduler()
    jobs = {job.id: job for job in created.get_jobs()}

    assert "ops_health_check_job" in jobs
    assert jobs["ops_health_check_job"].next_run_time > before + timedelta(minutes=20)


def test_start_api_scheduler_run_on_startup_runs_all_jobs(monkeypatch):
    calls = []

    class FakeScheduler:
        running = False

        def start(self):
            self.running = True

        def get_jobs(self):
            return [SimpleNamespace(id="results_sync_job"), SimpleNamespace(id="settlement_runner_job"), SimpleNamespace(id="ops_health_check_job")]

    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setenv("RUN_SCHEDULER_ON_STARTUP", "true")
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler, "_scheduler_startup_error", None)
    monkeypatch.setattr(scheduler, "create_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(scheduler, "run_results_sync_job", lambda dry_run, record_log: calls.append(("results_sync", dry_run, record_log)) or SimpleNamespace(matches_seen=1, errors=0))
    monkeypatch.setattr(scheduler, "run_settlement_job", lambda dry_run, record_log: calls.append(("settlement_runner", dry_run, record_log)) or SimpleNamespace(open_bets_seen=0, errors=0))
    monkeypatch.setattr(
        scheduler,
        "run_ops_health_check",
        lambda record_log: calls.append(("ops_health_check", record_log)) or {"overall": {"status": "WARN"}, "summary": {"overall_status": "WARN"}},
    )

    scheduler.start_api_scheduler()

    assert calls == [
        ("results_sync", False, True),
        ("settlement_runner", False, True),
        ("ops_health_check", True),
    ]
    assert scheduler.scheduler_startup_error() is None


def test_startup_job_error_is_recorded_for_health(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("DATABASE_URL=secret")

    monkeypatch.setattr(scheduler, "_scheduler_startup_error", None)
    monkeypatch.setattr(scheduler, "run_results_sync_job", fail)
    monkeypatch.setattr(scheduler, "run_settlement_job", lambda dry_run, record_log: SimpleNamespace(open_bets_seen=0, errors=0))
    monkeypatch.setattr(scheduler, "run_ops_health_check", lambda record_log: {"overall": {"status": "OK"}, "summary": {"overall_status": "OK"}})

    scheduler._run_startup_jobs()

    error = scheduler.scheduler_startup_error()
    assert error is not None
    assert "results_sync startup failed" in error
    assert "DATABASE_URL" not in error


def test_scheduler_jobs_catch_exceptions(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("DATABASE_URL should not leak")

    monkeypatch.setattr(scheduler, "run_results_sync_job", fail)
    monkeypatch.setattr(scheduler, "run_settlement_job", fail)
    monkeypatch.setattr(scheduler, "run_ops_health_check", fail)
    monkeypatch.setattr(scheduler, "run_result_ingest_monitor_once", fail)

    scheduler.results_sync_job()
    scheduler.settlement_runner_job()
    scheduler.ops_health_check_job()
    scheduler.result_ingest_monitor_job()


def test_scheduler_start_error_is_logged(monkeypatch, capsys):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setattr(scheduler, "create_scheduler", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    scheduler.start_api_scheduler()

    output = capsys.readouterr().out
    assert "api_scheduler_start_error" in output


def test_api_health_exposes_scheduler_startup_error(monkeypatch):
    monkeypatch.setattr(main, "scheduler_freshness", lambda: {"scheduler_last_seen": None, "scheduler_last_seen_age_minutes": None, "scheduler_stale": None})
    monkeypatch.setattr(main, "latest_ops_health_status", lambda: {"latest_ops_health_check_at": None, "ops_health_status": None, "ops_health_blockers": []})
    monkeypatch.setattr(main, "scheduler_startup_error", lambda: "results_sync startup failed: RuntimeError")
    monkeypatch.setattr(main, "_p3_fifa_health_summary", lambda: {})
    monkeypatch.setattr(main, "_betting_open_gate_health_summary", lambda: {})

    payload = main.health()

    assert payload["ok"] is False
    assert payload["scheduler_stale"] is True
    assert payload["scheduler_startup_error"] == "results_sync startup failed: RuntimeError"
    assert payload["ops_health_status"] == "FAIL"
    assert "scheduler_startup_error" in payload["ops_health_blockers"]


def test_error_sanitizer_redacts_secret_markers():
    error = sanitize_error(RuntimeError("JWT_SECRET=abc DATABASE_URL=postgres://secret PASSWORD=x"))

    assert "JWT_SECRET" not in error
    assert "DATABASE_URL" not in error
    assert "PASSWORD" not in error


def test_ops_log_success_write(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(ops_log, "connect", lambda: FakeConn())

    ops_log.record_ops_log("results_sync", "ok", datetime.now(timezone.utc), {"matches_seen": 1}, None)

    assert calls
    assert "INSERT INTO ops_log" in calls[0][0]
    assert calls[0][1][0] == "results_sync"
    assert calls[0][1][1] == "ok"


def test_acceptance_report_outputs_scheduler_status(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "false")
    monkeypatch.setenv("RESULTS_SYNC_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("SETTLEMENT_RUNNER_INTERVAL_MINUTES", "30")
    monkeypatch.setattr(acceptance_report, "_run_results_sync_dry_run", lambda: None)
    monkeypatch.setattr(acceptance_report, "_run_settlement_dry_run", lambda: None)
    monkeypatch.setattr(acceptance_report, "_recent_ops_log", lambda job_name: "NOT_CHECKED: ops_log table missing")

    report = acceptance_report.generate_report()
    scheduler_lines = {line.key: line.value for line in report["6. Scheduler"]}

    assert scheduler_lines["ENABLE_API_SCHEDULER"] == "false"
    assert scheduler_lines["scheduler_enabled"] is False
    assert scheduler_lines["RESULTS_SYNC_INTERVAL_MINUTES"] == "60"
    assert scheduler_lines["SETTLEMENT_RUNNER_INTERVAL_MINUTES"] == "30"


def test_betting_enabled_false_remains_default(monkeypatch):
    from api.betting import is_betting_enabled

    monkeypatch.delenv("BETTING_ENABLED", raising=False)

    assert is_betting_enabled() is False
