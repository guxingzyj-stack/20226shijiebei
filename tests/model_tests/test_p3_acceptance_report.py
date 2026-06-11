from model import p3_acceptance_report


def test_p3_acceptance_report_sample_passes(monkeypatch):
    monkeypatch.setattr(
        p3_acceptance_report.p3_train,
        "train",
        lambda dry_run, sample: {"lightgbm_available": False, "status": "gbm_unavailable", "w_gbm": 0, "team_features": 2},
    )

    report = p3_acceptance_report.generate_report(sample=True)

    assert report["result"] == "PASS"
    assert report["dry_run_import"]["would_write_db"] is False
    assert report["production_safety"]["affects_p1_predictions"] is False


def test_p3_acceptance_report_prints_pass(monkeypatch, capsys):
    monkeypatch.setattr(
        p3_acceptance_report.p3_train,
        "train",
        lambda dry_run, sample: {"lightgbm_available": False, "status": "gbm_unavailable", "w_gbm": 0, "team_features": 2},
    )

    p3_acceptance_report.print_report(p3_acceptance_report.generate_report(sample=True))

    output = capsys.readouterr().out
    assert "P3-C Sample Pipeline Report" in output
    assert "writes_production_db: false" in output
    assert "result: PASS" in output


def test_p3_acceptance_report_fails_if_gbm_weight_nonzero():
    report = {
        "csv_validation": {"validation_errors": []},
        "dry_run_import": {"would_write_db": False},
        "team_features": {"generated_features": 2},
        "gbm": {"w_gbm": 0.1},
        "production_safety": {
            "writes_production_db": False,
            "affects_p1_predictions": False,
            "betting_enabled_changed": False,
        },
    }

    assert p3_acceptance_report._result(report) == "FAIL"
