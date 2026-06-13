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
    assert mapping.normalize_team_name("沙 特 阿 拉 伯") == "沙特阿拉伯"
    assert mapping.normalize_team_name("科 特 迪 瓦") == "科特迪瓦"
    assert mapping.normalize_team_name("刚 果（金）") == "刚果(金)"


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


def test_qiumibao_mapping_parser_missing_team_fields_when_all_candidates_empty():
    result = mapping.analyze_external_mapping(
        _local("500-1359182", "加拿大", "波黑"),
        [
            {
                "external_id": "9001",
                "home_team": None,
                "away_team": None,
                "kickoff_at": "2026-06-18T20:00:00+00:00",
                "status": "finished",
                "result_home": 1,
                "result_away": 0,
            }
        ],
    )

    assert result["mapping_status"] == mapping.PARSER_MISSING_TEAM_FIELDS


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


def test_qiumibao_parser_extracts_team_names_from_common_fields():
    payload = {
        "list": [
            {"id": "1", "homeName": "Canada", "awayName": "Bosnia", "state": 3, "home_score": "1", "away_score": "1"},
            {"id": "2", "hteam": "Mexico", "ateam": "South Africa", "state": 3, "score1": "2", "score2": "0"},
            {"id": "3", "hn": "South Korea", "an": "Czech Republic", "state": 3, "left_score": "2", "right_score": "1"},
        ]
    }

    rows = probe.qiumibao.normalize_score_payload(payload)

    assert rows[0].home_team == "Canada"
    assert rows[0].away_team == "Bosnia"
    assert rows[1].home_team == "Mexico"
    assert rows[1].away_team == "South Africa"
    assert rows[2].home_team == "South Korea"
    assert rows[2].away_team == "Czech Republic"


def test_qiumibao_parser_extracts_team_names_from_nested_fields():
    payload = {
        "list": [
            {
                "id": "1",
                "teams": {"home": {"name": "Canada"}, "away": {"name": "Bosnia"}},
                "state": "完赛",
                "home_score": "1",
                "away_score": "1",
            },
            {
                "id": "2",
                "home": {"name": "Mexico"},
                "away": {"name": "South Africa"},
                "state": "完赛",
                "home_score": "2",
                "away_score": "0",
            },
        ]
    }

    rows = probe.qiumibao.normalize_score_payload(payload)

    assert rows[0].home_team == "Canada"
    assert rows[0].away_team == "Bosnia"
    assert rows[1].home_team == "Mexico"
    assert rows[1].away_team == "South Africa"


def test_qiumibao_parser_preserves_row_with_missing_team_fields_for_diagnostics():
    payload = {"list": [{"id": "1", "left": {"score": "1"}, "right": {"score": "0"}, "state": 3}]}

    rows = probe.qiumibao.normalize_score_payload(payload)

    assert rows[0].external_id == "1"
    assert rows[0].home_team is None
    assert rows[0].away_team is None
    assert rows[0].result_home == 1
    assert rows[0].result_away == 0


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
