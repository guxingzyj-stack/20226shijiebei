from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api import result_ingest_monitor


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _row(match_id: str, minutes_from_now: int, status: str, result_home=None, result_away=None) -> dict:
    return {
        "match_id": match_id,
        "match_num": "TEST001",
        "home_team": "主队",
        "away_team": "客队",
        "kickoff_at": NOW + timedelta(minutes=minutes_from_now),
        "status": status,
        "result_home": result_home,
        "result_away": result_away,
        "ht_home": None,
        "ht_away": None,
        "created_at": None,
        "updated_at": None,
    }


def _observation(match_id: str, audit_status: str, result_state: str, minutes: int, delay=None, consistency=True) -> dict:
    estimated = NOW - timedelta(minutes=minutes) + timedelta(minutes=120)
    return {
        "observed_at": NOW,
        "match_id": match_id,
        "home_team": "主队",
        "away_team": "客队",
        "kickoff_at": NOW - timedelta(minutes=minutes),
        "estimated_fulltime_at": estimated,
        "status": "finished" if result_state == "result_present" else "closed",
        "result_home": 1 if result_state == "result_present" else None,
        "result_away": 0 if result_state == "result_present" else None,
        "first_result_seen_at": estimated + timedelta(minutes=delay) if delay is not None else None,
        "result_ingest_delay_minutes": delay,
        "result_state": result_state,
        "audit_status": audit_status,
        "minutes_since_kickoff": minutes,
        "scheduler_stale": False,
        "result_consistency_pass": consistency,
    }


def test_build_observation_records_sets_first_seen_only_after_missing_baseline_stays_unknown() -> None:
    prior_seen = NOW - timedelta(minutes=5)
    records = result_ingest_monitor.build_observation_records(
        [
            _row("500-1", -180, "finished", 2, 1),
            _row("500-2", -60, "closed"),
            _row("500-3", -180, "finished", 2, 1),
        ],
        now=NOW,
        results_sync={
            "latest_run_at": NOW.isoformat(),
            "status": "ok",
            "source": "500_trade_jczq",
            "finished_updated": 1,
            "skipped": 0,
            "skipped_reasons": {},
            "source_fetch_ok": True,
            "parser_error": None,
        },
        coverage_summary={"closed_missing_count": 1, "overdue_count": 0},
        consistency={"result": "PASS"},
        scheduler={"scheduler_stale": False},
        first_seen_lookup=lambda match_id: prior_seen if match_id == "500-1" else None,
        has_missing_before_lookup=lambda match_id: match_id == "500-1",
    )

    assert records[0]["first_result_seen_at"] == prior_seen
    assert records[0]["result_ingest_delay_minutes"] == 55
    assert records[1]["first_result_seen_at"] is None
    assert records[1]["result_ingest_delay_minutes"] is None
    assert records[2]["first_result_seen_at"] is None
    assert records[2]["result_ingest_delay_minutes"] is None
    assert records[2]["notes"] == "baseline_result_present"
    assert all(record["is_test_match"] is False for record in records)


def test_run_once_appends_observations_without_business_table_writer(monkeypatch) -> None:
    inserted = []

    class FakeConnect:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(result_ingest_monitor, "connect", lambda: FakeConnect())
    monkeypatch.setattr(result_ingest_monitor, "_load_monitor_matches", lambda conn, now, window_hours: [_row("500-1", -180, "finished", 2, 1)])
    monkeypatch.setattr(result_ingest_monitor, "_latest_results_sync_rows", lambda conn: [])
    monkeypatch.setattr(result_ingest_monitor, "_first_result_seen_at", lambda conn, match_id: None)
    monkeypatch.setattr(result_ingest_monitor, "_has_missing_before_result", lambda conn, match_id: False)
    monkeypatch.setattr(result_ingest_monitor, "_insert_observations", lambda conn, records: inserted.extend(records) or len(records))
    monkeypatch.setattr(result_ingest_monitor, "generate_consistency_report", lambda: {"result": "PASS"})
    monkeypatch.setattr(result_ingest_monitor, "scheduler_freshness", lambda: {"scheduler_stale": False})
    monkeypatch.setattr(result_ingest_monitor, "record_ops_log", lambda *args, **kwargs: None)

    report = result_ingest_monitor.run_once(source="500", window_hours=36)

    assert report["ok"] is True
    assert report["writes_business_tables"] is False
    assert report["observed_matches"] == 1
    assert inserted[0]["match_id"] == "500-1"


