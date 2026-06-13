from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api import result_source_compare
from api.sources import qiumibao


def test_normalize_team_name_removes_visible_and_invisible_spaces():
    assert result_source_compare.normalize_team_name("加 拿 大") == "加拿大"
    assert result_source_compare.normalize_team_name("波\u3000黑") == "波黑"
    assert result_source_compare.normalize_team_name("\ufeff墨 西 哥\u200b") == "墨西哥"
    assert result_source_compare.normalize_team_name("南 非") == "南非"
    assert result_source_compare.normalize_team_name("韩 国") == "韩国"
    assert result_source_compare.normalize_team_name("捷 克") == "捷克"


def test_qiumibao_score_json_parses_finished_score():
    payload = {
        "list": [
            {
                "id": "1359182",
                "state": 3,
                "left": {"name": "加拿大", "score": "1"},
                "right": {"name": "波黑", "score": "1"},
                "time": "2026-06-12 19:00",
            }
        ]
    }

    rows = qiumibao.normalize_score_payload(payload)

    assert rows[0].status == "finished"
    assert rows[0].result_home == 1
    assert rows[0].result_away == 1
    assert rows[0].ht_home is None
    assert rows[0].ht_away is None


def test_qiumibao_score_json_missing_rows_returns_parser_error():
    with pytest.raises(ValueError, match="parser_error"):
        qiumibao.normalize_score_payload({"unexpected": []})


def test_qiumibao_events_parse_goal_event():
    payload = {"data": [{"time": "12", "event_code_cn": "进球", "player_name_cn": "球员A", "sl_team_name": "加拿大", "score": "1-0"}]}

    events = qiumibao.normalize_event_payload(payload)

    assert events[0].minute == "12"
    assert events[0].event_type == "进球"
    assert events[0].player == "球员A"
    assert events[0].score_after_event == "1-0"


def test_compare_ok_when_local_and_qiumibao_agree(monkeypatch):
    local = _local_match(result_home=1, result_away=1, status="finished")
    monkeypatch.setattr(result_source_compare, "_local_match", lambda match_id: local)
    monkeypatch.setattr(result_source_compare, "_source_500", lambda match_id: {"seen": True, "status": "finished", "score": "1-1", "ht_score": None, "confidence": "medium"})
    monkeypatch.setattr(result_source_compare.qiumibao, "score_source_report", lambda date=None: _q_score("1", "1"))
    monkeypatch.setattr(result_source_compare, "_source_qiumibao_events", lambda local, date, qiumibao_score_source=None: {"seen": True, "status": "unknown", "events": [], "confidence": "medium"})

    report = result_source_compare.compare_match("500-1359182")

    assert report["writes_db"] is False
    assert report["comparison"]["suggested_action"] == "OK_MATCH"
    assert report["comparison"]["external_confirmed"] is True
    assert "qiumibao_score" in report["comparison"]["external_confirming_sources"]
    assert report["comparison"]["conflicts"] == []


def test_compare_local_score_without_external_confirmation_is_local_db_only(monkeypatch):
    local = _local_match(result_home=2, result_away=0, status="finished")
    monkeypatch.setattr(result_source_compare, "_local_match", lambda match_id: local)
    monkeypatch.setattr(result_source_compare, "_source_500", lambda match_id: {"seen": False, "status": "source_not_found", "score": None, "ht_score": None, "confidence": "unknown"})
    monkeypatch.setattr(result_source_compare.qiumibao, "score_source_report", lambda date=None: {"source_fetch_ok": True, "matches": []})
    monkeypatch.setattr(result_source_compare, "_source_qiumibao_events", lambda local, date, qiumibao_score_source=None: {"seen": False, "status": "mapping_missing", "events": [], "confidence": "unknown"})

    report = result_source_compare.compare_match("500-1359182")

    assert report["comparison"]["suggested_action"] == "LOCAL_DB_ONLY"
    assert report["comparison"]["external_confirmed"] is False
    assert report["comparison"]["external_confirming_sources"] == []


