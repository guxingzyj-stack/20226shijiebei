import pytest

from model import p3_ingest, p3_train


def test_sample_csv_validation_passes():
    result = p3_ingest.validate(sample=True)

    assert result["ok"] is True
    assert result["details"]["squad"]["rows"] == 6
    assert result["details"]["player_stats"]["rows"] == 6
    assert result["details"]["injuries"]["rows"] == 2


def test_sample_dry_run_does_not_need_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(p3_ingest.db, "get_conn", lambda: (_ for _ in ()).throw(AssertionError("database should not be used")))

    result = p3_ingest.import_manual_data(sample=True, dry_run=True)

    assert result["would_write_db"] is False
    assert result["players"] == 6


def test_import_sample_without_confirm_refuses_write():
    with pytest.raises(ValueError, match="IMPORT_SAMPLE_DATA"):
        p3_ingest.import_manual_data(sample=True, dry_run=False)


def test_build_team_features_sample_dry_run_generates_two_teams(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = p3_ingest.build_team_features(sample=True, dry_run=True)

    teams = {row["team"] for row in result["features"]}
    assert teams == {"Mexico", "South Africa"}
    assert result["team_features"] == 2
    assert set(result["missing_indicators"]) == {"Mexico", "South Africa"}


def test_validate_missing_sample_like_fields_fails(tmp_path):
    (tmp_path / "manual_squad_template.csv").write_text("player_key,name\np1,A\n", encoding="utf-8")
    (tmp_path / "manual_player_stats_template.csv").write_text(
        "player_key,season,club,minutes,goals,assists,xg,xa,source\n",
        encoding="utf-8",
    )
    (tmp_path / "manual_injuries_template.csv").write_text(
        "player_key,team,status,injury_type,expected_return,source\n",
        encoding="utf-8",
    )

    result = p3_ingest.validate(data_dir=tmp_path)

    assert result["ok"] is False
    assert "team" in result["details"]["squad"]["missing_columns"]


def test_p3_train_sample_dry_run_keeps_zero_weight_when_unavailable(monkeypatch):
    monkeypatch.setattr(p3_train, "_lightgbm_available", lambda: False)

    result = p3_train.train(sample=True, dry_run=True)

    assert result["status"] == "gbm_unavailable"
    assert result["w_gbm"] == 0


def test_p3_train_sample_dry_run_keeps_zero_weight_when_insufficient(monkeypatch):
    monkeypatch.setattr(p3_train, "_lightgbm_available", lambda: True)

    result = p3_train.train(sample=True, dry_run=True)

    assert result["status"] == "insufficient_team_features"
    assert result["w_gbm"] == 0
