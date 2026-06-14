from pathlib import Path
from datetime import datetime, timezone

import pytest

from api import ops_log
from api import results_sync
from api.results_sync import ParsedResult, parse_results_html, run_results_sync_job, sync_results


class FakeResultsRepository:
    def __init__(self):
        self.matches = {
            "500-1001": {"match_id": "500-1001", "home_team": "A", "away_team": "B", "status": "scheduled", "result_home": None},
            "500-1003": {"match_id": "500-1003", "home_team": "E", "away_team": "F", "status": "scheduled", "result_home": None},
            "500-1004": {"match_id": "500-1004", "home_team": "G", "away_team": "H", "status": "scheduled", "result_home": None},
        }

    def update_finished(self, result: ParsedResult):
        if result.match_id not in self.matches:
            return False
        row = self.matches[result.match_id]
        row.update(
            {
                "result_home": result.result_home,
                "result_away": result.result_away,
                "ht_home": result.ht_home,
                "ht_away": result.ht_away,
                "status": "finished",
            }
        )

    def update_postponed(self, result: ParsedResult):
        if result.match_id not in self.matches:
            return False
        self.matches[result.match_id]["status"] = "postponed"
        return True


def test_parse_500_results_fixture_covers_finished_half_time_and_postponed():
    html = Path("tests/fixtures/500_results_finished_sample.html").read_text(encoding="utf-8")

    results = parse_results_html(html)

    by_id = {item.match_id: item for item in results}
    assert by_id["500-1001"].status == "finished"
    assert by_id["500-1001"].result_home == 2
    assert by_id["500-1001"].result_away == 1
    assert by_id["500-1001"].ht_home == 1
    assert by_id["500-1001"].ht_away == 0
    assert by_id["500-1002"].status == "scheduled"
    assert by_id["500-1003"].status == "postponed"
    assert by_id["500-1004"].status == "postponed"


def test_sync_results_updates_result_fields_without_destroying_match_metadata():
    html = Path("tests/fixtures/500_results_finished_sample.html").read_text(encoding="utf-8")
    repo = FakeResultsRepository()

    stats = sync_results(parse_results_html(html), repo)

    assert stats.matches_seen == 4
    assert stats.finished_updated == 1
    assert stats.halftime_updated == 1
    assert stats.postponed_updated == 2
    assert stats.skipped == 1
    finished = repo.matches["500-1001"]
    assert finished["home_team"] == "A"
    assert finished["away_team"] == "B"
    assert finished["result_home"] == 2
    assert finished["result_away"] == 1
    assert finished["ht_home"] == 1
    assert finished["ht_away"] == 0
    assert repo.matches["500-1003"]["status"] == "postponed"
    assert repo.matches["500-1004"]["status"] == "postponed"


def test_sync_results_reports_skipped_reasons():
    repo = FakeResultsRepository()
    results = [
        ParsedResult("500-1001", "scheduled"),
        ParsedResult("500-1002", "finished"),
        ParsedResult("500-9999", "finished", 1, 0),
    ]

    stats = sync_results(results, repo)

    assert stats.skipped == 3
    assert stats.skipped_reasons == {
        "not_finished_status": 1,
        "missing_result_score": 1,
        "match_id_not_found": 1,
    }


def test_half_time_missing_is_not_inferred_from_full_time_score():
    html = """
    <table>
      <tr data-match-id="500-2001" data-status="finished" data-score="3-2">
        <td>A</td><td>B</td><td>3-2</td>
      </tr>
    </table>
    """

    result = parse_results_html(html)[0]

    assert result.result_home == 3
    assert result.result_away == 2
    assert result.ht_home is None
    assert result.ht_away is None


def test_source_fetch_error_records_diagnostic_summary(monkeypatch):
    recorded = []

    def fail_fetch():
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(results_sync, "fetch_results_html", fail_fetch)
    monkeypatch.setattr(results_sync, "record_ops_log", lambda *args: recorded.append(args))

    with pytest.raises(RuntimeError):
        run_results_sync_job(record_log=True)

    assert recorded
    assert recorded[0][0] == "results_sync"
    assert recorded[0][1] == "error"
    assert recorded[0][3]["source_name"] == "500_trade_jczq"
    assert recorded[0][3]["source_fetch_ok"] is False


def test_results_sync_record_log_tolerates_datetime_summary(monkeypatch):
    html = """
    <table>
      <tr data-match-id="500-1001" data-status="finished" data-score="2-1"></tr>
    </table>
    """
    recorded = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            recorded.append((sql, params))
            assert params[4].obj["overdue_closed_matches"][0]["kickoff_at"] == "2026-06-14T12:00:00+00:00"

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    class FakeRepository(FakeResultsRepository):
        pass

    monkeypatch.setattr(results_sync, "fetch_results_html", lambda: html)
    monkeypatch.setattr(results_sync, "PostgresResultsRepository", FakeRepository)
    monkeypatch.setattr(
        results_sync,
        "_diagnose_overdue_closed_matches",
        lambda parsed: [{"match_id": "500-1001", "kickoff_at": datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)}],
    )
    monkeypatch.setattr(ops_log, "connect", lambda: FakeConn())
    monkeypatch.setattr(results_sync, "record_ops_log", ops_log.record_ops_log)

    stats = run_results_sync_job(record_log=True)

    assert stats.finished_updated == 1
    assert recorded
