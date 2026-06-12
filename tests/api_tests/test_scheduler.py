from datetime import datetime, timezone

from api import acceptance_report, ops_log, scheduler
from api.ops_log import sanitize_error


def test_scheduler_default_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_API_SCHEDULER", raising=False)

    assert scheduler.scheduler_enabled() is False


def test_scheduler_enabled_creates_jobs(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setenv("RESULTS_SYNC_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("SETTLEMENT_RUNNER_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("OPS_HEALTH_CHECK_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("RUN_SCHEDULER_ON_STARTUP", "false")

    created = scheduler.create_scheduler()
    jobs = {job.id: job for job in created.get_jobs()}

    assert set(jobs) == {"results_sync_job", "settlement_runner_job", "ops_health_check_job"}
    assert all(job.max_instances == 1 for job in jobs.values())
    assert all(job.coalesce is True for job in jobs.values())


def test_scheduler_jobs_catch_exceptions(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("DATABASE_URL should not leak")

    monkeypatch.setattr(scheduler, "run_results_sync_job", fail)
    monkeypatch.setattr(scheduler, "run_settlement_job", fail)
    monkeypatch.setattr(scheduler, "run_ops_health_check", fail)

    scheduler.results_sync_job()
    scheduler.settlement_runner_job()
    scheduler.ops_health_check_job()


def test_scheduler_start_error_is_logged(monkeypatch, capsys):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "true")
    monkeypatch.setattr(scheduler, "create_scheduler", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    scheduler.start_api_scheduler()

    output = capsys.readouterr().out
    assert "api_scheduler_start_error" in output


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
