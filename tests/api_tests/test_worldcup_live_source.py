from __future__ import annotations

from datetime import datetime, timezone

from api.sources import qiumibao, zhibo8
from api.result_source_mapping import normalize_team_name
from api.worldcup_live_source import (
    _compare_local_to_live,
    _map_one_local,
    _events_for_match,
    build_worldcup_live_matches,
    fetch_worldcup_live_report,
    score_live_to_local_match,
)


def test_zhibo8_worldcup_schedule_parser_extracts_match():
    html = """
    <li label="世界杯" data-type="football" data-time="2026-06-13 03:00">
      <a href="/zhibo/zuqiu/2026.html"><b id="saishi1359182">
        <span class="_league">世界杯</span>
        <span class="_teams">德国 <img src="x.png"> 2 - 1 <img src="y.png"> 加拿大</span></b>
      </a>
    </li>
    """

    matches = zhibo8.parse_worldcup_matches(html)

    assert len(matches) == 1
    assert matches[0].zhibo8_match_ref == "1359182"
    assert matches[0].home_team == "德国"
    assert matches[0].away_team == "加拿大"
    assert matches[0].score == "2-1"
    assert matches[0].kickoff_at == "2026-06-12T19:00:00+00:00"


def test_zhibo8_homepage_report_surfaces_parser_error_for_empty_page():
    report = zhibo8.homepage_source_report(fetcher=lambda: "<html></html>")

    assert report["source_fetch_ok"] is True
    assert report["parser_error"]
    assert report["matches"] == []


def test_qiumibao_score_parser_keeps_ids_period_and_half_score():
    payload = {
        "list": [
            {
                "id": 123,
                "code": "worldcup",
                "start_time": 1781377200,
                "period_cn": "完赛",
                "left": {"id": 10, "name": "德国", "score": 2},
                "right": {"id": 20, "name": "加拿大", "score": 1},
                "score_msg": ["半场 1-0"],
            }
        ]
    }

    match = qiumibao.normalize_score_payload(payload)[0]

    assert match.external_id == "123"
    assert match.left_id == "10"
    assert match.right_id == "20"
    assert match.period_cn == "完赛"
    assert match.result_home == 2
    assert match.result_away == 1
    assert match.ht_home == 1
    assert match.ht_away == 0


def test_qiumibao_score_parser_tolerates_missing_team_names():
    match = qiumibao.normalize_score_payload({"list": [{"id": "abc", "period_cn": "未赛"}]})[0]

    assert match.external_id == "abc"
    assert match.home_team is None
    assert match.away_team is None
    assert match.status == "scheduled"


def test_events_for_match_without_match_id_does_not_request_events():
    called = False

    def fetch_events(date, match_id):
        nonlocal called
        called = True
        return {"source_fetch_ok": True, "events": []}

    assert _events_for_match(None, {"kickoff_at": "2026-06-12T19:00:00+00:00"}, fetch_events, include_events=True) == []
    assert called is False


def test_events_source_report_uses_date_and_match_id():
    seen = {}

    def fetcher(date, match_id):
        seen["date"] = date
        seen["match_id"] = match_id
        return {"data": [{"time": "34", "event_code_cn": "进球", "player_name_cn": "A", "score": "1-0"}]}

    report = qiumibao.events_source_report("2026-06-12", "123", fetcher=fetcher)

    assert seen == {"date": "2026-06-12", "match_id": "123"}
    assert report["source_fetch_ok"] is True
    assert report["events"][0]["score_after_event"] == "1-0"


def test_worldcup_live_merge_uses_zhibo8_and_qiumibao_ids():
    zhibo8_rows = [
        {
            "zhibo8_match_ref": "123",
            "zhibo8_url": "https://example.test/match",
            "home_team": "德国",
            "away_team": "加拿大",
            "kickoff_at": "2026-06-12T19:00:00+00:00",
        }
    ]
    qiumibao_rows = [
        {
            "external_id": "123",
            "home_team": "德国",
            "away_team": "加拿大",
            "kickoff_at": "2026-06-12T19:00:00+00:00",
            "status": "finished",
            "result_home": 2,
            "result_away": 1,
            "ht_home": 1,
            "ht_away": 0,
            "left_id": "10",
            "right_id": "20",
            "period_cn": "完赛",
        }
    ]

    merged = build_worldcup_live_matches(zhibo8_rows, qiumibao_rows)

    assert len(merged) == 1
    assert merged[0].mapping_status == "matched"
    assert merged[0].qiumibao_match_id == "123"
    assert merged[0].qiumibao_left_id == "10"
    assert merged[0].score == "2-1"
    assert merged[0].half_score == "1-0"


