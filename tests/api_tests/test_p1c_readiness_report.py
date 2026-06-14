from __future__ import annotations

from contextlib import contextmanager

from api import p1c_readiness_report


class FakeCursor:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        return {
            "usable_finished_matches": 4,
            "finished_matches": 5,
            "finished_missing_result": 1,
            "non_finished_with_result": 0,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def cursor(self, *args, **kwargs):
        return self.cursor_obj


def test_p1c_readiness_counts_remaining_and_is_read_only(monkeypatch):
    conn = FakeConn()

    @contextmanager
    def fake_connect():
        yield conn

    monkeypatch.setattr(p1c_readiness_report, "connect", fake_connect)

    report = p1c_readiness_report.generate_report()

    assert report["writes_db"] is False
    assert report["usable_finished_matches"] == 4
    assert report["target_finished_matches"] == 30
    assert report["remaining_to_p1c_prime"] == 26
    assert report["p1c_ready"] is False
    assert "UPDATE" not in conn.cursor_obj.sql.upper()
