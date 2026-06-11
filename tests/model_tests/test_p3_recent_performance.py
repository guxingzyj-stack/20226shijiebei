from __future__ import annotations

from pathlib import Path

from model import p3_ingest


REAL_HEADER = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"
PERFORMANCE_HEADER = "team,player_name,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,source,retrieved_at,confidence,notes\n"


def test_no_real_performance_csv_keeps_gbm_closed(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=3)

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)
    features = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is True
    assert validation["details"]["performance"]["real_performance_csv_exists"] is False
    assert validation["performance_rows_validated"] == 0
    assert features["gbm_ready"] is False
    assert features["candidate_w_gbm"] == 0
    assert features["w_gbm"] == 0
    assert features["would_write_db"] is False


def test_real_performance_template_is_ignored(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad_template.csv").write_text(
        PERFORMANCE_HEADER
        + "EXAMPLE_ONLY_DO_NOT_USE,Example,Club,1,0,0,0,0,EXAMPLE_ONLY_DO_NOT_USE,2026-06-12,low,EXAMPLE_ONLY_DO_NOT_USE\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is True
    assert validation["performance_files"] == []
    assert validation["performance_rows_validated"] == 0


def test_real_performance_unmatched_outputs_are_ignored(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_unmatched_statsbomb.csv").write_text(
        "statsbomb_player_name,statsbomb_team,candidate_project_players,reason\n"
        "Unknown,Mexico,,no_exact_project_roster_match\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is True
    assert validation["performance_files"] == []
    assert validation["performance_rows_validated"] == 0


def test_performance_requires_source_retrieved_at_and_confidence(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad.csv").write_text(
        PERFORMANCE_HEADER + "Mexico,Mexico Player 1,Club,900,1,1,0.5,0.2,,,certain,test\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    errors = str(validation["details"]["performance"]["errors"])
    assert validation["ok"] is False
    assert "missing required source" in errors
    assert "missing required retrieved_at" in errors
    assert "confidence must be high, medium, or low" in errors


def test_performance_optional_xg_xa_require_unavailable_note(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad.csv").write_text(
        PERFORMANCE_HEADER + "Mexico,Mexico Player 1,Club,900,1,1,,,manual,2026-06-12,high,not provided\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    errors = str(validation["details"]["performance"]["errors"])
    assert validation["ok"] is False
    assert "blank xg_recent requires notes to include unavailable" in errors
    assert "blank xa_recent requires notes to include unavailable" in errors


def test_performance_optional_xg_xa_can_be_unavailable(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad.csv").write_text(
        PERFORMANCE_HEADER + "Mexico,Mexico Player 1,Club,900,1,1,,,manual,2026-06-12,high,unavailable xg xa\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is True
    assert validation["performance_rows_validated"] == 1
    assert validation["retrieved_at_coverage"]["performance"] == 1


def test_p3_light_requires_notes_even_when_xg_xa_present(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad.csv").write_text(
        PERFORMANCE_HEADER + "Mexico,Mexico Player 1,Club,900,1,1,0.5,0.2,manual,2026-06-12,high,\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is False
    assert "missing required notes" in str(validation["details"]["performance"]["errors"])


def test_performance_rejects_players_outside_official_roster(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=1)
    (tmp_path / "real_performance_squad.csv").write_text(
        PERFORMANCE_HEADER + "Mexico,Unknown Player,Club,900,1,1,0.5,0.2,manual,2026-06-12,high,test\n",
        encoding="utf-8",
    )

    validation = p3_ingest.validate_real(data_dir=tmp_path, dry_run=True)

    assert validation["ok"] is False
    assert "player does not match official roster" in str(validation["details"]["performance"]["errors"])


def test_performance_coverage_below_threshold_keeps_zero_weight(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico",), players_per_team=10)
    rows = [PERFORMANCE_HEADER]
    for index in range(1, 7):
        rows.append(f"Mexico,Mexico Player {index},Club,900,1,1,0.5,0.2,manual,2026-06-12,high,test\n")
    (tmp_path / "real_performance_squad.csv").write_text("".join(rows), encoding="utf-8")

    features = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=True)

    assert features["performance_coverage"]["teams"]["Mexico"]["ratio"] == 0.6
    assert features["teams_below_70_percent"] == ["Mexico"]
    assert features["gbm_ready"] is False
    assert features["candidate_w_gbm"] == 0
    assert features["w_gbm"] == 0


def test_performance_coverage_ready_reports_candidate_weight_only_in_dry_run(tmp_path: Path) -> None:
    _write_real_rows(tmp_path, teams=("Mexico", "South Africa"), players_per_team=10)
    rows = [PERFORMANCE_HEADER]
    for team in ("Mexico", "South Africa"):
        for index in range(1, 8):
            rows.append(f"{team},{team} Player {index},Club,900,1,1,0.5,0.2,manual,2026-06-12,high,test\n")
    (tmp_path / "real_performance_squad.csv").write_text("".join(rows), encoding="utf-8")

    features = p3_ingest.build_team_features_real(data_dir=tmp_path, dry_run=True)

    assert features["gbm_ready"] is True
    assert features["teams_below_70_percent"] == []
    assert features["p3_mode"] == "light"
    assert features["requires_xg_xa"] is False
    assert features["xg_xa_optional"] is True
    assert features["light_required_fields"] == [
        "assists_recent",
        "confidence",
        "goals_recent",
        "minutes_recent",
        "notes",
        "retrieved_at",
        "source",
    ]
    assert features["candidate_w_gbm"] == 0.2
    assert features["w_gbm"] == 0
    assert features["would_write_db"] is False


def _write_real_rows(tmp_path: Path, teams: tuple[str, ...], players_per_team: int) -> None:
    rows = [REAL_HEADER]
    for team in teams:
        for index in range(1, players_per_team + 1):
            rows.append(f"{team},{team} Player {index},MF,25,Club,,,,,,,manual,2026-06-12,high,test\n")
    text = "".join(rows)
    for name in ("manual_real_squad.csv", "manual_real_player_stats.csv", "manual_real_injuries.csv"):
        (tmp_path / name).write_text(text, encoding="utf-8")