def test_local_compare_statuses_ok_fallback_and_conflict():
    local = {
        "match_id": "500-1",
        "home_team": "德国",
        "away_team": "加拿大",
        "kickoff_at": datetime(2026, 6, 12, 19, 0, tzinfo=timezone.utc),
        "result_home": 2,
        "result_away": 1,
    }
    live = {
        "home_team": "德国",
        "away_team": "加拿大",
        "kickoff_at": "2026-06-12T19:00:00+00:00",
        "status": "finished",
        "score": "2-1",
    }
    assert _compare_local_to_live(local, [live])["comparison_status"] == "OK_MATCH"

    local_missing = {**local, "result_home": None, "result_away": None}
    assert _compare_local_to_live(local_missing, [live])["comparison_status"] == "NEEDS_VERIFIED_FALLBACK"

    conflict_live = {**live, "score": "1-2"}
    assert _compare_local_to_live(local, [conflict_live])["comparison_status"] == "CONFLICT_NEEDS_REVIEW"


def test_fetch_worldcup_live_report_is_dry_run_and_writes_nothing():
    report = fetch_worldcup_live_report(
        fetch_zhibo8=lambda: {
            "source_fetch_ok": True,
            "parser_error": None,
            "matches": [
                {
                    "zhibo8_match_ref": "123",
                    "home_team": "德国",
                    "away_team": "加拿大",
                    "kickoff_at": "2026-06-12T19:00:00+00:00",
                }
            ],
        },
        fetch_qiumibao=lambda date=None: {
            "source_fetch_ok": True,
            "parser_error": None,
            "matches": [
                {
                    "external_id": "123",
                    "home_team": "德国",
                    "away_team": "加拿大",
                    "kickoff_at": "2026-06-12T19:00:00+00:00",
                    "status": "scheduled",
                }
            ],
        },
    )

    assert report["mode"] == "dry-run"
    assert report["writes_db"] is False
    assert report["source_fetch_ok"] is True
    assert report["merged_matches_count"] == 1


def test_normalize_team_name_removes_chinese_inner_spaces_and_aliases():
    assert normalize_team_name("\u7f8e \u56fd") == "\u7f8e\u56fd"
    assert normalize_team_name("\u5df4 \u62c9 \u572d") == "\u5df4\u62c9\u572d"
    assert normalize_team_name("\u52a0 \u62ff \u5927") == "\u52a0\u62ff\u5927"
    assert normalize_team_name("\u5361 \u5854 \u5c14") == "\u5361\u5854\u5c14"
    assert normalize_team_name("\u6fb3 \u5927 \u5229 \u4e9a") == "\u6fb3\u5927\u5229\u4e9a"
    assert normalize_team_name("\u58a8 \u897f \u54e5") == "\u58a8\u897f\u54e5"
    assert normalize_team_name("USA") == "\u7f8e\u56fd"
    assert normalize_team_name("Brazil") == "\u5df4\u897f"
    assert normalize_team_name("Qatar") == "\u5361\u5854\u5c14"
    assert normalize_team_name("Switzerland") == "\u745e\u58eb"


def test_live_to_local_score_matched_high_confidence():
    local = _local("\u7f8e \u56fd", "\u5df4 \u62c9 \u572d", "2026-06-13T01:00:00+00:00")
    live = _live("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")

    candidate = score_live_to_local_match(live, local)

    assert candidate.mapping_status == "matched"
    assert candidate.confidence == "high"
    assert candidate.match_score >= 0.9


def test_live_to_local_score_team_match_but_kickoff_mismatch():
    local = _local("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")
    live = _live("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T06:00:00+00:00")

    candidate = score_live_to_local_match(live, local)

    assert candidate.mapping_status == "kickoff_time_mismatch"


def test_live_to_local_score_time_match_but_team_mismatch():
    local = _local("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")
    live = _live("\u5fb7\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")

    candidate = score_live_to_local_match(live, local)

    assert candidate.mapping_status == "team_name_mismatch"


def test_map_one_local_detects_ambiguous_candidates():
    local = _local("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")
    live_matches = [
        _live("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00", ref="111"),
        _live("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:01:00+00:00", ref="222"),
    ]

    row = _map_one_local(local, live_matches)

    assert row["mapping_status"] == "ambiguous_candidates"
    assert row["comparison_status"] == "AMBIGUOUS_CANDIDATES"


