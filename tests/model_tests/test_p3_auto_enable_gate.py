from __future__ import annotations

from pathlib import Path

from model import p3_auto_enable_gate


def test_gate_defaults_to_wait_without_weight_change(tmp_path: Path) -> None:
    report = p3_auto_enable_gate.generate_report(data_dir=tmp_path)

    assert report["p3_status"] == "WAIT"
    assert report["can_enter_shadow"] is False
    assert report["production_w_p3"] == 0
    assert report["production_weight_changed"] is False


def test_gate_candidate_does_not_change_production_weight(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=16, teams=16)

    report = p3_auto_enable_gate.generate_report(data_dir=tmp_path)

    assert report["p3_status"] == "CANDIDATE"
    assert report["can_enter_candidate"] is True
    assert report["candidate_w_p3"] == 0.05
    assert report["production_w_p3"] == 0
    assert report["production_weight_changed"] is False


def test_gate_active_ready_still_requires_zero_production_weight(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=32, teams=32)

    report = p3_auto_enable_gate.generate_report(
        data_dir=tmp_path,
        consecutive_matchdays_ok=True,
        p1c_prime_ready=True,
        p3_feature_eval_not_degrade=True,
        user_approved=True,
    )

    assert report["p3_status"] == "ACTIVE_READY"
    assert report["can_enter_active_ready"] is True
    assert report["production_w_p3"] == 0
    assert report["production_w_gbm"] == 0
    assert report["production_weight_changed"] is False


def test_gate_blocks_candidate_when_ops_health_fails(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=16, teams=16)

    report = p3_auto_enable_gate.generate_report(data_dir=tmp_path, ops_health_status="FAIL")

    assert report["p3_status"] == "SHADOW"
    assert report["can_enter_candidate"] is False
    assert "ops_health_fail" in report["blockers"]


def _write_rows(data_dir: Path, *, matches: int, teams: int) -> None:
    path = data_dir / "real_performance_fifa_match_sample.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("match_id,team,player_name,minutes,goals,assists\n")
        for index in range(matches):
            home = f"Team {index % teams}"
            away = f"Team {(index + 1) % teams}"
            handle.write(f"match-{index},{home},Player {index}A,90,1,0\n")
            handle.write(f"match-{index},{away},Player {index}B,78,0,1\n")
