from __future__ import annotations

from model import p3_data_audit


def test_p3_data_audit_reports_48_tournament_teams() -> None:
    report = p3_data_audit.generate_report()

    assert report["summary"]["teams_total"] == 48
    assert report["summary"]["missing_teams"] == 0
    assert report["summary"]["teams_with_official_profile"] == 48
    assert report["summary"]["teams_with_numeric_stats"] == 0
    assert report["result"] == "WAIT"
    assert report["blocker"] == "numeric_recent_stats_incomplete"
    assert report["next_backlog"]


def test_p3_data_audit_canonicalizes_curacao_rows() -> None:
    report = p3_data_audit.generate_report()
    curacao = next(row for row in report["coverage"] if row["team"] == "Curacao")

    assert curacao["squad_rows"] >= 10
    assert curacao["player_stats_rows"] >= 4
    assert curacao["official_profile_rows"] >= 10
    assert "numeric_recent_stats" in curacao["missing_items"]
    assert "official_profile" not in curacao["missing_items"]


def test_write_backlog_outputs_missing_work(tmp_path) -> None:
    report = p3_data_audit.generate_report()
    path = p3_data_audit.write_backlog(report, tmp_path / "backlog.csv")

    text = path.read_text(encoding="utf-8")
    assert "team" in text
    assert "official_profile_rows" in text
    assert "numeric_recent_stats" in text
