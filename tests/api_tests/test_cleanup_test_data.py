from contextlib import contextmanager

import pytest

from api import cleanup_test_data


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.conn.sql.append(sql)

    def fetchone(self):
        sql = self.last_sql
        if "bets WHERE legs::text" in sql:
            return [2]
        if "matches WHERE match_id LIKE 'test-" in sql:
            return [1]
        if "users WHERE username" in sql:
            return [3]
        return [0]


class FakeConn:
    def __init__(self):
        self.sql = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def fake_connect(conn):
    @contextmanager
    def _connect():
        yield conn

    return _connect


def test_cleanup_dry_run_does_not_write(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    counts = cleanup_test_data.dry_run()

    assert counts == {"bets": 2, "matches": 1, "users": 3}
    assert not any(sql.strip().upper().startswith("DELETE") for sql in conn.sql)
    assert conn.commits == 0


def test_cleanup_run_requires_confirmation():
    with pytest.raises(ValueError):
        cleanup_test_data.run(confirm=None)


def test_cleanup_run_uses_only_test_scopes(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    cleanup_test_data.run(confirm="CLEAN_TEST_DATA")

    deletes = [sql for sql in conn.sql if sql.strip().upper().startswith("DELETE")]
    assert "legs::text LIKE '%%test-%%'" in deletes[0]
    assert "match_id LIKE 'test-%%'" in deletes[1]
    assert "username LIKE 'test_user_%%'" in deletes[2]
    assert "codex_blocker_%%" in deletes[2]
    assert all("500-" not in sql for sql in deletes)
    assert conn.commits == 1
