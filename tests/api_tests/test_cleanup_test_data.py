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
        self.last_sql = " ".join(sql.split())
        self.conn.sql.append(self.last_sql)
        self.conn.params.append(params)
        if self.conn.fail_on_delete and self.last_sql.upper().startswith("DELETE"):
            raise RuntimeError("delete failed")

    def fetchall(self):
        sql = self.last_sql
        if "FROM users WHERE" in sql:
            return [(row["id"], row["username"]) for row in self.conn.users]
        if "FROM matches WHERE" in sql:
            return [(match_id,) for match_id in self.conn.matches]
        if "FROM bets" in sql:
            return [(bet_id,) for bet_id in self.conn.bets]
        return []

    def fetchone(self):
        if "500-" in self.last_sql and self.conn.real_match_scope_violation:
            return [1]
        return [0]


class FakeConn:
    def __init__(self):
        self.users = [{"id": 1, "username": "test_user_one"}, {"id": 2, "username": "codex_blocker_two"}]
        self.matches = ["test-settlement-1"]
        self.bets = [10, 11, 12]
        self.sql = []
        self.params = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_delete = False
        self.real_match_scope_violation = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def fake_connect(conn):
    @contextmanager
    def _connect():
        yield conn

    return _connect


def test_cleanup_dry_run_identifies_test_targets_without_writing(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    counts = cleanup_test_data.dry_run()

    assert counts == {"bet_legs": 0, "bets": 3, "matches": 1, "users": 2}
    assert not any(sql.upper().startswith("DELETE") for sql in conn.sql)
    assert conn.commits == 0
    assert conn.rollbacks == 0


def test_cleanup_run_requires_confirmation():
    with pytest.raises(ValueError):
        cleanup_test_data.run(confirm=None)


def test_cleanup_run_deletes_bets_before_users_and_uses_transaction(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    counts = cleanup_test_data.run(confirm="CLEAN_TEST_DATA")

    deletes = [sql for sql in conn.sql if sql.upper().startswith("DELETE")]
    assert counts == {"bet_legs": 0, "bets": 3, "matches": 1, "users": 2}
    assert "DELETE FROM bets" in deletes[0]
    assert "DELETE FROM matches" in deletes[1]
    assert "DELETE FROM users" in deletes[2]
    assert "match_id NOT LIKE '500-%%'" in deletes[1]
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_cleanup_protects_real_500_match(monkeypatch):
    conn = FakeConn()
    conn.matches = ["500-1359172"]
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    with pytest.raises(RuntimeError):
        cleanup_test_data.dry_run()


def test_cleanup_protects_non_test_user(monkeypatch):
    conn = FakeConn()
    conn.users = [{"id": 1, "username": "real_user"}]
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    with pytest.raises(RuntimeError):
        cleanup_test_data.dry_run()


def test_cleanup_rollback_on_delete_failure(monkeypatch):
    conn = FakeConn()
    conn.fail_on_delete = True
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(conn))

    with pytest.raises(RuntimeError):
        cleanup_test_data.run(confirm="CLEAN_TEST_DATA")

    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_cleanup_dry_run_and_run_target_counts_match(monkeypatch):
    dry_conn = FakeConn()
    run_conn = FakeConn()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(dry_conn))
    dry_counts = cleanup_test_data.dry_run()
    monkeypatch.setattr(cleanup_test_data, "connect", fake_connect(run_conn))
    run_counts = cleanup_test_data.run(confirm="CLEAN_TEST_DATA")

    assert dry_counts == run_counts
