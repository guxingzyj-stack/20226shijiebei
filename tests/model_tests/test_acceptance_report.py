from model import acceptance_report


def test_model_acceptance_report_without_database_url_is_not_checked(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "should-not-appear")

    acceptance_report.print_report(acceptance_report.generate_report())

    output = capsys.readouterr().out
    assert "NOT_CHECKED: DATABASE_URL missing" in output
    assert "should-not-appear" not in output


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
