from __future__ import annotations

from datetime import datetime, timezone

from api import result_source_mapping as mapping
from api import result_source_mapping_probe as probe


def test_normalize_team_name_supports_aliases_and_spaces():
    assert mapping.normalize_team_name("加 拿 大") == "加拿大"
    assert mapping.normalize_team_name("Canada") == "加拿大"
    assert mapping.normalize_team_name("Bosnia and Herzegovina") == "波黑"
    assert mapping.normalize_team_name("Korea Republic") == "韩国"
    assert mapping.normalize_team_name("South Korea") == "韩国"
    assert mapping.normalize_team_name("Czech Republic") == "捷克"
    assert mapping.normalize_team_name("USA") == "美国"
    assert mapping.normalize_team_name("Paraguay") == "巴拉圭"


def test_qiumibao_mapping_matches_by_team_and_time():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加 拿 大", "波 黑"),
        [_external("9001", "Canada", "Bosnia and Herzegovina", "2026-06-12T20:00:00+00:00")],
    )

    assert result["mapping_status"] == mapping.MATCHED
    assert result["external_id"] == "9001"
    assert result["local_match"]["normalized_home_team"] == "加拿大"
    assert result["candidates"][0]["normalized_away_team"] == "波黑"


def test_qiumibao_mapping_team_name_mismatch_when_time_close():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加拿大", "波黑"),
        [_external("9001", "Mexico", "South Africa", "2026-06-12T20:00:00+00:00")],
    )

    assert result["mapping_status"] == mapping.TEAM_NAME_MISMATCH


def test_qiumibao_mapping_kickoff_time_mismatch_when_teams_match():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加拿大", "波黑"),
        [_external("9001", "Canada", "Bosnia", "2026-06-13T20:00:00+00:00")],
    )

    assert result["mapping_status"] == mapping.KICKOFF_TIME_MISMATCH


def test_qiumibao_mapping_ambiguous_candidates():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加拿大", "波黑"),
        [
            _external("9001", "Canada", "Bosnia", "2026-06-12T20:00:00+00:00"),
            _external("9002", "Canada", "Bosnia", "2026-06-12T20:10:00+00:00"),
        ],
    )

    assert result["mapping_status"] == mapping.AMBIGUOUS_CANDIDATES


def test_qiumibao_mapping_source_available_but_match_not_in_window():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加拿大", "波黑"),
        [_external("9001", "Mexico", "South Africa", "2026-06-18T20:00:00+00:00")],
    )

    assert result["mapping_status"] == mapping.SOURCE_AVAILABLE_BUT_MATCH_NOT_IN_WINDOW


def test_qiumibao_mapping_source_empty():
    result = mapping.analyze_external_mapping(_local("500-1359182", "加拿大", "波黑"), [])

    assert result["mapping_status"] == mapping.SOURCE_EMPTY


def test_fifa_mapping_placeholder_is_explicit():
    result = mapping.fifa_mapping_placeholder(_local("500-1359182", "加拿大", "波黑"))

    assert result["mapping_status"] == mapping.FIFA_MAPPING_MISSING
    assert result["suggested_next_step"] == "build_fifa_match_id_mapping"


def test_probe_qiumibao_match_uses_source_rows(monkeypatch):
    monkeypatch.setattr(probe, "_local_match", lambda match_id: _local(match_id, "加拿大", "波黑"))
    monkeypatch.setattr(
        probe.qiumibao,
        "score_source_report",
        lambda date=None: {"source_fetch_ok": True, "parser_error": None, "matches": [_external("9001", "Canada", "Bosnia", "2026-06-12T20:00:00+00:00")]},
    )

    report = probe.probe_match("500-1359182")

    assert report["writes_db"] is False
    assert report["source_fetch_ok"] is True
    assert report["result"]["mapping_status"] == mapping.MATCHED
    assert report["result"]["external_id"] == "9001"


def test_probe_network_failure_does_not_crash(monkeypatch):
    monkeypatch.setattr(probe, "_local_match", lambda match_id: _local(match_id, "加拿大", "波黑"))
    monkeypatch.setattr(
        probe.qiumibao,
        "score_source_report",
        lambda date=None: {"source_fetch_ok": False, "parser_error": "timeout", "matches": []},
    )

    report = probe.probe_match("500-1359182")

    assert report["writes_db"] is False
    assert report["result"]["mapping_status"] == mapping.SOURCE_FETCH_ERROR


def _local(match_id: str, home: str, away: str) -> dict:
    return {
        "match_id": match_id,
        "home_team": home,
        "away_team": away,
        "kickoff_at": datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc),
        "status": "finished",
        "result_home": 1,
        "result_away": 1,
    }


def _external(external_id: str, home: str, away: str, kickoff: str) -> dict:
    return {
        "external_id": external_id,
        "home_team": home,
        "away_team": away,
        "kickoff_at": kickoff,
        "status": "finished",
        "result_home": 1,
        "result_away": 1,
    }
