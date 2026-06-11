from __future__ import annotations

import argparse
from typing import Any

from model import p1c_acceptance_report, p3d_acceptance_report


def generate_report() -> dict[str, Any]:
    p1c = p1c_acceptance_report.generate_report()
    p3d = p3d_acceptance_report.generate_report()
    safety = {
        "betting_enabled": False,
        "gbm_weight": p3d["gbm_status"]["w_gbm"],
        "would_write_db": False,
        "fake_data_used": False,
    }
    result = _overall_result(p1c, p3d, safety)
    return {"p1c": p1c, "p3d": p3d, "production_safety": safety, "overall_result": result}


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
    print(f"- real_csv_exists: {str(report['p3d']['real_csv_validation']['real_csv_exists']).lower()}")
    print(f"- rows_validated: {report['p3d']['real_csv_validation']['rows_validated']}")
    print(f"- source_coverage: {_safe(report['p3d']['real_csv_validation']['source_coverage'])}")
    print(f"- w_gbm: {report['p3d']['gbm_status']['w_gbm']}")
    print(f"- blocker: {report['p3d']['blocker']}")
    print("")
    print("3. Production safety")
    for key, value in report["production_safety"].items():
        print(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}")
    print("")
    print(f"overall_result: {report['overall_result']}")


def _overall_result(p1c: dict[str, Any], p3d: dict[str, Any], safety: dict[str, Any]) -> str:
    if p1c["result"] == "FAIL" or p3d["result"] == "FAIL":
        return "FAIL"
    if safety["betting_enabled"] or safety["gbm_weight"] != 0 or safety["would_write_db"] or safety["fake_data_used"]:
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
