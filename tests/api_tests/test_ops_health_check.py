from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api import main, ops_health_check


def test_ops_health_check_ok_when_system_healthy():
    status, blockers = ops_health_check.evaluate_status(
        scheduler_stale=False,
        latest_results_sync_age_minutes=10,
        latest_settlement_runner_age_minutes=10,
        latest_odds_snapshot_age_minutes=8,
        finished_null_count=0,
        non_finished_with_result_count=0,
        latest_settlement_runner_status="ok",
        latest_settlement_runner_error=None,
        open_pending_bets=1,
        evaluable_finished_matches=30,
    )

    assert status == "OK"
    assert blockers == []


def test_ops_health_check_fails_when_scheduler_stale():
    status, blockers = ops_health_check.evaluate_status(
        scheduler_stale=True,
        latest_results_sync_age_minutes=10,
        latest_settlement_runner_age_minutes=10,
        latest_odds_snapshot_age_minutes=8,
        finished_null_count=0,
        non_finished_with_result_count=0,
        latest_settlement_runner_status="ok",
        latest_settlement_runner_error=None,
        open_pending_bets=1,
        evaluable_finished_matches=30,
    )

    assert status == "FAIL"
    assert "scheduler_stale" in blockers


def test_ops_health_check_fails_when_finished_null_exists():
    status, blockers = ops_health_check.evaluate_status(
        scheduler_stale=False,
        latest_results_sync_age_minutes=10,
        latest_settlement_runner_age_minutes=10,
        latest_odds_snapshot_age_minutes=8,
        finished_null_count=1,
        non_finished_with_result_count=0,
        latest_settlement_runner_status="ok",
        latest_settlement_runner_error=None,
        open_pending_bets=1,
        evaluable_finished_matches=30,
    )

    assert status == "FAIL"
    assert "finished_null_recurred" in blockers


def test_ops_health_check_fails_when_odds_stale():
    status, blockers = ops_health_check.evaluate_status(
        scheduler_stale=False,
        latest_results_sync_age_minutes=10,
        latest_settlement_runner_age_minutes=10,
        latest_odds_snapshot_age_minutes=31,
        finished_null_count=0,
        non_finished_with_result_count=0,
        latest_settlement_runner_status="ok",
        latest_settlement_runner_error=None,
        open_pending_bets=1,
        evaluable_finished_matches=30,
        odds_stale_threshold_minutes=30,
    )

    assert status == "FAIL"
    assert "odds_snapshot_stale" in blockers


def test_ops_health_check_warns_without_open_bets_or_enough_samples():
    status, blockers = ops_health_check.evaluate_status(
        scheduler_stale=False,
        latest_results_sync_age_minutes=10,
        latest_settlement_runner_age_minutes=10,
        latest_odds_snapshot_age_minutes=8,
        finished_null_count=0,
        non_finished_with_result_count=0,
        latest_settlement_runner_status="ok",
        latest_settlement_runner_error=None,
        open_pending_bets=0,
        evaluable_finished_matches=2,
    )

    assert status == "WARN"
    assert "no_open_bets_to_settle" in blockers
    assert "insufficient_finished_matches" in blockers


def test_ops_health_check_records_ops_log(monkeypatch):
    recorded = []
    report = {
        "overall": {"status": "WARN", "blockers": ["no_open_bets_to_settle"]},
        "summary": {"overall_status": "WARN", "blockers": ["no_open_bets_to_settle"]},
    }
    monkeypatch.setattr(ops_health_check, "generate_report", lambda: report)
    monkeypatch.setattr(ops_health_check, "record_ops_log", lambda *args, **kwargs: recorded.append((args, kwargs)))

    returned = ops_health_check.run_ops_health_check(record_log=True)

    assert returned is report
    assert recorded
    assert recorded[0][0][0] == "ops_health_check"
    assert recorded[0][0][1] == "warn"


def test_ops_health_check_alert_disabled_does_not_call_webhook(monkeypatch):
    monkeypatch.setenv("OPS_ALERT_ENABLED", "false")
    called = []
    monkeypatch.setattr(ops_health_check.request, "urlopen", lambda *args, **kwargs: called.append(args))

    ops_health_check._maybe_send_alert({"overall": {"status": "FAIL", "blockers": ["x"]}, "scheduler": {}, "odds": {}, "result_consistency": {}})

    assert called == []


def test_ops_health_check_alert_enabled_without_webhook_does_not_crash(monkeypatch):
    monkeypatch.setenv("OPS_ALERT_ENABLED", "true")
    monkeypatch.delenv("OPS_ALERT_WEBHOOK_URL", raising=False)

    ops_health_check._maybe_send_alert({"overall": {"status": "FAIL", "blockers": ["x"]}, "scheduler": {}, "odds": {}, "result_consistency": {}})


def test_latest_ops_health_status_db_unavailable_does_not_crash(monkeypatch):
    monkeypatch.setattr(ops_health_check, "connect", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    status = ops_health_check.latest_ops_health_status()

    assert status["latest_ops_health_check_at"] is None
    assert status["ops_health_status"] is None
    assert status["ops_health_blockers"] == []


def test_api_health_includes_ops_health_when_db_unavailable(monkeypatch):
    monkeypatch.setattr(main, "scheduler_freshness", lambda: {
        "scheduler_last_seen": None,
        "scheduler_last_seen_age_minutes": None,
        "scheduler_stale": None,
    })
    monkeypatch.setattr(main, "latest_ops_health_status", lambda: {
        "latest_ops_health_check_at": None,
        "ops_health_status": None,
        "ops_health_blockers": [],
    })

    payload = main.health()

    assert payload["ok"] is True
    assert payload["latest_ops_health_check_at"] is None
    assert payload["ops_health_blockers"] == []


def test_latest_ops_health_status_reads_summary(monkeypatch):
    now = datetime.now(timezone.utc) - timedelta(minutes=3)

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchone(self):
            return {
                "job_name": "ops_health_check",
                "status": "warn",
                "started_at": now,
                "finished_at": now,
                "summary": {"overall_status": "WARN", "blockers": ["no_open_bets_to_settle"]},
                "error": None,
            }

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return FakeCursor()

    monkeypatch.setattr(ops_health_check, "connect", lambda: FakeConn())

    status = ops_health_check.latest_ops_health_status()

    assert status["ops_health_status"] == "WARN"
    assert status["ops_health_blockers"] == ["no_open_bets_to_settle"]
