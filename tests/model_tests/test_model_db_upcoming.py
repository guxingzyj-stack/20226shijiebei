from __future__ import annotations

from model import db


def test_fetch_upcoming_matches_includes_closed_but_not_finished() -> None:
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql):
            calls.append(sql)

        def fetchall(self):
            return []

    class Conn:
        def cursor(self, *args, **kwargs):
            return Cursor()

    db.fetch_upcoming_matches(Conn())  # type: ignore[arg-type]

    sql = calls[0]
    assert "status IN ('scheduled', 'closed')" in sql
    assert "finished" not in sql
    assert "kickoff_at >= now()" in sql