def test_map_one_local_comparison_statuses():
    local_missing = _local("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")
    live_finished = _live("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00", score="4-1", status="finished")
    assert _map_one_local(local_missing, [live_finished])["comparison_status"] == "NEEDS_VERIFIED_FALLBACK"

    local_same = {**local_missing, "result_home": 4, "result_away": 1}
    assert _map_one_local(local_same, [live_finished])["comparison_status"] == "OK_MATCH"

    local_conflict = {**local_missing, "result_home": 1, "result_away": 4}
    assert _map_one_local(local_conflict, [live_finished])["comparison_status"] == "CONFLICT_NEEDS_REVIEW"


def test_map_one_local_is_dry_run_shape():
    local = _local("\u7f8e\u56fd", "\u5df4\u62c9\u572d", "2026-06-13T01:00:00+00:00")
    row = _map_one_local(local, [])

    assert row["mapping_status"] == "source_window_missing"
    assert row["local_match"]["normalized_home_team"] == "\u7f8e\u56fd"


def test_zhibo8_parser_outputs_raw_links_and_possible_qiumibao_ids():
    html = """
    <li label="\u4e16\u754c\u676f" data-type="football" data-time="2026-06-13 03:00">
      <a href="/zhibo/zuqiu/1869145.html"><b id="saishi1869145">
        <span class="_league">\u4e16\u754c\u676f</span>
        <span class="_teams">Qatar <img src="x.png"> VS <img src="y.png"> Switzerland</span></b>
      </a>
      <a href="https://dc4pc.qiumibao.com/dc/matchs/data/2026-06-13/match_event_999001.htm">event</a>
    </li>
    """

    match = zhibo8.parse_worldcup_matches(html)[0]

    assert match.zhibo8_raw_links
    assert "1869145" in match.possible_qiumibao_ids
    assert "999001" in match.possible_qiumibao_ids
    assert match.normalized_home_team == "\u5361\u5854\u5c14"
    assert match.normalized_away_team == "\u745e\u58eb"


def test_zhibo8_link_id_can_bind_to_qiumibao_score_id():
    zhibo8_rows = [
        {
            "zhibo8_match_ref": "111",
            "zhibo8_url": "https://example.test/111",
            "possible_qiumibao_ids": ["999001"],
            "home_team": "\u5361\u5854\u5c14",
            "away_team": "\u745e\u58eb",
            "kickoff_at": "2026-06-13T19:00:00+00:00",
        }
    ]
    qiumibao_rows = [
        {
            "external_id": "999001",
            "home_team": "\u5361\u5854\u5c14",
            "away_team": "\u745e\u58eb",
            "kickoff_at": "2026-06-13T19:00:00+00:00",
            "status": "scheduled",
        }
    ]

    merged = build_worldcup_live_matches(zhibo8_rows, qiumibao_rows)

    assert merged[0].qiumibao_match_id == "999001"
    assert merged[0].qiumibao_link_status == "qiumibao_linked"


def test_zhibo8_matched_but_qiumibao_unlinked_status_is_reported():
    local = _local("\u5361 \u5854 \u5c14", "\u745e \u58eb", "2026-06-13T19:00:00+00:00")
    live = {
        "home_team": "\u5361\u5854\u5c14",
        "away_team": "\u745e\u58eb",
        "kickoff_at": "2026-06-13T19:00:00+00:00",
        "status": "scheduled",
        "score": None,
        "half_score": None,
        "zhibo8_match_ref": "1869145",
        "qiumibao_match_id": None,
        "possible_qiumibao_ids": ["1869145"],
    }

    row = _map_one_local(local, [live])

    assert row["mapping_status"] == "matched"
    assert row["comparison_status"] == "WAIT_SOURCE"
    assert row["qiumibao_link_status"] == "zhibo8_matched_but_qiumibao_unlinked"
    assert row["next_step"] == "EXTRACT_QIUMIBAO_ID_FROM_ZHIBO8_LINKS"


def _local(home: str, away: str, kickoff_at: str) -> dict:
    return {
        "match_id": "500-1359189",
        "match_num": "\u5468\u4e94005",
        "league": "\u4e16\u754c\u676f",
        "home_team": home,
        "away_team": away,
        "kickoff_at": kickoff_at,
        "status": "closed",
        "result_home": None,
        "result_away": None,
    }


def _live(home: str, away: str, kickoff_at: str, score: str | None = None, status: str = "scheduled", ref: str = "1359189") -> dict:
    result_home = result_away = None
    if score:
        result_home, result_away = [int(part) for part in score.split("-", 1)]
    return {
        "home_team": home,
        "away_team": away,
        "kickoff_at": kickoff_at,
        "status": status,
        "score": score,
        "half_score": None,
        "result_home": result_home,
        "result_away": result_away,
        "zhibo8_match_ref": ref,
        "qiumibao_match_id": ref,
    }
