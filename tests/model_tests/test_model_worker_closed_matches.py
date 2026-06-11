from __future__ import annotations

from model import db


def test_fetch_upcoming_matches_scans_scheduled_and_closed_without_results() -> None:
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
    assert "result_home IS NULL" in sql
    assert "result_away IS NULL" in sql
    assert "kickoff_at >= now()" in sql
    assert "completed" not in sql
    assert "finished" not in sql
