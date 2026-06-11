from __future__ import annotations

from pathlib import Path

from model import p3_ingest


def test_real_templates_validate_as_empty_wait() -> None:
    report = p3_ingest.validate_real(dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "no_real_data_csv"
    assert report["result"] == "WAIT"
    assert report["would_write_db"] is False


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

