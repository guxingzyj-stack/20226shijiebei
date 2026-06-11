from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api import scheduler_health


def test_scheduler_freshness_marks_old_ops_log_stale(monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(minutes=120)

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return {"job_name": "settlement_runner", "started_at": old, "finished_at": old, "status": "ok", "summary": {}, "error": None}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(scheduler_health, "connect", lambda: Conn())

    report = scheduler_health.scheduler_freshness(threshold_minutes=90)

    assert report["scheduler_stale"] is True
    assert report["latest_ops_log_age_minutes"] >= 120


def test_scheduler_freshness_handles_database_error(monkeypatch):
    monkeypatch.setattr(scheduler_health, "connect", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    report = scheduler_health.scheduler_freshness()

    assert report["scheduler_last_seen"] is None
    assert report["scheduler_stale"] is None

