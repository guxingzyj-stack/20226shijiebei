from __future__ import annotations

from datetime import datetime, timezone

from api import main, result_overdue_report


def test_overdue_report_marks_verified_fallback_after_recent_sync(monkeypatch):
    class Cursor:
        def __init__(self):
            self.sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            self.sql = sql

        def fetchall(self):
            if "FROM matches" in self.sql:
                return [
                    {
                        "match_id": "500-1359182",
                        "match_num": "周五003",
                        "home_team": "加拿大",
                        "away_team": "波黑",
                        "kickoff_at": datetime(2026, 6, 12, tzinfo=timezone.utc),
                        "status": "closed",
                        "result_home": None,
                        "result_away": None,
                    }
                ]
            return []

        def fetchone(self):
            if "FROM ops_log" in self.sql:
                return {
                    "job_name": "results_sync",
                    "status": "ok",
                    "started_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
                    "finished_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
                    "summary": {"skipped": 20},
                    "error": None,
                }
            return None

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(result_overdue_report, "connect", lambda: Conn())
    monkeypatch.setattr(result_overdue_report, "scheduler_freshness", lambda: {"scheduler_stale": False})

    report = result_overdue_report.generate_report()

    assert report["ok"] is True
    assert report["overdue_count"] == 1
    assert report["matches"][0]["suggested_action"] == "NEEDS_VERIFIED_FALLBACK"


def test_overdue_report_marks_run_results_sync_when_scheduler_stale(monkeypatch):
    monkeypatch.setattr(result_overdue_report, "overdue_matches", lambda limit=50: [{"match_id": "500-x"}])
    monkeypatch.setattr(result_overdue_report, "latest_results_sync", lambda: None)
    monkeypatch.setattr(result_overdue_report, "scheduler_freshness", lambda: {"scheduler_stale": True})

    report = result_overdue_report.generate_report()

    assert report["matches"][0]["suggested_action"] == "RUN_RESULTS_SYNC"


def test_health_exposes_result_sync_observability(monkeypatch):
    monkeypatch.setattr(main, "scheduler_freshness", lambda: {"scheduler_last_seen": None, "scheduler_last_seen_age_minutes": None, "scheduler_stale": False})
    monkeypatch.setattr(main, "scheduler_startup_error", lambda: None)
    monkeypatch.setattr(main, "latest_ops_health_status", lambda: {"latest_ops_health_check_at": None, "ops_health_status": "WARN", "ops_health_blockers": []})
    monkeypatch.setattr(
        main,
        "_result_sync_health_summary",
        lambda: {
            "latest_results_sync_at": "2026-06-13T00:00:00+00:00",
            "latest_results_sync_status": "ok",
            "latest_results_sync_source": "500_trade_jczq",
            "latest_results_sync_finished_updated": 0,
            "latest_results_sync_skipped": 20,
            "latest_results_sync_skipped_reasons": {"not_finished_status": 20},
            "result_overdue_closed_count": 1,
            "result_overdue_closed_matches": [{"match_id": "500-1359182", "suggested_action": "NEEDS_VERIFIED_FALLBACK"}],
        },
    )
    monkeypatch.setattr(main, "_p3_fifa_health_summary", lambda: {})
    monkeypatch.setattr(main, "_betting_open_gate_health_summary", lambda: {})

    payload = main.health()

    assert payload["latest_results_sync_source"] == "500_trade_jczq"
    assert payload["latest_results_sync_skipped_reasons"] == {"not_finished_status": 20}
    assert payload["result_overdue_closed_count"] == 1
    assert "result_overdue_closed_matches" in payload["ops_health_blockers"]


def test_health_marks_results_sync_error_as_blocker(monkeypatch):
    monkeypatch.setattr(main, "scheduler_freshness", lambda: {"scheduler_last_seen": None, "scheduler_last_seen_age_minutes": None, "scheduler_stale": False})
    monkeypatch.setattr(main, "scheduler_startup_error", lambda: None)
    monkeypatch.setattr(main, "latest_ops_health_status", lambda: {"latest_ops_health_check_at": None, "ops_health_status": "OK", "ops_health_blockers": []})
    monkeypatch.setattr(
        main,
        "_result_sync_health_summary",
        lambda: {
            "latest_results_sync_status": "error",
            "result_overdue_closed_count": 0,
            "result_overdue_closed_matches": [],
        },
    )
    monkeypatch.setattr(main, "_p3_fifa_health_summary", lambda: {})
    monkeypatch.setattr(main, "_betting_open_gate_health_summary", lambda: {})

    payload = main.health()

    assert payload["ops_health_status"] == "WARN"
    assert "results_sync_error" in payload["ops_health_blockers"]
