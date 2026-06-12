from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_daily_ops_check.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_daily_ops_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_missing_database_url_does_not_leak_connection_string(monkeypatch, capsys):
    script = _load_script()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("BETTING_ENABLED", "false")
    monkeypatch.setattr(script, "fetch_api_health", lambda *args, **kwargs: {"ok": True, "scheduler_stale": False})
    monkeypatch.setattr(
        script,
        "run_ops_health_check",
        lambda record_log=True: {
            "overall": {"status": "FAIL", "blockers": ["ops_health_check_error"]},
            "odds": {},
            "result_consistency": {},
            "settlement": {"latest_settlement_runner_error": "RuntimeError: [redacted] is required"},
            "p1c_prime": {},
        },
    )

    code = script.main([])

    output = capsys.readouterr().out
    assert code == 1
    assert "DATABASE_URL_SET: False" in output
    assert "postgresql://" not in output
    assert "DATABASE_URL=" not in output


def test_betting_enabled_true_stops_before_health_check(monkeypatch, capsys):
    script = _load_script()
    called = []
    monkeypatch.setenv("BETTING_ENABLED", "true")
    monkeypatch.setattr(script, "fetch_api_health", lambda *args, **kwargs: called.append("health"))
    monkeypatch.setattr(script, "run_ops_health_check", lambda record_log=True: called.append("ops"))

    code = script.main([])

    output = capsys.readouterr().out
    assert code == 2
    assert called == []
    assert "betting_enabled_true" in output


def test_script_does_not_use_external_db_or_http_shell_tools():
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "psql" not in text
    assert "curl" not in text
    assert "bash -x" not in text


def test_daily_check_warn_is_not_fail(monkeypatch):
    script = _load_script()
    monkeypatch.setenv("BETTING_ENABLED", "false")
    monkeypatch.setattr(script, "_safe_fetch_health", lambda url: {"ok": True, "scheduler_stale": False})
    monkeypatch.setattr(
        script,
        "run_ops_health_check",
        lambda record_log=True: {
            "overall": {"status": "WARN", "blockers": ["no_open_bets_to_settle"]},
            "odds": {"odds_stale": False},
            "result_consistency": {"finished_null_count": 0, "non_finished_with_result_count": 0},
            "settlement": {"open_pending_bets": 0},
            "p1c_prime": {"evaluable_finished_matches": 2},
        },
    )

    result = script.run_daily_check()

    assert result["status"] == "WARN"
    assert result["exit_code"] == 0
