from __future__ import annotations

from datetime import datetime, timezone
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


def test_espn_parser_reads_final_event_and_score():
    event = sources.parse_espn_event(
        {
            "id": "espn-1",
            "date": "2026-06-14T01:00Z",
            "status": {"type": {"name": "STATUS_FINAL", "state": "post", "completed": True}},
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "team": {"displayName": "Haiti"}, "score": "0"},
                        {"homeAway": "away", "team": {"displayName": "Scotland"}, "score": "1"},
                    ]
                }
            ],
        },
        source_url="https://site.api.espn.com/test",
    )

    assert event is not None
    assert event.status == "finished"
    assert event.result_home == 0
    assert event.result_away == 1
    assert event.home_team == "海地"
    assert event.away_team == "苏格兰"


def test_espn_parser_keeps_scheduled_event_non_final():
    event = sources.parse_espn_event(
        {
            "id": "espn-2",
            "date": "2026-06-14T17:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre", "completed": False}},
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "team": {"displayName": "Germany"}, "score": ""},
                        {"homeAway": "away", "team": {"displayName": "Curaçao"}, "score": ""},
                    ]
                }
            ],
        },
        source_url="https://site.api.espn.com/test",
    )

    assert event is not None
    assert event.status == "scheduled"
    assert event.result_home is None
    assert event.away_team == "库拉索"


def test_espn_parser_keeps_in_progress_event_non_final():
    event = sources.parse_espn_event(
        {
            "id": "espn-3",
            "date": "2026-06-14T17:00Z",
            "status": {"type": {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}},
            "competitions": [
                {
                    "competitors": [
                        {"homeAway": "home", "team": {"displayName": "Brazil"}, "score": "1"},
                        {"homeAway": "away", "team": {"displayName": "Morocco"}, "score": "1"},
                    ]
                }
            ],
        },
        source_url="https://site.api.espn.com/test",
    )

    assert event is not None
    assert event.status == "live"


def test_espn_scoreboard_dates_for_utc_early_kickoff_include_et_previous_day():
    dates = sources.espn_scoreboard_dates_for_kickoff(datetime(2026, 6, 14, 1, 0, tzinfo=timezone.utc))

    assert "20260613" in dates
    assert "20260614" in dates
    assert dates[0] == "20260613"


def test_espn_multi_date_fetch_dedupes_external_id(monkeypatch):
    def fake_fetch(match_date):
        return {
            "source": "espn",
            "source_fetch_ok": True,
            "source_url": f"https://espn.example/{match_date}",
            "events_seen": 1,
            "events": [
                {
                    "source": "espn",
                    "source_url": f"https://espn.example/{match_date}",
                    "external_id": "760418",
                    "raw_home": "Haiti",
                    "raw_away": "Scotland",
                    "normalized_home": "海地",
                    "normalized_away": "苏格兰",
                    "kickoff_at": "2026-06-14T01:00:00+00:00",
                    "status": "finished",
                    "result_home": 0,
                    "result_away": 1,
                }
            ],
            "parser_error": None,
        }

    monkeypatch.setattr(sources, "fetch_espn_events", fake_fetch)

    report = sources.fetch_espn_events_for_dates(["20260613", "20260614"])

    assert report["events_seen"] == 1
    assert report["events"][0]["external_source_date"] == "20260613"


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
    assert normalize_team_name("Ecuador") == "厄瓜多尔"
    assert normalize_team_name("Sweden") == "瑞典"
    assert normalize_team_name("Tunisia") == "突尼斯"
    assert normalize_team_name("Türkiye") == "土耳其"

def test_espn_0615_and_future_aliases_normalize_to_local_names():
    assert normalize_team_name("Spain") == "\u897f\u73ed\u7259"
    assert normalize_team_name("Belgium") == "\u6bd4\u5229\u65f6"
    assert normalize_team_name("Egypt") == "\u57c3\u53ca"
    assert normalize_team_name("Uruguay") == "\u4e4c\u62c9\u572d"
    assert normalize_team_name("Cape Verde") == "\u4f5b\u5f97\u89d2"
    assert normalize_team_name("Cabo Verde") == "\u4f5b\u5f97\u89d2"
    assert normalize_team_name("Saudi Arabia") == "\u6c99\u7279\u963f\u62c9\u4f2f"
    assert normalize_team_name("Saudi") == "\u6c99\u7279\u963f\u62c9\u4f2f"
    assert normalize_team_name("IR Iran") == "\u4f0a\u6717"
    assert normalize_team_name("Iran") == "\u4f0a\u6717"
    assert normalize_team_name("New Zealand") == "\u65b0\u897f\u5170"
    assert normalize_team_name("France") == "\u6cd5\u56fd"
    assert normalize_team_name("Senegal") == "\u585e\u5185\u52a0\u5c14"
    assert normalize_team_name("Iraq") == "\u4f0a\u62c9\u514b"
    assert normalize_team_name("Norway") == "\u632a\u5a01"
    assert normalize_team_name("Argentina") == "\u963f\u6839\u5ef7"
    assert normalize_team_name("Algeria") == "\u963f\u5c14\u53ca\u5229\u4e9a"
    assert normalize_team_name("Austria") == "\u5965\u5730\u5229"
    assert normalize_team_name("Jordan") == "\u7ea6\u65e6"
    assert normalize_team_name("Portugal") == "\u8461\u8404\u7259"
    assert normalize_team_name("DR Congo") == "\u521a\u679c(\u91d1)"
    assert normalize_team_name("Congo DR") == "\u521a\u679c(\u91d1)"
    assert normalize_team_name("Uzbekistan") == "\u4e4c\u5179\u522b\u514b"
    assert normalize_team_name("Colombia") == "\u54e5\u4f26\u6bd4\u4e9a"
    assert normalize_team_name("England") == "\u82f1\u683c\u5170"
    assert normalize_team_name("Croatia") == "\u514b\u7f57\u5730\u4e9a"
    assert normalize_team_name("Ghana") == "\u52a0\u7eb3"
    assert normalize_team_name("Panama") == "\u5df4\u62ff\u9a6c"
    assert normalize_team_name("Bosnia-Herzegovina") == "\u6ce2\u9ed1"
    assert normalize_team_name("Bosnia and Herzegovina") == "\u6ce2\u9ed1"
    assert normalize_team_name("Bosnia & Herzegovina") == "\u6ce2\u9ed1"
    assert normalize_team_name("BIH") == "\u6ce2\u9ed1"


