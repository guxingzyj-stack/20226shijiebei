from __future__ import annotations

from api import abnormal_status_probe


def test_abnormal_status_probe_refuses_production_confirm(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ALLOW_TEST_PROBES", raising=False)

    report = abnormal_status_probe.run_confirm("RUN_ABNORMAL_STATUS_PROBE")

    assert report["result"] == "FAIL"
    assert report["environment_guard_passed"] is False
    assert "must not run against production" in report["error"]


def test_abnormal_status_probe_dry_run_uses_only_test_match_ids(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    report = abnormal_status_probe.dry_run_report()

    assert report["mode"] == "dry-run"
    assert report["result"] == "PASS"
    assert all(match_id.startswith("test-") for match_id in report["created_test_matches"])
    assert report["writes_real_matches"] is False
    assert report["opens_betting"] is False


def test_abnormal_status_probe_confirm_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")

    report = abnormal_status_probe.run_confirm(None)

    assert report["result"] == "FAIL"
    assert "confirm token required" in report["error"]


def test_abnormal_status_probe_cleanup_sql_is_scoped(monkeypatch) -> None:
    executed = []

    class FakeCursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            executed.append((sql, params))

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(abnormal_status_probe, "connect", lambda: FakeConn())

    cleanup = abnormal_status_probe._cleanup_probe_data()

    assert cleanup == {"deleted_test_matches": 0, "deleted_probe_bets": 0, "deleted_probe_users": 0}
    match_delete_sql, match_delete_params = executed[1]
    assert "match_id = ANY" in match_delete_sql
    assert all(match_id.startswith("test-") for match_id in match_delete_params[0])
