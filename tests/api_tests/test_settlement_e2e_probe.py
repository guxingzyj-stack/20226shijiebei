from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from api import settlement_e2e_probe


def _plan(blockers=None):
    return settlement_e2e_probe.ProbePlan(
        match_id="500-1359172",
        stake=Decimal("1"),
        target_match={
            "match_id": "500-1359172",
            "match_num": "001",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "status": "finished",
            "result_home": 2,
            "result_away": 0,
            "ht_home": None,
            "ht_away": None,
        },
        latest_odds=Decimal("1.26"),
        selected_outcome="had:3",
        expected_status="won",
        expected_payout=Decimal("1.26"),
        blockers=blockers or [],
    )


def test_dry_run_does_not_write_db(monkeypatch):
    called = []
    monkeypatch.setattr(settlement_e2e_probe, "build_plan", lambda match_id, stake: _plan())
    monkeypatch.setattr(settlement_e2e_probe, "_create_probe_bet", lambda plan: called.append(plan))

    report = settlement_e2e_probe.dry_run()

    assert report["ok"] is True
    assert report["would_write_db"] is False
    assert report["probe_user_would_create"] == settlement_e2e_probe.PROBE_USERNAME
    assert called == []


def test_confirm_rejects_wrong_code():
    with pytest.raises(ValueError, match="confirm code"):
        settlement_e2e_probe.confirm_probe(confirm="WRONG")


def test_confirm_rejects_when_betting_enabled(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "true")

    with pytest.raises(ValueError, match="BETTING_ENABLED"):
        settlement_e2e_probe.confirm_probe(confirm=settlement_e2e_probe.CONFIRM_CODE)


def test_build_plan_rejects_target_match_without_result(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/test")
    monkeypatch.setenv("BETTING_ENABLED", "false")
    monkeypatch.setattr(
        settlement_e2e_probe,
        "_target_match",
        lambda match_id: {"match_id": match_id, "status": "finished", "result_home": None, "result_away": None},
    )
    monkeypatch.setattr(settlement_e2e_probe, "_result_consistency_counts", lambda: {"finished_null": 0, "non_finished_with_result": 0})
    monkeypatch.setattr(settlement_e2e_probe, "_non_probe_open_pending_count", lambda: 0)
    monkeypatch.setattr(settlement_e2e_probe, "_probe_artifact_count", lambda: 0)
    monkeypatch.setattr(settlement_e2e_probe, "_latest_had_home_odds", lambda match_id: Decimal("1.26"))

    plan = settlement_e2e_probe.build_plan("500-1359172", Decimal("1"))

    assert "target_match_result_missing" in plan.blockers


def test_build_plan_rejects_existing_non_probe_open_pending_bets(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/test")
    monkeypatch.setenv("BETTING_ENABLED", "false")
    monkeypatch.setattr(
        settlement_e2e_probe,
        "_target_match",
        lambda match_id: {"match_id": match_id, "status": "finished", "result_home": 2, "result_away": 0},
    )
    monkeypatch.setattr(settlement_e2e_probe, "_result_consistency_counts", lambda: {"finished_null": 0, "non_finished_with_result": 0})
    monkeypatch.setattr(settlement_e2e_probe, "_non_probe_open_pending_count", lambda: 1)
    monkeypatch.setattr(settlement_e2e_probe, "_probe_artifact_count", lambda: 0)
    monkeypatch.setattr(settlement_e2e_probe, "_latest_had_home_odds", lambda match_id: Decimal("1.26"))

    plan = settlement_e2e_probe.build_plan("500-1359172", Decimal("1"))

    assert "existing_open_pending_bets" in plan.blockers


def test_confirm_probe_settles_cleans_up_writes_ops_log(monkeypatch):
    monkeypatch.setenv("BETTING_ENABLED", "false")
    records = []
    balances = iter([Decimal("10000.26"), Decimal("10000.26")])
    snapshots = iter(
        [
            {"id": 1, "status": "won", "payout": Decimal("1.26"), "settled_at": "clock"},
            {"id": 1, "status": "won", "payout": Decimal("1.26"), "settled_at": "clock"},
        ]
    )
    stats = iter(
        [
            SimpleNamespace(open_bets_seen=1, settled_won=1, settled_lost=0, settled_void=0, skipped_not_ready=0, errors=0),
            SimpleNamespace(open_bets_seen=0, settled_won=0, settled_lost=0, settled_void=0, skipped_not_ready=0, errors=0),
        ]
    )
    monkeypatch.setattr(settlement_e2e_probe, "build_plan", lambda match_id, stake: _plan())
    monkeypatch.setattr(settlement_e2e_probe, "_create_probe_bet", lambda plan: {"user_id": 1, "bet_id": 1, "balance_after_bet": Decimal("9999")})
    monkeypatch.setattr(settlement_e2e_probe, "run_settlement_job", lambda dry_run=False, record_log=True: next(stats))
    monkeypatch.setattr(settlement_e2e_probe, "_probe_bet_snapshot", lambda bet_id: next(snapshots))
    monkeypatch.setattr(settlement_e2e_probe, "_probe_user_balance", lambda: next(balances))
    monkeypatch.setattr(settlement_e2e_probe, "_cleanup_probe_data", lambda: {"deleted_bets": 1, "deleted_users": 1, "cleanup_success": True})
    monkeypatch.setattr(
        settlement_e2e_probe,
        "_leaderboard_safety",
        lambda: {"leaderboard_no_probe_user_pollution": True, "leaderboard_no_internal_id": True},
    )
    monkeypatch.setattr(settlement_e2e_probe, "record_ops_log", lambda *args, **kwargs: records.append((args, kwargs)))

    report = settlement_e2e_probe.confirm_probe(confirm=settlement_e2e_probe.CONFIRM_CODE)

    assert report["ok"] is True
    assert report["probe_bet_id"] == 1
    assert report["balance_delta_correct"] is True
    assert report["idempotency_pass"] is True
    assert report["cleanup_success"] is True
    assert records
    assert records[0][0][0] == settlement_e2e_probe.JOB_NAME
    assert records[0][0][1] == "ok"