def test_local_team_names_with_visible_and_invisible_spaces_normalize():
    assert normalize_team_name("\u897f \u73ed \u7259") == "\u897f\u73ed\u7259"
    assert normalize_team_name("\u6c99\u200b \u7279\u3000\u963f \u62c9 \u4f2f") == "\u6c99\u7279\u963f\u62c9\u4f2f"
    assert normalize_team_name("\u521a \u679c (\u91d1 )") == "\u521a\u679c(\u91d1)"


def test_fifa_source_without_targets_reports_mapping_missing(tmp_path: Path):
    missing = tmp_path / "missing.csv"

    report = sources.fetch_fifa_events("2026-06-14", targets_csv=missing)

    assert report["source_fetch_ok"] is True
    assert report["events_seen"] == 0
    assert report["parser_error"] == "missing_fifa_match_url_mapping"


def test_fifa_mapping_missing_counts_target_rows(tmp_path: Path):
    targets = tmp_path / "fifa_match_targets.csv"
    targets.write_text(
        "local_match_id,home_team,away_team,kickoff_at,fifa_url,fifa_match_id,source_status,notes\n"
        "500-1359227,卡塔尔,瑞士,2026-06-14T12:00:00Z,,,missing_url_mapping,\n",
        encoding="utf-8",
    )

    report = sources.fetch_fifa_events("2026-06-14", targets_csv=targets)

    assert report["events_seen"] == 0
    assert report["missing_url_mapping_count"] == 1
    assert report["verified_url_count"] == 0
    assert report["target_details"][0]["local_match_id"] == "500-1359227"


def test_fifa_mapping_fetch_error_does_not_create_event(tmp_path: Path):
    targets = tmp_path / "fifa_match_targets.csv"
    targets.write_text(
        "local_match_id,home_team,away_team,kickoff_at,fifa_url,fifa_match_id,source_status,notes\n"
        "500-1359227,卡塔尔,瑞士,2026-06-14T12:00:00Z,missing-page.html,,candidate,\n",
        encoding="utf-8",
    )

    report = sources.fetch_fifa_events("2026-06-14", targets_csv=targets)

    assert report["events_seen"] == 0
    assert report["verified_url_count"] == 0
    assert report["target_details"][0]["reason"].startswith("fetch_error")


def test_fifa_mapping_verified_url_can_emit_finished_event(tmp_path: Path):
    page = tmp_path / "match.json"
    page.write_text('{"homeScore":1,"awayScore":2,"status":"finished"}', encoding="utf-8")
    targets = tmp_path / "fifa_match_targets.csv"
    targets.write_text(
        "local_match_id,home_team,away_team,kickoff_at,fifa_url,fifa_match_id,source_status,notes\n"
        f"500-1359227,卡塔尔,瑞士,2026-06-14T12:00:00Z,{page},fifa-1,verified_url,\n",
        encoding="utf-8",
    )

    report = sources.fetch_fifa_events("2026-06-14", targets_csv=targets)

    assert report["events_seen"] == 1
    assert report["verified_url_count"] == 1
    assert report["events"][0]["result_home"] == 1
    assert report["target_details"][0]["team_match_status"] == "matched"


def test_fifa_discover_url_reports_wait_without_detected_links(monkeypatch):
    monkeypatch.setattr(sources, "_fetch_text", lambda url: "<html><body>schedule only</body></html>")

    report = sources.discover_fifa_urls("2026-06-14", limit=5)

    assert report["source_fetch_ok"] is True
    assert report["writes_db"] is False
    assert report["discovered_urls"] == []
    assert report["result"] == "WAIT"
