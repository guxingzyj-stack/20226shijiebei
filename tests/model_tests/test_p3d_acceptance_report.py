from __future__ import annotations

from model import p3d_acceptance_report


def test_p3d_acceptance_passes_for_small_batch_real_csv_and_keeps_gbm_zero() -> None:
    report = p3d_acceptance_report.generate_report()

    assert report["result"] == "PASS"
    assert report["blocker"] is None
    assert report["real_csv_validation"]["real_csv_exists"] is True
    assert report["real_csv_validation"]["would_write_db"] is False
    assert report["gbm_status"]["w_gbm"] == 0
    assert report["gbm_status"]["affects_p1_predictions"] is False
