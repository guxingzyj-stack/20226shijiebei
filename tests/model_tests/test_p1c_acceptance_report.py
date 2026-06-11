from __future__ import annotations

from model import p1c_acceptance_report


def test_p1c_acceptance_waits_when_no_real_historical_market_rows() -> None:
    report = p1c_acceptance_report.generate_report()

    assert report["result"] == "WAIT"
    assert report["metrics"]["market_rps"] is None
    assert report["production_safety"]["uses_fake_metrics"] is False

