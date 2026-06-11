from api import acceptance_report
from api.results_sync import ResultsSyncStats
from api.settlement_runner import SettlementStats


def test_api_acceptance_report_does_not_print_secrets(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@example/db")
    monkeypatch.setenv("JWT_SECRET", "super-secret-jwt")
    monkeypatch.setenv("BETTING_ENABLED", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://worldcup2026.zeabur.app")
    monkeypatch.setattr(acceptance_report, "_run_results_sync_dry_run", lambda: ResultsSyncStats(matches_seen=1))
    monkeypatch.setattr(acceptance_report, "_run_settlement_dry_run", lambda: SettlementStats())

    acceptance_report.print_report(acceptance_report.generate_report())

    output = capsys.readouterr().out
    assert "postgresql://user:secret@example/db" not in output
    assert "super-secret-jwt" not in output
    assert "DATABASE_URL_exists: yes" in output
    assert "JWT_SECRET_exists: yes" in output


def test_api_acceptance_contract_checks():
    assert acceptance_report._latest_prediction_filters_model_version() is True
    assert acceptance_report._detail_does_not_set_top_level_score_matrix() is True
    assert acceptance_report._leaderboard_hides_id() is True
