from datetime import datetime, timedelta, timezone

from api import scheduler_observe


def test_scheduler_observe_pass_when_scheduler_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_API_SCHEDULER", "false")
    report = {
        "latest results_sync ops_log": None,
        "latest settlement_runner ops_log": None,
        "latest odds_snapshots fetched_at": None,
        "open_bets_count": 0,
    }

    assert scheduler_observe._result(report, False, datetime.now(timezone.utc)) == "PASS"


def test_scheduler_observe_wait_when_enabled_and_logs_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    report = {
        "latest results_sync ops_log": {"started_at": now - timedelta(minutes=61), "status": "ok"},
        "latest settlement_runner ops_log": {"started_at": now - timedelta(minutes=10), "status": "ok"},
        "latest odds_snapshots fetched_at": now,
        "open_bets_count": 0,
    }

    assert scheduler_observe._result(report, True, now) == "WAIT"


def test_scheduler_observe_fail_on_not_checked():
    report = {
        "latest results_sync ops_log": "NOT_CHECKED: missing",
        "latest settlement_runner ops_log": None,
        "latest odds_snapshots fetched_at": None,
        "open_bets_count": 0,
    }

    assert scheduler_observe._result(report, True, datetime.now(timezone.utc)) == "FAIL"
