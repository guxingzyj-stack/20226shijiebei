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


def test_optional_match_id_parameters_are_cast_to_text(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            calls.append((sql, params))

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
            "latest_ops_log_at": None,
            "latest_results_sync_at": None,
            "latest_settlement_runner_at": None,
            "latest_ops_log_age_minutes": None,
            "scheduler_stale": False,
        },
    )

    result_consistency_report.generate_report(match_id=None)

    assert calls
    assert all("%s::text IS NULL OR match_id = %s" in sql for sql, _ in calls)
    assert all(params == (None, None) for _, params in calls)


def test_repair_finished_null_dry_run_lists_targets_without_update(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            calls.append(sql)

        def fetchall(self):
            return [
                {
                    "match_id": "500-1359172",
                    "match_num": "周四001",
                    "home_team": "墨西哥",
                    "away_team": "南非",
                    "kickoff_at": None,
                    "status": "finished",
                    "result_home": None,
                    "result_away": None,
                    "ht_home": None,
                    "ht_away": None,
                }
            ]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr(result_consistency_report, "connect", lambda: Conn())

    report = result_consistency_report.repair_finished_null(dry_run=True)

    assert report["mode"] == "dry-run"
    assert report["would_update_count"] == 1
    assert report["updated_count"] == 0
    assert all("UPDATE matches" not in sql for sql in calls)


def test_repair_finished_null_requires_confirm_for_run():
    report = result_consistency_report.repair_finished_null(dry_run=False, confirm=None)

    assert report["ok"] is False
    assert report["updated_count"] == 0


def test_repair_finished_null_confirm_updates_only_both_null_scores(monkeypatch):
    calls = []

    class Cursor:
        def __init__(self):
            self.sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            self.sql = sql
            calls.append(sql)

        def fetchall(self):
            if "UPDATE matches" in self.sql:
                assert "result_home IS NULL" in self.sql
                assert "result_away IS NULL" in self.sql
                assert "SET status = 'closed'" in self.sql
                return [("500-1359172",), ("500-1359224",)]
            return [
                {
                    "match_id": "500-1359172",
                    "match_num": "周四001",
                    "home_team": "墨西哥",
                    "away_team": "南非",
                    "kickoff_at": None,
                    "status": "finished",
                    "result_home": None,
                    "result_away": None,
                    "ht_home": None,
                    "ht_away": None,
                },
                {
                    "match_id": "500-1359224",
                    "match_num": "周四002",
                    "home_team": "韩国",
                    "away_team": "捷克",
                    "kickoff_at": None,
                    "status": "finished",
                    "result_home": None,
                    "result_away": None,
                    "ht_home": None,
                    "ht_away": None,
                },
            ]

    class Tx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

        def transaction(self):
            return Tx()

    monkeypatch.setattr(result_consistency_report, "connect", lambda: Conn())

    report = result_consistency_report.repair_finished_null(dry_run=False, confirm="REPAIR_FINISHED_NULL")

    assert report["mode"] == "run"
    assert report["ok"] is True
    assert report["would_update_count"] == 2
    assert report["updated_count"] == 2
    assert report["updated_match_ids"] == ["500-1359172", "500-1359224"]
    assert any("UPDATE matches" in sql for sql in calls)
