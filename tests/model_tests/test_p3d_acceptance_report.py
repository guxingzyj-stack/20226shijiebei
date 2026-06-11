from __future__ import annotations

from model import p3d_acceptance_report


def test_p3d_acceptance_waits_for_full_real_csv_and_keeps_gbm_zero() -> None:
    report = p3d_acceptance_report.generate_report()

    assert report["result"] == "WAIT"
    assert report["blocker"] in {"no_real_performance_csv", "performance_coverage_below_threshold", "numeric_recent_stats_incomplete"}
    assert report["source_plan"]["p3_mode"] == "light"
    assert report["source_plan"]["requires_xg_xa"] is False
    assert report["source_plan"]["xg_xa_optional"] is True
    assert report["real_csv_validation"]["p3_mode"] == "light"
    assert report["feature_readiness"]["p3_mode"] == "light"
    assert report["real_csv_validation"]["real_csv_exists"] is True
    assert report["real_csv_validation"]["real_performance_csv_exists"] is False
    assert report["real_csv_validation"]["performance_rows_validated"] == 0
    assert report["real_csv_validation"]["performance_files"] == []
    assert report["real_csv_validation"]["would_write_db"] is False
    assert report["data_audit"]["summary"]["teams_total"] == 48
    assert len(report["feature_readiness"]["teams_below_70_percent"]) == 48
    assert report["feature_readiness"]["gbm_ready"] is False
    assert report["feature_readiness"]["candidate_w_gbm"] == 0
    assert report["feature_readiness"]["would_write_db"] is False
    assert report["gbm_status"]["w_gbm"] == 0
    assert report["gbm_status"]["candidate_w_gbm"] == 0
    assert report["gbm_status"]["production_w_gbm"] == 0
    assert report["gbm_status"]["affects_p1_predictions"] is False
