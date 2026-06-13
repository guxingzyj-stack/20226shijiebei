from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.result_source_coverage_audit import (
    build_coverage_report,
    build_half_time_probe,
    classify_match,
    summarize_results_sync_ops,
)


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _row(
    match_id: str,
    minutes_from_now: int,
    status: str,
    result_home: int | None = None,
    result_away: int | None = None,
    ht_home: int | None = None,
    ht_away: int | None = None,
) -> dict:
    return {
        "match_id": match_id,
        "match_num": "周六001",
        "home_team": "主队",
        "away_team": "客队",
        "kickoff_at": NOW + timedelta(minutes=minutes_from_now),
        "status": status,
        "result_home": result_home,
        "result_away": result_away,
        "ht_home": ht_home,
        "ht_away": ht_away,
        "created_at": None,
        "updated_at": None,
    }


def test_classify_match_statuses() -> None:
    assert classify_match(_row("future", 30, "scheduled"), now=NOW)["audit_status"] == "WAIT_NOT_STARTED"
    assert classify_match(_row("recent", -60, "closed"), now=NOW)["audit_status"] == "WAIT_RECENTLY_STARTED"
    assert classify_match(_row("overdue", -180, "closed"), now=NOW)["audit_status"] == "MISSING_RESULT_OVERDUE"
    assert classify_match(_row("ok", -180, "finished", 2, 1), now=NOW)["audit_status"] == "OK_RESULT_PRESENT"
    assert classify_match(_row("bad-finished", -180, "finished"), now=NOW)["audit_status"] == "FINISHED_NULL_ERROR"
    assert (
        classify_match(_row("bad-open", -180, "closed", 1, 0), now=NOW)["audit_status"]
        == "NON_FINISHED_HAS_RESULT_ERROR"
    )


def test_build_coverage_report_counts_started_and_missing_results() -> None:
    rows = [
        _row("future", 30, "scheduled"),
        _row("recent", -60, "closed"),
        _row("overdue", -180, "closed"),
        _row("finished", -180, "finished", 2, 1),
        _row("finished-null", -180, "finished"),
        _row("closed-with-result", -180, "closed", 1, 0),
    ]
    report = build_coverage_report(rows, now=NOW, ops_rows=[], scope="test")

    assert report["writes_db"] is False
    assert report["summary"]["total_matches"] == 6
    assert report["summary"]["started_matches"] == 5
    assert report["summary"]["started_with_result"] == 2
    assert report["summary"]["started_missing_result"] == 3
    assert report["summary"]["closed_missing_count"] == 2
    assert report["summary"]["finished_with_result_count"] == 1
    assert report["summary"]["finished_missing_count"] == 1
    assert report["summary"]["non_finished_with_result_count"] == 1
    assert report["summary"]["ready_for_settlement_count"] == 1
    assert report["summary"]["overdue_count"] == 1
    assert report["conclusion"] == "500_RESULT_SOURCE_PARTIAL"


def test_results_sync_ops_summary_keeps_parser_error() -> None:
    rows = [
        {
            "status": "error",
            "started_at": NOW,
            "summary": {
                "source_name": "500_trade_jczq",
                "source_fetch_ok": False,
                "finished_updated": 0,
                "skipped": 3,
                "skipped_reasons": {"missing_result_score": 3},
            },
            "error": "ParserError",
        }
    ]

    summary = summarize_results_sync_ops(rows)

    assert summary["latest_run_at"] == NOW.isoformat()
    assert summary["source"] == "500_trade_jczq"
    assert summary["status"] == "error"
    assert summary["finished_updated"] == 0
    assert summary["skipped"] == 3
    assert summary["skipped_reasons"] == {"missing_result_score": 3}
    assert summary["source_fetch_ok"] is False
    assert summary["parser_error"] == "ParserError"


def test_half_time_probe_detects_parser_half_time_and_db_coverage() -> None:
    html = """
    <table>
      <tr data-match-id="500-1" data-status="finished" data-score="2-1" data-half-score="1-0"></tr>
    </table>
    """
    rows = [_row("500-1", -180, "finished", 2, 1, 1, 0)]

    probe = build_half_time_probe(rows, html=html)

    assert probe["writes_db"] is False
    assert probe["source_fetch_ok"] is True
    assert probe["raw_field_candidates"]["data-half-score"] == 1
    assert probe["parser_extracts_half_time"] is True
    assert probe["db_ht_coverage"]["finished_matches"] == 1
    assert probe["db_ht_coverage"]["finished_with_ht"] == 1
    assert probe["db_ht_coverage"]["finished_missing_ht"] == 0
    assert probe["conclusion"] == "HT_COVERAGE_OK"


def test_half_time_probe_reports_source_unavailable_without_half_fields() -> None:
    html = '<table><tr data-match-id="500-1" data-status="finished" data-score="2-1"></tr></table>'
    rows = [_row("500-1", -180, "finished", 2, 1)]

    probe = build_half_time_probe(rows, html=html)

    assert probe["writes_db"] is False
    assert probe["raw_field_candidates"] == {}
    assert probe["parser_extracts_half_time"] is False
    assert probe["db_ht_coverage"]["finished_missing_ht"] == 1
    assert probe["conclusion"] == "HT_SOURCE_UNAVAILABLE"


def test_all_audit_reports_are_dry_run() -> None:
    report = build_coverage_report([_row("future", 30, "scheduled")], now=NOW, include_half_time_probe=True, html="")

    assert report["mode"] == "dry-run"
    assert report["writes_db"] is False
    assert report["half_time_probe"]["writes_db"] is False
