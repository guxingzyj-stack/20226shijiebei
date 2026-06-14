from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from api import official_result_fallback


HEADER = "match_id,home_team,away_team,result_home,result_away,ht_home,ht_away,status,source_name,source_url,retrieved_at,verified_by,notes\n"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.params = None
        self.rowcount = 0
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.conn.sql.append(normalized)
        self.conn.params.append(params)
        self.params = params
        self.rowcount = 0
        if normalized.startswith("SELECT match_id"):
            match_id = params[0]
            self.result = self.conn.matches.get(match_id)
            return
        if normalized.startswith("UPDATE matches"):
            status, result_home, result_away, ht_home, ht_away, match_id = params
            match = self.conn.matches.get(match_id)
            if (
                match
                and match["status"] in {"scheduled", "closed", "finished", "completed"}
                and match["result_home"] is None
                and match["result_away"] is None
            ):
                match.update(
                    {
                        "status": status,
                        "result_home": result_home,
                        "result_away": result_away,
                        "ht_home": ht_home,
                        "ht_away": ht_away,
                    }
                )
                self.rowcount = 1
            return
        if normalized.startswith("INSERT INTO ops_log"):
            self.conn.ops_log.append(params)
            self.rowcount = 1
            return

    def fetchone(self):
        return self.result


class FakeConn:
    def __init__(self):
        self.matches = {
            "500-closed": {
                "match_id": "500-closed",
                "home_team": "Mexico",
                "away_team": "South Africa",
                "status": "closed",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            },
            "500-finished-null": {
                "match_id": "500-finished-null",
                "home_team": "Korea Republic",
                "away_team": "Czech Republic",
                "status": "finished",
                "result_home": None,
                "result_away": None,
                "ht_home": None,
                "ht_away": None,
            },
            "500-existing": {
                "match_id": "500-existing",
                "home_team": "A",
                "away_team": "B",
                "status": "finished",
                "result_home": 1,
                "result_away": 0,
                "ht_home": 1,
                "ht_away": 0,
            },
        }
        self.sql = []
        self.params = []
        self.ops_log = []

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)


def fake_connect(conn):
    @contextmanager
    def _connect():
        yield conn

    return _connect


def test_dry_run_does_not_write_db(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setattr(official_result_fallback, "connect", fake_connect(conn))
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://fifa.example/match,2026-06-12,operator,verified\n")

    report = official_result_fallback.dry_run(path)

    assert report["ok"] is True
    assert report["would_update_count"] == 1
    assert report["updated_count"] == 0
    assert conn.matches["500-closed"]["result_home"] is None
    assert not any(sql.startswith("UPDATE matches") for sql in conn.sql)
    assert conn.ops_log == []


def test_confirm_requires_code(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://fifa.example/match,2026-06-12,operator,verified\n")

    with pytest.raises(ValueError):
        official_result_fallback.apply_results(path, confirm=None)


def test_missing_source_url_fails(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,,2026-06-12,operator,verified\n")

    with pytest.raises(ValueError, match="source_url"):
        official_result_fallback.load_csv(path)


def test_missing_verified_by_fails(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://fifa.example/match,2026-06-12,,verified\n")

    with pytest.raises(ValueError, match="verified_by"):
        official_result_fallback.load_csv(path)


def test_placeholder_source_url_fails(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,<PASTE_OFFICIAL_URL>,2026-06-12,operator,verified\n")

    with pytest.raises(ValueError, match="source_url"):
        official_result_fallback.load_csv(path)


def test_chinese_placeholder_source_url_fails(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://这里换成官方链接,2026-06-12,operator,verified\n")

    with pytest.raises(ValueError, match="source_url"):
        official_result_fallback.load_csv(path)


def test_non_http_source_url_fails(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,file:///tmp/result,2026-06-12,operator,verified\n")

    with pytest.raises(ValueError, match="source_url"):
        official_result_fallback.load_csv(path)


def test_legal_http_source_url_passes(tmp_path):
    path = _csv(tmp_path, "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://www.fifa.com/match-centre/example,2026-06-12,operator,verified\n")

    rows = official_result_fallback.load_csv(path)

    assert rows[0].source_url == "https://www.fifa.com/match-centre/example"


def test_match_id_not_found_reports_error(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setattr(official_result_fallback, "connect", fake_connect(conn))
    path = _csv(tmp_path, "500-missing,Mexico,South Africa,2,0,,,finished,FIFA,https://fifa.example/match,2026-06-12,operator,verified\n")

    report = official_result_fallback.dry_run(path)

    assert report["ok"] is False
    assert report["error_count"] == 1
    assert report["matches"][0]["reason"] == "match_id_not_found"


def test_existing_result_is_skipped_without_overwrite(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setattr(official_result_fallback, "connect", fake_connect(conn))
    path = _csv(tmp_path, "500-existing,A,B,2,0,,,finished,FIFA,https://fifa.example/match,2026-06-12,operator,verified\n")

    report = official_result_fallback.apply_results(path, confirm=official_result_fallback.CONFIRM_CODE)

    assert report["updated_count"] == 0
    assert report["skipped_count"] == 1
    assert conn.matches["500-existing"]["result_home"] == 1
    assert conn.ops_log


def test_closed_and_finished_null_can_update_and_write_ops_log(monkeypatch, tmp_path):
    conn = FakeConn()
    monkeypatch.setattr(official_result_fallback, "connect", fake_connect(conn))
    path = _csv(
        tmp_path,
        "500-closed,Mexico,South Africa,2,0,,,finished,FIFA,https://fifa.example/match-a,2026-06-12,operator,verified\n"
        "500-finished-null,Korea Republic,Czech Republic,2,1,1,0,finished,FIFA,https://fifa.example/match-b,2026-06-12,operator,verified\n",
    )

    report = official_result_fallback.apply_results(path, confirm=official_result_fallback.CONFIRM_CODE)

    assert report["updated_count"] == 2
    assert conn.matches["500-closed"]["status"] == "finished"
    assert conn.matches["500-closed"]["result_home"] == 2
    assert conn.matches["500-finished-null"]["result_away"] == 1
    assert conn.matches["500-finished-null"]["ht_home"] == 1
    assert conn.ops_log
    assert conn.ops_log[-1][0] == official_result_fallback.JOB_NAME
    assert conn.ops_log[-1][1] == "ok"


def _csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "official_results_verified.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path
