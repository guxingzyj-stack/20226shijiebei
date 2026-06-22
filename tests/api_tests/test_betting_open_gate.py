from __future__ import annotations

import os

from api import betting_open_gate, main


def _base(**overrides):
    data = {
        "scheduler_stale": False,
        "odds_stale": False,
        "finished_null_count": 0,
        "result_overdue_closed_count": 0,
        "non_finished_with_result_count": 0,
        "settlement_runner_error": False,
        "settlement_probe_pass": True,
        "settlement_idempotency_pass": True,
        "leaderboard_safe": True,
        "leaderboard_exposes_internal_id": False,
        "leaderboard_test_user_count": 0,
        "two_matchdays_auto_result_sync": True,
        "betting_enabled": False,
        "p1c_prime_ready": True,
        "p3_status": "SHADOW",
    }
    data.update(overrides)
    return data


def test_gate_ready_when_all_conditions_pass():
    report = betting_open_gate.evaluate_gate(**_base())

    assert report["status"] == "READY"
    assert report["betting_open_gate_status"] == "READY"
    assert report["recommend_open_betting"] is True
    assert report["blockers"] == []


def test_gate_waits_without_two_matchdays_auto_result_sync():
    report = betting_open_gate.evaluate_gate(**_base(two_matchdays_auto_result_sync=False))

    assert report["status"] == "WAIT"
    assert report["recommend_open_betting"] is False
    assert "need_two_matchdays_auto_result_sync" in report["blockers"]


def test_p1c_and_p3_wait_are_warnings_not_blockers():
    report = betting_open_gate.evaluate_gate(**_base(p1c_prime_ready=False, p3_status="WAIT"))

    assert report["status"] == "READY"
    assert "p1c_prime_insufficient_samples" in report["warnings"]
    assert "p3_wait" in report["warnings"]


def test_scheduler_stale_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(scheduler_stale=True))

    assert report["status"] == "BLOCKED"
    assert "scheduler_stale" in report["blockers"]


def test_odds_stale_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(odds_stale=True))

    assert report["status"] == "BLOCKED"
    assert "odds_stale" in report["blockers"]


def test_finished_null_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(finished_null_count=1))

    assert report["status"] == "BLOCKED"
    assert "finished_null_count" in report["blockers"]


def test_non_finished_with_result_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(non_finished_with_result_count=1))

    assert report["status"] == "BLOCKED"
    assert "non_finished_with_result_count" in report["blockers"]


def test_settlement_probe_missing_waits():
    report = betting_open_gate.evaluate_gate(**_base(settlement_probe_pass=False, settlement_idempotency_pass=False))

    assert report["status"] == "WAIT"
    assert "settlement_e2e_probe_not_passed" in report["blockers"]
    assert "settlement_idempotency_not_passed" in report["blockers"]


def test_leaderboard_internal_id_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(leaderboard_safe=False, leaderboard_exposes_internal_id=True))

    assert report["status"] == "BLOCKED"
    assert "leaderboard_unsafe" in report["blockers"]
    assert "leaderboard_exposes_internal_id" in report["blockers"]


def test_betting_enabled_live_when_all_conditions_pass_without_artificial_blocker(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "true")
    before = os.getenv("BETTING_ENABLED")

    report = betting_open_gate.evaluate_gate(**_base(betting_enabled=True))

    assert report["status"] == "LIVE"
    assert report["betting_open_gate_status"] == "LIVE"
    assert report["recommend_open_betting"] is False
    assert report["blockers"] == []
    assert report["betting_open_blockers"] == []
    assert "betting_enabled_already_true" not in report["blockers"]
    assert "betting_enabled_true_before_gate_ready" not in report["blockers"]
    assert os.getenv("BETTING_ENABLED") == before


def test_betting_enabled_with_wait_blocker_is_blocked_without_artificial_blocker(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "true")
    before = os.getenv("BETTING_ENABLED")

    report = betting_open_gate.evaluate_gate(**_base(betting_enabled=True, two_matchdays_auto_result_sync=False))

    assert report["status"] == "BLOCKED"
    assert "need_two_matchdays_auto_result_sync" in report["blockers"]
    assert "betting_enabled_already_true" not in report["blockers"]
    assert "betting_enabled_true_before_gate_ready" not in report["blockers"]
    assert os.getenv("BETTING_ENABLED") == before


def test_betting_enabled_with_odds_stale_blocks_on_real_reason():
    report = betting_open_gate.evaluate_gate(**_base(betting_enabled=True, odds_stale=True))

    assert report["status"] == "BLOCKED"
    assert report["betting_open_gate_status"] == "BLOCKED"
    assert "odds_stale" in report["blockers"]
    assert "betting_enabled_already_true" not in report["blockers"]
    assert "betting_enabled_true_before_gate_ready" not in report["blockers"]


