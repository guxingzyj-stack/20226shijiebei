from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from api import external_result_sync as sync


NOW = datetime(2026, 6, 14, 16, 0, tzinfo=timezone.utc)
LOCAL = {
    "match_id": "500-1359227",
    "match_num": "周日001",
    "home_team": "卡塔尔",
    "away_team": "瑞士",
    "kickoff_at": datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
    "status": "closed",
    "result_home": None,
    "result_away": None,
}


def _event(**overrides):
    event = {
        "source": "thesportsdb",
        "source_url": "https://www.thesportsdb.com/api/test",
        "external_id": "evt-1",
        "raw_home": "Qatar",
        "raw_away": "Switzerland",
        "normalized_home": "卡塔尔",
        "normalized_away": "瑞士",
        "kickoff_at": "2026-06-14T12:00:00+00:00",
        "status": "finished",
        "result_home": 1,
        "result_away": 2,
    }
    event.update(overrides)
    return event


def _source_report(events):
    return {
        "source_fetch_ok": True,
        "source_url": "https://source.example",
        "events_seen": len(events),
        "events": events,
        "parser_error": None,
        "scoreboard_dates": [],
    }


def _patch_plan(monkeypatch, events, locals_=None, current_500=None):
    monkeypatch.setattr(sync, "fetch_source_events", lambda source, date: _source_report(events))
    monkeypatch.setattr(sync, "fetch_espn_events_for_dates", lambda dates: {**_source_report(events), "scoreboard_dates": dates})
    monkeypatch.setattr(sync, "load_local_candidates", lambda date, now: list(locals_ if locals_ is not None else [LOCAL]))
    monkeypatch.setattr(sync, "current_500_match_ids", lambda: dict(current_500 or {}))


def test_external_finished_score_dry_run_matches(monkeypatch):
    _patch_plan(monkeypatch, [_event()])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["writes_db"] is False
    assert report["would_update_count"] == 1
    assert report["matches"][0]["reason"] == "external_result_matched"


def test_espn_final_score_dry_run_matches(monkeypatch):
    espn_event = _event(source="espn", source_url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260614")
    _patch_plan(monkeypatch, [espn_event])

    report = sync.dry_run("espn", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 1
    assert report["matches"][0]["external_source"] == "espn"


def test_espn_sync_matches_previous_et_bucket_when_cli_date_is_utc_date(monkeypatch):
    captured = {}

    def fake_fetch_espn(dates):
        captured["dates"] = dates
        return {
            "source_fetch_ok": True,
            "source_url": "https://site.api.espn.com",
            "events_seen": 1,
            "events": [_event(source="espn", external_id="760418", external_source_date="20260613")],
            "parser_error": None,
            "scoreboard_dates": dates,
        }

    monkeypatch.setattr(sync, "fetch_espn_events_for_dates", fake_fetch_espn)
    monkeypatch.setattr(sync, "load_local_candidates", lambda date, now: [LOCAL])
    monkeypatch.setattr(sync, "current_500_match_ids", lambda: {})

    report = sync.dry_run("espn", "2026-06-14", now=NOW)

    assert "20260613" in captured["dates"]
    assert "20260614" in captured["dates"]
    assert report["would_update_count"] == 1
    assert report["matches"][0]["external_source_date"] == "20260613"


def test_espn_500_fetch_error_is_diagnostic_not_skip_reason(monkeypatch):
    espn_event = _event(source="espn")
    _patch_plan(monkeypatch, [espn_event], current_500={"__source_error__": "source_500_fetch_error"})

    report = sync.dry_run("espn", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 1
    assert report["matches"][0]["reason"] == "external_result_matched"
    assert report["matches"][0]["source_500_diagnostic"] == "source_500_fetch_error"


def test_espn_500_still_present_is_diagnostic_not_skip_reason(monkeypatch):
    espn_event = _event(source="espn")
    _patch_plan(monkeypatch, [espn_event], current_500={"500-1359227": "closed"})

    report = sync.dry_run("espn", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 1
    assert report["matches"][0]["reason"] == "external_result_matched"
    assert report["matches"][0]["source_500_diagnostic"] == "source_500_still_present"
    assert report["matches"][0]["source_500_status"] == "closed"


def test_non_espn_500_fetch_error_still_blocks_external_fallback(monkeypatch):
    _patch_plan(monkeypatch, [_event()], current_500={"__source_error__": "source_500_fetch_error"})

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "source_500_fetch_error"
    assert report["matches"][0]["source_500_diagnostic"] == "source_500_fetch_error"


def test_external_not_final_does_not_write(monkeypatch):
    _patch_plan(monkeypatch, [_event(status="scheduled")])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "external_result_status_not_final"


def test_external_score_missing_does_not_write(monkeypatch):
    _patch_plan(monkeypatch, [_event(result_home=None, result_away=None)])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "external_result_score_missing"


def test_team_mismatch_does_not_write(monkeypatch):
    _patch_plan(monkeypatch, [_event(normalized_home="巴西", normalized_away="摩洛哥")])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "external_result_no_candidate"


def test_ambiguous_candidates_do_not_write(monkeypatch):
    _patch_plan(monkeypatch, [_event(external_id="a"), _event(external_id="b")])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "external_result_ambiguous"


def test_reversed_team_order_does_not_write(monkeypatch):
    _patch_plan(monkeypatch, [_event(normalized_home="瑞士", normalized_away="卡塔尔", raw_home="Switzerland", raw_away="Qatar")])

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "external_result_reversed_team_order"


def test_500_current_window_presence_blocks_external_fallback(monkeypatch):
    _patch_plan(monkeypatch, [_event()], current_500={"500-1359227": "scheduled"})

    report = sync.dry_run("thesportsdb", "2026-06-14", now=NOW)

    assert report["would_update_count"] == 0
    assert report["matches"][0]["reason"] == "source_500_still_present"


def test_confirm_requires_explicit_code(monkeypatch):
    _patch_plan(monkeypatch, [_event()])

    with pytest.raises(ValueError, match=sync.CONFIRM_CODE):
        sync.apply_results("thesportsdb", "2026-06-14", confirm=None, now=NOW)


def test_confirm_writes_result_and_ops_log(monkeypatch):
    _patch_plan(monkeypatch, [_event()])
    conn = FakeConn()
    records = []
    monkeypatch.setattr(sync, "connect", fake_connect(conn))
    monkeypatch.setattr(sync, "record_ops_log", lambda *args, **kwargs: records.append((args, kwargs)))

    report = sync.apply_results("thesportsdb", "2026-06-14", confirm=sync.CONFIRM_CODE, now=NOW)

    assert report["updated_count"] == 1
    assert conn.updated
    assert conn.updated[0][0:2] == (1, 2)
    assert records
    assert records[0][0][0] == sync.JOB_NAME
    assert records[0][1]["summary"]["matched"][0]["verified_mode"] == "structured_source"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.rowcount = 0
        if normalized.startswith("UPDATE matches"):
            self.conn.updated.append(params)
            self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self):
        self.updated = []

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)


def fake_connect(conn):
    @contextmanager
    def _connect():
        yield conn

    return _connect