def test_compare_needs_verified_fallback_when_local_missing_but_source_finished(monkeypatch):
    local = _local_match(result_home=None, result_away=None, status="closed")
    monkeypatch.setattr(result_source_compare, "_local_match", lambda match_id: local)
    monkeypatch.setattr(result_source_compare, "_source_500", lambda match_id: {"seen": False, "status": "source_not_found", "score": None, "ht_score": None, "confidence": "unknown"})
    monkeypatch.setattr(result_source_compare.qiumibao, "score_source_report", lambda date=None: _q_score("1", "1"))
    monkeypatch.setattr(result_source_compare, "_source_qiumibao_events", lambda local, date, qiumibao_score_source=None: {"seen": True, "status": "unknown", "events": [], "confidence": "medium"})

    report = result_source_compare.compare_match("500-1359182")

    assert report["comparison"]["suggested_action"] == "NEEDS_VERIFIED_FALLBACK"
    assert report["comparison"]["consensus_score"] == "1-1"


def test_compare_conflict_needs_review(monkeypatch):
    local = _local_match(result_home=2, result_away=0, status="finished")
    monkeypatch.setattr(result_source_compare, "_local_match", lambda match_id: local)
    monkeypatch.setattr(result_source_compare, "_source_500", lambda match_id: {"seen": True, "status": "finished", "score": "2-0", "ht_score": None, "confidence": "medium"})
    monkeypatch.setattr(result_source_compare.qiumibao, "score_source_report", lambda date=None: _q_score("1", "1"))
    monkeypatch.setattr(result_source_compare, "_source_qiumibao_events", lambda local, date, qiumibao_score_source=None: {"seen": True, "status": "unknown", "events": [], "confidence": "medium"})

    report = result_source_compare.compare_match("500-1359182")

    assert report["comparison"]["suggested_action"] == "CONFLICT_NEEDS_REVIEW"
    assert report["comparison"]["conflicts"]


def test_compare_mapping_missing(monkeypatch):
    local = _local_match(result_home=None, result_away=None, status="closed")
    monkeypatch.setattr(result_source_compare, "_local_match", lambda match_id: local)
    monkeypatch.setattr(result_source_compare, "_source_500", lambda match_id: {"seen": False, "status": "source_not_found", "score": None, "ht_score": None, "confidence": "unknown"})
    monkeypatch.setattr(result_source_compare.qiumibao, "score_source_report", lambda date=None: {"source_fetch_ok": True, "matches": []})
    monkeypatch.setattr(result_source_compare, "_source_qiumibao_events", lambda local, date, qiumibao_score_source=None: {"seen": False, "status": "mapping_missing", "events": [], "confidence": "unknown"})

    report = result_source_compare.compare_match("500-1359182")

    assert report["comparison"]["suggested_action"] == "MAPPING_MISSING"


def test_qiumibao_events_requires_external_match_id(monkeypatch):
    def fail_if_called(date, match_id):
        raise AssertionError("events fetcher should not be called without qiumibao external_id")

    monkeypatch.setattr(result_source_compare.qiumibao, "events_source_report", fail_if_called)

    source = result_source_compare._source_qiumibao_events(
        _local_match(result_home=1, result_away=1, status="finished"),
        "2026-06-12",
        {"seen": False, "status": "mapping_missing"},
    )

    assert source["seen"] is False
    assert source["status"] == "mapping_missing"
    assert source["mapping_status"] == "missing"


def test_qiumibao_network_failure_does_not_crash():
    def fail(_date=None):
        raise RuntimeError("network down")

    report = qiumibao.score_source_report(date="2026-06-12", fetcher=fail)

    assert report["source_fetch_ok"] is False
    assert report["parser_error"]
    assert report["matches"] == []


def test_compare_all_overdue_is_dry_run(monkeypatch):
    monkeypatch.setattr(result_source_compare, "overdue_matches", lambda limit=20: [{"match_id": "500-1359182"}])
    monkeypatch.setattr(result_source_compare, "compare_match", lambda match_id: {"match_id": match_id, "writes_db": False})

    report = result_source_compare.compare_all_overdue()

    assert report["writes_db"] is False
    assert report["matches"] == [{"match_id": "500-1359182", "writes_db": False}]


def _local_match(result_home, result_away, status):
    return {
        "match_id": "500-1359182",
        "home_team": "加拿大",
        "away_team": "波黑",
        "kickoff_at": datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc),
        "status": status,
        "result_home": result_home,
        "result_away": result_away,
        "ht_home": None,
        "ht_away": None,
    }


def _q_score(home: str, away: str):
    return {
        "source_fetch_ok": True,
        "matches": [
            {
                "external_id": "1359182",
                "home_team": "加拿大",
                "away_team": "波黑",
                "kickoff_at": "2026-06-12T19:00:00+00:00",
                "status": "finished",
                "result_home": int(home),
                "result_away": int(away),
                "ht_home": None,
                "ht_away": None,
            }
        ],
    }