def test_betting_enabled_with_overdue_closed_result_blocks_gate():
    report = betting_open_gate.evaluate_gate(**_base(betting_enabled=True, result_overdue_closed_count=2))

    assert report["status"] == "BLOCKED"
    assert report["betting_open_gate_status"] == "BLOCKED"
    assert "result_overdue_closed_matches" in report["blockers"]


def test_api_health_outputs_betting_open_gate_status(monkeypatch):
    monkeypatch.setattr(
        main,
        "scheduler_freshness",
        lambda: {"scheduler_last_seen": None, "scheduler_last_seen_age_minutes": None, "scheduler_stale": False},
    )
    monkeypatch.setattr(main, "latest_ops_health_status", lambda: {"latest_ops_health_check_at": None, "ops_health_status": None, "ops_health_blockers": []})
    monkeypatch.setattr(main, "_p3_fifa_health_summary", lambda: {"p3_mode": "fifa_matchdata", "p3_status": "WAIT", "p3_candidate_w": 0, "p3_production_w": 0})
    monkeypatch.setattr(
        main,
        "_betting_open_gate_health_summary",
        lambda: {
            "betting_open_gate_status": "WAIT",
            "recommend_open_betting": False,
            "betting_open_blockers": ["need_two_matchdays_auto_result_sync"],
            "betting_open_warnings": ["p3_wait"],
        },
    )

    payload = main.health()

    assert payload["betting_open_gate_status"] == "WAIT"
    assert payload["recommend_open_betting"] is False
    assert payload["betting_open_blockers"] == ["need_two_matchdays_auto_result_sync"]


def test_historical_official_result_fallback_outside_recent_window_does_not_block(monkeypatch):
    monkeypatch.setattr(betting_open_gate, "_rows", lambda conn, sql: [{"matchday": "2026-06-11"}, {"matchday": "2026-06-12"}])

    def fake_scalar(conn, sql, params=None):
        if "official_result_fallback" in sql and "started_at::date" in sql:
            assert params == ("2026-06-11",)
            return 0
        if "official_result_fallback" in sql:
            return 4
        if "results_sync" in sql:
            return 2
        return 0

    monkeypatch.setattr(betting_open_gate, "_scalar", fake_scalar)

    evidence = betting_open_gate._two_matchdays_auto_result_sync_evidence(object())

    assert betting_open_gate._two_matchdays_auto_result_sync(object()) is True
    assert evidence["two_matchdays_auto_result_sync"] is True
    assert evidence["fallback_window_start"] == "2026-06-11"
    assert evidence["recent_fallback_ok_count"] == 0
    assert evidence["historical_fallback_ok_count"] == 4
    assert evidence["results_ok_count"] == 2


def test_official_result_fallback_inside_recent_window_blocks(monkeypatch):
    monkeypatch.setattr(betting_open_gate, "_rows", lambda conn, sql: [{"matchday": "2026-06-18"}, {"matchday": "2026-06-19"}])

    def fake_scalar(conn, sql, params=None):
        if "official_result_fallback" in sql and "started_at::date" in sql:
            assert params == ("2026-06-18",)
            return 1
        if "official_result_fallback" in sql:
            return 4
        if "results_sync" in sql:
            return 2
        return 0

    monkeypatch.setattr(betting_open_gate, "_scalar", fake_scalar)

    evidence = betting_open_gate._two_matchdays_auto_result_sync_evidence(object())

    assert evidence["two_matchdays_auto_result_sync"] is False
    assert betting_open_gate._two_matchdays_auto_result_sync(object()) is False
    assert evidence["recent_fallback_ok_count"] == 1


def test_two_matchdays_auto_result_sync_requires_two_results_sync_ok(monkeypatch):
    monkeypatch.setattr(betting_open_gate, "_rows", lambda conn, sql: [{"matchday": "2026-06-18"}, {"matchday": "2026-06-19"}])

    def fake_scalar(conn, sql, params=None):
        if "results_sync" in sql:
            return 1
        return 0

    monkeypatch.setattr(betting_open_gate, "_scalar", fake_scalar)

    evidence = betting_open_gate._two_matchdays_auto_result_sync_evidence(object())

    assert evidence["two_matchdays_auto_result_sync"] is False
    assert evidence["results_ok_count"] == 1


def test_two_matchdays_auto_result_sync_requires_two_finished_matchdays(monkeypatch):
    monkeypatch.setattr(betting_open_gate, "_rows", lambda conn, sql: [{"matchday": "2026-06-19"}])
    monkeypatch.setattr(betting_open_gate, "_scalar", lambda conn, sql, params=None: 99)

    evidence = betting_open_gate._two_matchdays_auto_result_sync_evidence(object())

    assert evidence["two_matchdays_auto_result_sync"] is False
    assert evidence["recent_matchdays"] == ["2026-06-19"]
    assert evidence["recent_fallback_ok_count"] is None
