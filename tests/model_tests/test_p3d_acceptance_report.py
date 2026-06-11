from __future__ import annotations

from model import p3d_acceptance_report


def test_p3d_acceptance_waits_without_real_csv_and_keeps_gbm_zero() -> None:
    report = p3d_acceptance_report.generate_report()

    assert report["result"] == "WAIT"
    assert report["blocker"] == "no_real_data_csv"
    assert report["real_csv_validation"]["would_write_db"] is False
    assert report["gbm_status"]["w_gbm"] == 0
    assert report["gbm_status"]["affects_p1_predictions"] is False

