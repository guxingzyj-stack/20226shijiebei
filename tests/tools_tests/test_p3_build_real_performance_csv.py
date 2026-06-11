from __future__ import annotations

from pathlib import Path

from tools import p3_build_real_performance_csv as builder


HEADER = "team,player_name,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,source,retrieved_at,confidence,notes\n"
REAL_HEADER = "team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes\n"


def test_builder_waits_without_source_csv(tmp_path: Path) -> None:
    report = builder.build_real_performance_csv(
        out=tmp_path / "real_performance_squad.csv",
        source_file=tmp_path / "missing.csv",
        raw_dir=tmp_path / "missing_dir",
        dry_run=True,
    )

    assert report["result"] == "WAIT"
    assert report["reason"] == "no_legal_recent_performance_source"
    assert report["would_write_csv"] is False
    assert not (tmp_path / "real_performance_squad.csv").exists()


def test_builder_rejects_example_rows(tmp_path: Path, monkeypatch) -> None:
    _write_roster(tmp_path, "Mexico", "Mexico Player 1")
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    source = tmp_path / "real_performance_squad_source.csv"
    source.write_text(
        HEADER + "Mexico,Mexico Player 1,Club,900,1,1,0.5,0.2,EXAMPLE_ONLY_DO_NOT_USE,2026-06-12,high,test\n",
        encoding="utf-8",
    )

    report = builder.build_real_performance_csv(
        out=tmp_path / "real_performance_squad.csv",
        source_file=source,
        raw_dir=tmp_path / "missing_dir",
        dry_run=False,
    )

    assert report["result"] == "FAIL"
    assert report["fake_or_example_rows_detected"] is True
    assert not (tmp_path / "real_performance_squad.csv").exists()


def test_builder_requires_source_retrieved_at_and_confidence(tmp_path: Path, monkeypatch) -> None:
    _write_roster(tmp_path, "Mexico", "Mexico Player 1")
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    source = tmp_path / "real_performance_squad_source.csv"
    source.write_text(HEADER + "Mexico,Mexico Player 1,Club,900,1,1,0.5,0.2,,,certain,test\n", encoding="utf-8")

    report = builder.build_real_performance_csv(
        out=tmp_path / "real_performance_squad.csv",
        source_file=source,
        raw_dir=tmp_path / "missing_dir",
        dry_run=True,
    )

    errors = str(report["errors"])
    assert report["result"] == "FAIL"
    assert "missing required source" in errors
    assert "missing required retrieved_at" in errors
    assert "confidence must be high, medium, or low" in errors


def test_builder_reports_unmatched_players(tmp_path: Path, monkeypatch) -> None:
    _write_roster(tmp_path, "Mexico", "Mexico Player 1")
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    source = tmp_path / "real_performance_squad_source.csv"
    source.write_text(
        HEADER + "Mexico,Unknown Player,Club,900,1,1,0.5,0.2,manual,2026-06-12,high,test\n",
        encoding="utf-8",
    )

    report = builder.build_real_performance_csv(
        out=tmp_path / "real_performance_squad.csv",
        source_file=source,
        raw_dir=tmp_path / "missing_dir",
        dry_run=True,
    )

    assert report["result"] == "FAIL"
    assert report["unmatched_players"] == ["Mexico::Unknown Player"]


def test_builder_writes_valid_csv_and_reports_coverage(tmp_path: Path, monkeypatch) -> None:
    _write_roster(tmp_path, "Mexico", "Mexico Player 1")
    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    source = tmp_path / "real_performance_squad_source.csv"
    out = tmp_path / "real_performance_squad.csv"
    source.write_text(
        HEADER + "Mexico,Mexico Player 1,Club,900,1,1,, ,manual,2026-06-12,high,unavailable xg xa\n",
        encoding="utf-8",
    )

    report = builder.build_real_performance_csv(
        out=out,
        source_file=source,
        raw_dir=tmp_path / "missing_dir",
        dry_run=False,
    )

    assert report["result"] == "PASS"
    assert report["rows"] == 1
    assert report["coverage_by_team"]["Mexico"]["ratio"] == 1.0
    assert report["teams_below_70_percent"] == []
    assert report["would_write_csv"] is True
    assert out.exists()


def _write_roster(tmp_path: Path, team: str, player: str) -> None:
    text = REAL_HEADER + f"{team},{player},MF,25,Club,,,,,,,manual,2026-06-12,high,test\n"
    (tmp_path / "manual_real_squad.csv").write_text(text, encoding="utf-8")
