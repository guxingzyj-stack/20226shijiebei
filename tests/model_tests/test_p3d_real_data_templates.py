from __future__ import annotations

from pathlib import Path

from model import p3_ingest


REAL_HEADER = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
PERFORMANCE_HEADER = "team,player_name,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,source,retrieved_at,confidence,notes\n"


def test_real_csv_validate_as_small_batch_pass() -> None:
    report = p3_ingest.validate_real(dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert report["result"] == "PASS"
    assert report["real_csv_exists"] is True
    assert report["would_write_db"] is False


def test_header_only_real_templates_validate_as_empty_wait(tmp_path: Path) -> None:
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(REAL_HEADER, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "no_real_data_csv"
    assert report["result"] == "WAIT"
    assert report["real_csv_exists"] is False


def test_real_confidence_validation(tmp_path: Path) -> None:
    bad = REAL_HEADER + "Mexico,Player A,FW,25,Club,100,1,0,0.5,0.2,,manual,2026-06-11,certain,test\n"
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(bad, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["ok"] is False
    assert report["result"] == "FAIL"
    assert "confidence must be high, medium, or low" in str(report["details"])


def test_real_feature_dry_run_generates_preview(tmp_path: Path) -> None:
    rows = (
        REAL_HEADER
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
    rows = REAL_HEADER + "Mexico,Player A,FW,25,Club,,,,,,,manual,2026-06-11,high,test\n"
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(rows, encoding="utf-8")

    result = p3_ingest.build_team_features_real(dry_run=True, data_dir=tmp_path)
    mexico = result["feature_preview"][0]

    assert mexico["avg_age"] == 25
    assert mexico["missing_avg_age"] is False


def test_real_data_files_are_preferred_over_templates(tmp_path: Path) -> None:
    good = REAL_HEADER + "Mexico,Player A,FW,25,Club,100,1,0,0.5,0.2,,manual,2026-06-11,high,test\n"
    for name in ("manual_real_squad.csv", "manual_real_player_stats.csv", "manual_real_injuries.csv"):
        (tmp_path / name).write_text(good, encoding="utf-8")
    for name in ("manual_real_squad_template.csv", "manual_real_player_stats_template.csv", "manual_real_injuries_template.csv"):
        (tmp_path / name).write_text(REAL_HEADER, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["real_csv_exists"] is True
    assert report["rows_validated"] == 3
    assert report["retrieved_at_coverage"] == {"squad": 1, "player_stats": 1, "injuries": 1, "performance": 0}
    assert report["confidence_valid"] is True


def test_performance_file_requires_complete_numeric_fields(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    bad = PERFORMANCE_HEADER + "Mexico,Mexico Player 1,Club,900,1,,0.5,0.1,manual,2026-06-12,high,test\n"
    (tmp_path / "real_performance_test.csv").write_text(bad, encoding="utf-8")

    report = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert report["ok"] is False
    assert report["result"] == "FAIL"
    assert "missing required numeric assists_recent" in str(report["details"]["performance"]["errors"])


def test_performance_coverage_enables_gbm_readiness_but_dry_run_keeps_zero_weight(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico", "South Africa"), players_per_team=10)
    performance_rows = [PERFORMANCE_HEADER]
    for team in ("Mexico", "South Africa"):
        for index in range(1, 8):
            performance_rows.append(
                f"{team},{team} Player {index},Club,{800 + index},1,2,0.{index},0.{index},manual,2026-06-12,high,test\n"
            )
    (tmp_path / "real_performance_test.csv").write_text("".join(performance_rows), encoding="utf-8")

    dry_run = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=True)
    not_dry_run = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=False)

    assert dry_run["gbm_ready"] is True
    assert dry_run["performance_coverage"]["teams_ready"] == 2
    assert dry_run["w_gbm"] == 0
    assert dry_run["would_write_db"] is False
    assert not_dry_run["w_gbm"] == 0.2
    assert not_dry_run["would_write_db"] is False


def _write_real_rows(tmp_path: Path, teams: tuple[str, ...], players_per_team: int) -> None:
    rows = [REAL_HEADER]
    for team in teams:
        for index in range(1, players_per_team + 1):
            rows.append(f"{team},{team} Player {index},MF,25,Club,,,,,,,manual,2026-06-12,high,test\n")
    text = "".join(rows)
    for name in ("manual_real_squad.csv", "manual_real_player_stats.csv", "manual_real_injuries.csv"):
        (tmp_path / name).write_text(text, encoding="utf-8")
