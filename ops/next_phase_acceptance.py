from __future__ import annotations

import argparse
from typing import Any

from model import p1c_acceptance_report, p3_auto_enable_gate, p3d_acceptance_report


def generate_report() -> dict[str, Any]:
    p1c = p1c_acceptance_report.generate_report()
    p3d = p3d_acceptance_report.generate_report()
    p3_fifa_gate = p3_auto_enable_gate.generate_report()
    safety = {
        "betting_enabled": False,
        "gbm_weight": p3d["gbm_status"]["w_gbm"],
        "candidate_w_gbm": p3d["gbm_status"].get("candidate_w_gbm", 0),
        "production_w_gbm": p3d["gbm_status"].get("production_w_gbm", 0),
        "would_write_db": bool(p3d["feature_readiness"].get("would_write_db", False)),
        "fake_data_used": False,
        "production_weight_changed": False,
        "production_w_p3": p3_fifa_gate["production_w_p3"],
    }
    result = _overall_result(p1c, p3d, safety)
    return {"p1c": p1c, "p3d": p3d, "p3_fifa_gate": p3_fifa_gate, "production_safety": safety, "overall_result": result}


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("Next Phase Acceptance Report")
    print("")
    print("1. P1-C")
    print(f"- result: {report['p1c']['result']}")
    print(f"- market_rps: {report['p1c']['metrics']['market_rps']}")
    print(f"- dc_rps: {report['p1c']['metrics']['dc_rps']}")
    print(f"- blended_rps: {report['p1c']['metrics']['blended_rps']}")
    print(f"- best_w_dc: {report['p1c']['metrics']['best_w_dc']}")
    print(f"- blocker: {report['p1c']['blocker']}")
    print("")
    print("2. P3-D")
    print(f"- result: {report['p3d']['result']}")
    print(f"- p3_mode: {report['p3d']['source_plan']['p3_mode']}")
    print(f"- requires_xg_xa: {str(report['p3d']['source_plan']['requires_xg_xa']).lower()}")
    print(f"- xg_xa_optional: {str(report['p3d']['source_plan']['xg_xa_optional']).lower()}")
    print(f"- light_required_fields: {_safe(report['p3d']['source_plan']['light_required_fields'])}")
    print(f"- real_csv_exists: {str(report['p3d']['real_csv_validation']['real_csv_exists']).lower()}")
    print(f"- real_performance_csv_exists: {str(report['p3d']['real_csv_validation']['real_performance_csv_exists']).lower()}")
    print(f"- rows_validated: {report['p3d']['real_csv_validation']['rows_validated']}")
    print(f"- performance_rows_validated: {report['p3d']['real_csv_validation']['performance_rows_validated']}")
    print(f"- performance_files: {_safe(report['p3d']['real_csv_validation']['performance_files'])}")
    print(f"- source_coverage: {_safe(report['p3d']['real_csv_validation']['source_coverage'])}")
    print(f"- teams_below_70_percent: {_safe(report['p3d']['feature_readiness']['teams_below_70_percent'])}")
    print(f"- candidate_w_gbm: {report['p3d']['gbm_status']['candidate_w_gbm']}")
    print(f"- production_w_gbm: {report['p3d']['gbm_status']['production_w_gbm']}")
    print(f"- w_gbm: {report['p3d']['gbm_status']['w_gbm']}")
    print(f"- blocker: {report['p3d']['blocker']}")
    print("")
    print("3. Production safety")
    for key, value in report["production_safety"].items():
        print(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}")
    print("")
    print("4. P3 FIFA MatchData gate")
    for key in ("p3_status", "can_enter_shadow", "can_enter_candidate", "can_enter_active_ready", "candidate_w_p3", "production_w_p3", "production_weight_changed"):
        print(f"- {key}: {_safe(report['p3_fifa_gate'][key])}")
    print("")
    print(f"overall_result: {report['overall_result']}")


def _overall_result(p1c: dict[str, Any], p3d: dict[str, Any], safety: dict[str, Any]) -> str:
    if p1c["result"] == "FAIL" or p3d["result"] == "FAIL":
        return "FAIL"
    if safety["betting_enabled"] or safety["gbm_weight"] > 0.2 or safety["would_write_db"] or safety["fake_data_used"]:
        return "FAIL"
    if safety["production_weight_changed"] or safety.get("production_w_p3", 0) != 0:
        return "FAIL"
    if p1c["result"] == "WAIT" or p3d["result"] == "WAIT":
        return "WAIT"
    return "PASS"


def _safe(value: Any) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C/P3-D next phase acceptance")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0 if report["overall_result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
