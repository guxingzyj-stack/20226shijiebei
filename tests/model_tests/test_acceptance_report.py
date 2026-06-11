from model import acceptance_report


def test_model_acceptance_report_without_database_url_is_not_checked(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "should-not-appear")

    acceptance_report.print_report(acceptance_report.generate_report())

    output = capsys.readouterr().out
    assert "NOT_CHECKED: DATABASE_URL missing" in output
    assert "should-not-appear" not in output
    assert "OVERALL_STATUS: FAIL" in output


def test_model_acceptance_matrix_edge_check():
    matrix = [[0.0 for _ in range(11)] for _ in range(11)]
    matrix[1][0] = 0.50
    matrix[0][0] = 0.25
    matrix[0][1] = 0.25
    row = {
        "p_home": 0.5,
        "p_draw": 0.25,
        "p_away": 0.25,
        "score_matrix": matrix,
    }

    assert acceptance_report._prediction_edge_check(row) is True


def test_model_acceptance_failed_checks_pass_for_required_values():
    report = {
        "1. Latest Model Version": [
            acceptance_report.ReportLine("params.elo_start_date", "2000-01-01"),
            acceptance_report.ReportLine("params.training_start_date", "2015-01-01"),
            acceptance_report.ReportLine("k_on_boundary", False),
        ],
        "2. Predictions": [
            acceptance_report.ReportLine("score_matrix_edges_match_prediction", True),
            acceptance_report.ReportLine("ev_matches_latest_prediction_version", True),
        ],
        "3. Market Source": [
            acceptance_report.ReportLine("market_source_had_count", 20),
            acceptance_report.ReportLine("market_source_hhad_count", 4),
            acceptance_report.ReportLine("skipped_missing_market_count", 0),
            acceptance_report.ReportLine("dc_only_count", 0),
        ],
        "4. EV": [
            acceptance_report.ReportLine("ev_gt_0_15_all_research_only", True),
            acceptance_report.ReportLine("suggestion_pool_only_had_hhad", True),
        ],
    }

    assert acceptance_report.failed_checks(report) == []


def test_model_acceptance_failed_checks_include_ev_version():
    report = {
        "1. Latest Model Version": [
            acceptance_report.ReportLine("params.elo_start_date", "2000-01-01"),
            acceptance_report.ReportLine("params.training_start_date", "2015-01-01"),
            acceptance_report.ReportLine("k_on_boundary", False),
        ],
        "2. Predictions": [
            acceptance_report.ReportLine("score_matrix_edges_match_prediction", True),
            acceptance_report.ReportLine("ev_matches_latest_prediction_version", False),
        ],
        "3. Market Source": [
            acceptance_report.ReportLine("market_source_had_count", 1),
            acceptance_report.ReportLine("market_source_hhad_count", 0),
            acceptance_report.ReportLine("skipped_missing_market_count", 0),
            acceptance_report.ReportLine("dc_only_count", 0),
        ],
        "4. EV": [
            acceptance_report.ReportLine("ev_gt_0_15_all_research_only", True),
            acceptance_report.ReportLine("suggestion_pool_only_had_hhad", True),
        ],
    }

    assert "ev_matches_latest_prediction_version" in acceptance_report.failed_checks(report)
