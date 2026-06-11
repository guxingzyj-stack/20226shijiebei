from __future__ import annotations

from pathlib import Path

from model import p3_ingest


def test_real_csv_validate_as_small_batch_pass() -> None:
    report = p3_ingest.validate_real(dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert report["result"] == "PASS"
    assert report["real_csv_exists"] is True
    assert report["would_write_db"] is False


def test_header_only_real_templates_validate_as_empty_wait(tmp_path: Path) -> None:
    header = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(header, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "no_real_data_csv"
    assert report["result"] == "WAIT"
    assert report["real_csv_exists"] is False


def test_real_confidence_validation(tmp_path: Path) -> None:
    header = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
    bad = header + "Mexico,Player A,FW,25,Club,100,1,0,0.5,0.2,,manual,2026-06-11,certain,test\n"
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(bad, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["ok"] is False
    assert report["result"] == "FAIL"
    assert "confidence must be high, medium, or low" in str(report["details"])


def test_real_feature_dry_run_generates_preview(tmp_path: Path) -> None:
    header = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
    rows = (
        header
        + "Mexico,Player A,FW,25,Club,900,4,2,3.5,1.2,,manual,2026-06-11,high,test\n"
        + "South Africa,Player B,MF,27,Club,800,1,3,0.8,2.1,out,manual,2026-06-11,medium,test\n"
    )
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(rows, encoding="utf-8")

    result = p3_ingest.build_team_features_real(dry_run=True, data_dir=tmp_path)

    assert result["result"] == "PASS"
    assert sorted(result["teams"]) == ["Mexico", "South Africa"]
    assert result["would_write_db"] is False
    assert result["w_gbm"] == 0


def test_real_feature_dry_run_uses_age_for_avg_age(tmp_path: Path) -> None:
    header = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
    rows = header + "Mexico,Player A,FW,25,Club,,,,,,,manual,2026-06-11,high,test\n"
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(rows, encoding="utf-8")

    result = p3_ingest.build_team_features_real(dry_run=True, data_dir=tmp_path)
    mexico = result["feature_preview"][0]

    assert mexico["avg_age"] == 25
    assert mexico["missing_avg_age"] is False


def test_real_data_files_are_preferred_over_templates(tmp_path: Path) -> None:
    header = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
    good = header + "Mexico,Player A,FW,25,Club,100,1,0,0.5,0.2,,manual,2026-06-11,high,test\n"
    for name in ("manual_real_squad.csv", "manual_real_player_stats.csv", "manual_real_injuries.csv"):
        (tmp_path / name).write_text(good, encoding="utf-8")
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(header, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["real_csv_exists"] is True
    assert report["rows_validated"] == 3
    assert report["retrieved_at_coverage"] == {"squad": 1, "player_stats": 1, "injuries": 1}
    assert report["confidence_valid"] is True
