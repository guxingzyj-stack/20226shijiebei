from __future__ import annotations

from api import result_consistency_report


def test_result_consistency_report_detects_finished_missing_result(monkeypatch):
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
            if "status IN ('finished', 'completed')" in self.sql and "result_home IS NULL" in self.sql:
                return [
                    {
                        "match_id": "500-1359172",
                        "match_num": "001",
                        "home_team": "A",
                        "away_team": "B",
                        "kickoff_at": None,
                        "status": "finished",
                        "result_home": None,
                        "result_away": None,
                        "ht_home": None,
                        "ht_away": None,
                    }
                ]
            return []

        def fetchone(self):
            if "result_home IS NOT NULL" in self.sql:
                return [0]
            return [1]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(result_consistency_report, "connect", lambda: Conn())
    monkeypatch.setattr(
        result_consistency_report,
        "scheduler_freshness",
        lambda: {
            "latest_ops_log_at": "2026-06-12T00:00:00+00:00",
            "latest_results_sync_at": "2026-06-12T00:00:00+00:00",
            "latest_settlement_runner_at": "2026-06-12T00:00:00+00:00",
            "latest_ops_log_age_minutes": 10,
            "scheduler_stale": False,
        },
    )

    report = result_consistency_report.generate_report()

    assert report["finished_but_missing_result"]["count"] == 1
    assert report["settlement_readiness"]["ready_for_settlement_count"] == 0
    assert report["result"] == "WARN"


def test_result_consistency_report_warns_on_scheduler_stale(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return [0]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(result_consistency_report, "connect", lambda: Conn())
    monkeypatch.setattr(
        result_consistency_report,
        "scheduler_freshness",
        lambda: {
            "latest_ops_log_at": "2026-06-12T00:00:00+00:00",
            "latest_results_sync_at": "2026-06-12T00:00:00+00:00",
            "latest_settlement_runner_at": "2026-06-12T00:00:00+00:00",
            "latest_ops_log_age_minutes": 120,
            "scheduler_stale": True,
        },
    )

    report = result_consistency_report.generate_report()

    assert report["scheduler_freshness"]["scheduler_stale"] is True
    assert report["result"] == "WARN"

