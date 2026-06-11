from api import health_report


def test_health_report_result_pass_when_readonly_system_ok():
    report = {
        "database": "ok",
        "odds_snapshots count": 10,
        "betting_enabled": "false",
        "test_users_count": 0,
        "test_matches_count": 0,
    }

    assert health_report._result(report) == "PASS"


def test_health_report_warns_when_betting_enabled():
    report = {
        "database": "ok",
        "odds_snapshots count": 10,
        "betting_enabled": "true",
        "test_users_count": 0,
        "test_matches_count": 0,
    }

    assert health_report._result(report) == "WARN"


def test_health_report_fails_without_database_or_odds():
    assert health_report._result({"database": "fail", "odds_snapshots count": 10}) == "FAIL"
    assert health_report._result({"database": "ok", "odds_snapshots count": 0}) == "FAIL"


def test_health_report_output_has_required_keys(capsys):
    health_report.print_report(
        {
            "database": "ok",
            "matches count": 1,
            "odds_snapshots count": 2,
            "latest odds fetched_at": "2026-06-11",
            "latest model_version": {"id": 1},
            "latest prediction count": 3,
            "latest ev_signals count": 4,
            "betting_enabled": "false",
            "api_scheduler_enabled": "true",
            "recent ops_log": {},
            "open_bets_count": 0,
            "test_users_count": 0,
            "test_matches_count": 0,
            "result": "PASS",
        }
    )

    output = capsys.readouterr().out
    assert "Health Report" in output
    assert "- latest ev_signals count: 4" in output
    assert "- result: PASS" in output
