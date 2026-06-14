from __future__ import annotations

from pathlib import Path

from api import external_result_sources as sources
from api.result_source_mapping import normalize_team_name


def test_thesportsdb_parser_reads_finished_score_and_teams():
    event = sources.parse_thesportsdb_event(
        {
            "idEvent": "tsdb-1",
            "strHomeTeam": "Qatar",
            "strAwayTeam": "Switzerland",
            "dateEvent": "2026-06-14",
            "strTime": "12:00:00",
            "strStatus": "Match Finished",
            "intHomeScore": "1",
            "intAwayScore": "2",
        },
        source_url="https://www.thesportsdb.com/api/test",
    )

    assert event is not None
    assert event.status == "finished"
    assert event.result_home == 1
    assert event.result_away == 2
    assert event.home_team == "卡塔尔"
    assert event.away_team == "瑞士"


def test_thesportsdb_pair_marks_delayed_free_tier():
    historical = {"source_fetch_ok": True, "events_seen": 10, "target_matches_seen": 1}
    current = {"source_fetch_ok": True, "events_seen": 0, "target_matches_seen": 0}

    assert sources.classify_thesportsdb_date_pair(historical, current) == "THESPORTSDB_DELAYED_FREE_TIER"


def test_fifa_parser_reads_finished_score():
    row = {
        "project_match_id": "500-1359227",
        "fifa_match_url": "https://www.fifa.com/match/1",
        "home_team": "Qatar",
        "away_team": "Switzerland",
        "kickoff_at": "2026-06-14T12:00:00Z",
        "status": "finished",
    }
    event = sources.parse_fifa_event(row, '{"homeScore":1,"awayScore":2,"status":"finished"}', row["fifa_match_url"])

    assert event.status == "finished"
    assert event.result_home == 1
    assert event.result_away == 2
    assert event.home_team == "卡塔尔"
    assert event.away_team == "瑞士"


def test_english_team_aliases_normalize_to_local_names():
    assert normalize_team_name("Qatar") == "卡塔尔"
    assert normalize_team_name("Switzerland") == "瑞士"
    assert normalize_team_name("Brazil") == "巴西"
    assert normalize_team_name("Morocco") == "摩洛哥"
    assert normalize_team_name("Korea Republic") == "韩国"
    assert normalize_team_name("United States") == "美国"
    assert normalize_team_name("USMNT") == "美国"
    assert normalize_team_name("IR Iran") == "伊朗"
    assert normalize_team_name("Côte d'Ivoire") == "科特迪瓦"
    assert normalize_team_name("DR Congo") == "刚果(金)"
    assert normalize_team_name("Cape Verde") == "佛得角"


def test_fifa_source_without_targets_reports_mapping_missing(tmp_path: Path):
    missing = tmp_path / "missing.csv"

    report = sources.fetch_fifa_events("2026-06-14", targets_csv=missing)

    assert report["source_fetch_ok"] is True
    assert report["events_seen"] == 0
    assert report["parser_error"] == "missing_fifa_match_url_mapping"
