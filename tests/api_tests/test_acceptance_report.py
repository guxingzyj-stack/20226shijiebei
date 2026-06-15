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
    monkeypatch.setattr(acceptance_report, "_recent_ops_log", lambda job_name: [])
    monkeypatch.setattr(acceptance_report, "_p3_status", lambda: {"tables_exist": False, "gbm_enabled": False, "gbm_weight": 0, "status": "pending_migration"})
    monkeypatch.setattr(acceptance_report, "_p4_status", lambda: {"finished_matches": 0, "recap_available": False, "status": "insufficient_finished_matches"})

    acceptance_report.print_report(acceptance_report.generate_report())

    output = capsys.readouterr().out
    assert "postgresql://user:secret@example/db" not in output
    assert "super-secret-jwt" not in output
    assert "DATABASE_URL_exists: yes" in output
    assert "JWT_SECRET_exists: yes" in output
    assert "7. P3" in output
    assert "8. P4" in output


def test_api_acceptance_contract_checks():
    assert acceptance_report._latest_prediction_uses_match_latest_prediction() is True
    assert acceptance_report._detail_does_not_set_top_level_score_matrix() is True
    assert acceptance_report._leaderboard_hides_id() is True


def test_ev_queries_filter_match_latest_prediction_version():
    import inspect

    from api.db import Database

    latest_source = inspect.getsource(Database.latest_ev_signals)
    best_source = inspect.getsource(Database.best_ev_signal)
    latest_prediction_subquery = "select p.model_version from predictions p"
    latest_compact = " ".join(latest_source.split()).lower()
    best_compact = " ".join(best_source.split()).lower()

    assert "model_version = (" in latest_source
    assert latest_prediction_subquery in latest_compact
    assert "where p.match_id = %s" in latest_compact
    assert "model_version = (" in best_source
    assert latest_prediction_subquery in best_compact
    assert "where p.match_id = %s" in best_compact


def test_best_ev_signal_filters_suggestion_eligible():
    import inspect

    from api.db import Database

    best_source = inspect.getsource(Database.best_ev_signal)

    assert "suggestion_eligible = true" in best_source
