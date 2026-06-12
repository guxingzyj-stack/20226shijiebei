from __future__ import annotations

from pathlib import Path

from model import p3_fifa_readiness


def test_no_fifa_sample_reports_wait(tmp_path: Path) -> None:
    report = p3_fifa_readiness.generate_report(data_dir=tmp_path)

    assert report["p3_status"] == "WAIT"
    assert report["candidate_w_p3"] == 0
    assert report["production_w_p3"] == 0
    assert "missing_fifa_matchdata" in report["blockers"]


def test_one_fifa_match_enters_shadow(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=1, teams=2)

    report = p3_fifa_readiness.generate_report(data_dir=tmp_path)

    assert report["p3_status"] == "SHADOW"
    assert report["p3_features_generated"] is True
    assert report["candidate_w_p3"] == 0
    assert report["production_w_p3"] == 0
    assert "insufficient_fifa_matchdata_samples" in report["blockers"]


def test_sixteen_matches_can_enter_candidate(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=16, teams=16)

    report = p3_fifa_readiness.generate_report(data_dir=tmp_path)

    assert report["p3_status"] == "CANDIDATE"
    assert report["candidate_w_p3"] == 0.05
    assert report["production_w_p3"] == 0
    assert report["production_weight_changed"] is False


def test_thirty_two_matches_enter_active_ready_only_with_all_gates(tmp_path: Path) -> None:
    _write_rows(tmp_path, matches=32, teams=32)

    report = p3_fifa_readiness.generate_report(
        data_dir=tmp_path,
        consecutive_matchdays_ok=True,
        p1c_prime_ready=True,
        p3_feature_eval_not_degrade=True,
        user_approved=True,
    )

    assert report["p3_status"] == "ACTIVE_READY"
    assert report["candidate_w_p3"] == 0.05
    assert report["production_w_p3"] == 0
    assert report["production_w_gbm"] == 0


def test_health_summary_never_exposes_paths_or_large_objects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(p3_fifa_readiness, "DEFAULT_DATA_DIR", tmp_path)

    summary = p3_fifa_readiness.health_summary()

    assert summary == {
        "p3_mode": "fifa_matchdata",
        "p3_status": "WAIT",
        "p3_candidate_w": 0,
        "p3_production_w": 0,
        "p3_blockers": ["missing_fifa_matchdata"],
    }


def _write_rows(data_dir: Path, *, matches: int, teams: int) -> None:
    path = data_dir / "real_performance_fifa_match_sample.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("match_id,team,player_name,minutes,goals,assists\n")
        for index in range(matches):
            home = f"Team {index % teams}"
            away = f"Team {(index + 1) % teams}"
            handle.write(f"match-{index},{home},Player {index}A,90,{index % 3},1\n")
            handle.write(f"match-{index},{away},Player {index}B,84,0,{index % 2}\n")
