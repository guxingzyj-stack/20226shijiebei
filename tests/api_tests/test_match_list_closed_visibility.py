from __future__ import annotations

from api.db import Database


def test_upcoming_query_includes_closed_and_no_market_matches(monkeypatch):
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

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr("api.db.connect", lambda: Conn())

    Database().list_matches(status="upcoming")

    assert "status IN ('scheduled', 'closed', 'no_market')" in calls[0][0]
    assert calls[0][1] is None
