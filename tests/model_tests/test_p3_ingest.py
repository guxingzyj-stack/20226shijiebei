from contextlib import contextmanager

from model import p3_ingest


def write_manual_csvs(path):
    (path / "manual_squad_template.csv").write_text(
        "player_key,name,team,position,birth_date,market_value,source\n"
        "p1,Alice,Team A,FW,2000-01-01,100,manual_csv\n",
        encoding="utf-8",
    )
    (path / "manual_player_stats_template.csv").write_text(
        "player_key,season,club,minutes,goals,assists,xg,xa,source\n"
        "p1,2025,Club A,900,10,3,8.5,2.1,manual_csv\n",
        encoding="utf-8",
    )
    (path / "manual_injuries_template.csv").write_text(
        "player_key,team,status,injury_type,expected_return,source\n"
        "p1,Team A,out,hamstring,2026-07-01,manual_csv\n",
        encoding="utf-8",
    )


def test_validate_checks_required_csv_columns(tmp_path):
    write_manual_csvs(tmp_path)

    result = p3_ingest.validate(tmp_path)

    assert result["ok"] is True
    assert result["details"]["squad"]["rows"] == 1


def test_validate_reports_missing_columns(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "manual_squad_template.csv").write_text("player_key,name\n", encoding="utf-8")
    (tmp_path / "manual_player_stats_template.csv").write_text(
        "player_key,season,club,minutes,goals,assists,xg,xa,source\n",
        encoding="utf-8",
    )
    (tmp_path / "manual_injuries_template.csv").write_text(
        "player_key,team,status,injury_type,expected_return,source\n",
        encoding="utf-8",
    )

    result = p3_ingest.validate(tmp_path)

    assert result["ok"] is False
    assert "team" in result["details"]["squad"]["missing_columns"]


def test_import_dry_run_counts_rows_without_db(tmp_path):
    write_manual_csvs(tmp_path)

    result = p3_ingest.import_manual_data(dry_run=True, data_dir=tmp_path)

    assert result["status"] == "dry_run"
    assert result["source"] == "manual_csv"
    assert result["players"] == 1
    assert result["player_season_stats"] == 1
    assert result["injuries"] == 1


def test_build_team_features_dry_run_handles_missing_data(monkeypatch):
    class FakeConn:
        pass

    @contextmanager
    def fake_get_conn():
        yield FakeConn()

    monkeypatch.setattr(p3_ingest.db, "get_conn", fake_get_conn)
    monkeypatch.setattr(p3_ingest, "_fetch_players", lambda _conn: [{"player_key": "p1", "team": "Team A", "market_value": ""}])
    monkeypatch.setattr(p3_ingest, "_fetch_player_stats", lambda _conn: [])
    monkeypatch.setattr(p3_ingest, "_fetch_injuries", lambda _conn: [])
    monkeypatch.setattr(p3_ingest.db, "fetch_team_ratings", lambda _conn: {})

    result = p3_ingest.build_team_features(dry_run=True)

    assert result == {"status": "dry_run", "teams": 1, "team_features": 1}