def test_summary_health_states() -> None:
    healthy = result_ingest_monitor.summarize_observations(
        [
            _observation("m1", "MISSING_RESULT_OVERDUE", "result_missing", 180),
            _observation("m1", "OK_RESULT_PRESENT", "result_present", 180, delay=45),
        ]
    )
    observe = result_ingest_monitor.summarize_observations([_observation("m1", "WAIT_RECENTLY_STARTED", "result_missing", 190)])
    action = result_ingest_monitor.summarize_observations([_observation("m1", "MISSING_RESULT_OVERDUE", "result_missing", 250)])
    inconsistent = result_ingest_monitor.summarize_observations(
        [_observation("m1", "NON_FINISHED_HAS_RESULT_ERROR", "result_present", 180, delay=10, consistency=False)]
    )

    assert healthy["result"] == "RESULT_INGEST_HEALTHY"
    assert observe["result"] == "RESULT_INGEST_SLOW_OBSERVE"
    assert action["result"] == "RESULT_INGEST_SLOW_NEEDS_ACTION"
    assert inconsistent["result"] == "RESULT_INGEST_INCONSISTENT"


def test_baseline_result_present_is_not_counted_as_true_delay_or_slow_action() -> None:
    report = result_ingest_monitor.summarize_observations(
        [
            _observation("m1", "OK_RESULT_PRESENT", "result_present", 2200, delay=2080),
            _observation("m2", "OK_RESULT_PRESENT", "result_present", 1300, delay=1180),
        ]
    )

    assert report["summary"]["baseline_result_present_matches"] == 2
    assert report["summary"]["true_delay_measured_matches"] == 0
    assert report["summary"]["delay_unknown_matches"] == 2
    assert report["summary"]["median_ingest_delay_minutes"] is None
    assert report["summary"]["max_ingest_delay_minutes"] is None
    assert report["result"] == "RESULT_INGEST_BASELINE_ONLY"


def test_missing_to_present_transition_counts_as_true_delay() -> None:
    report = result_ingest_monitor.summarize_observations(
        [
            _observation("m1", "MISSING_RESULT_OVERDUE", "result_missing", 250),
            _observation("m1", "OK_RESULT_PRESENT", "result_present", 250, delay=130),
        ]
    )

    assert report["summary"]["baseline_result_present_matches"] == 0
    assert report["summary"]["true_delay_measured_matches"] == 1
    assert report["summary"]["delay_unknown_matches"] == 0
    assert report["summary"]["median_ingest_delay_minutes"] == 130
    assert report["summary"]["max_ingest_delay_minutes"] == 130
    assert report["result"] == "RESULT_INGEST_SLOW_NEEDS_ACTION"


def test_summary_outputs_delay_precision_note_and_minutes(monkeypatch) -> None:
    monkeypatch.setenv("RESULT_INGEST_MONITOR_INTERVAL_MINUTES", "30")

    report = result_ingest_monitor.summarize_observations([_observation("m1", "OK_RESULT_PRESENT", "result_present", 180)])

    assert "kickoff_at + 120min" in report["summary"]["delay_precision_note"]
    assert report["summary"]["delay_precision_minutes"] == 30


def test_monitor_scheduler_env_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_RESULT_INGEST_MONITOR", raising=False)
    monkeypatch.delenv("RESULT_INGEST_MONITOR_INTERVAL_MINUTES", raising=False)

    assert result_ingest_monitor.monitor_enabled() is False
    assert result_ingest_monitor.monitor_interval_minutes() == 30
