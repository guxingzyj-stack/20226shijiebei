from __future__ import annotations

from ops import next_phase_acceptance


def test_next_phase_acceptance_waits_without_production_risk() -> None:
    report = next_phase_acceptance.generate_report()

    assert report["overall_result"] == "WAIT"
    assert report["production_safety"]["betting_enabled"] is False
    assert report["production_safety"]["gbm_weight"] == 0
    assert report["production_safety"]["would_write_db"] is False
