from __future__ import annotations

import argparse
from typing import Any

from model import p3_data_audit, p3_ingest, p3_train


def generate_report(dry_run: bool = True) -> dict[str, Any]:
    validation = p3_ingest.validate_real(dry_run=True)
    features = p3_ingest.build_team_features_real(dry_run=dry_run)
    gbm = p3_train.train(dry_run=True, sample=False)
    source_coverage = _source_coverage(validation)
    data_audit = p3_data_audit.generate_report()
    report = {
        "source_plan": {
            "mode": "manual_real_csv_first",
            "external_scraping_enabled": False,
            "full_production_import_enabled": False,
        },
        "real_csv_validation": {
            "status": validation["status"],
            "real_csv_exists": validation["real_csv_exists"],
            "rows_validated": validation["rows_validated"],
            "validation_errors": _validation_errors(validation),
            "source_coverage": source_coverage,
            "retrieved_at_coverage": validation["retrieved_at_coverage"],
            "confidence_valid": validation["confidence_valid"],
            "would_write_db": False,
        },
        "feature_readiness": {
            "status": features["status"],
            "teams": features["teams"],
            "feature_preview": features["feature_preview"],
            "missing_indicators": features["missing_indicators"],
            "performance_coverage": features.get("performance_coverage", {}),
            "gbm_ready": features.get("gbm_ready", False),
            "would_write_db": features.get("would_write_db", False),
        },
        "data_audit": {
            "result": data_audit["result"],
            "blocker": data_audit["blocker"],
            "summary": data_audit["summary"],
            "next_backlog": data_audit["next_backlog"][:20],
        },
        "gbm_status": {
            "status": _gbm_status(features, gbm, dry_run=dry_run),
            "lightgbm_available": gbm.get("lightgbm_available", False),
            "w_gbm": features.get("w_gbm", 0),
            "affects_p1_predictions": False,
        },
    }
    report["blocker"] = _blocker(report)
    report["result"] = _result(report)
    return report


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("P3-D Real Data Readiness Report")
    print("")
    print("1. Source plan")
    print(f"- mode: {report['source_plan']['mode']}")
    print(f"- external_scraping_enabled: {str(report['source_plan']['external_scraping_enabled']).lower()}")
    print(f"- full_production_import_enabled: {str(report['source_plan']['full_production_import_enabled']).lower()}")
    print("")
    print("2. Real CSV validation")
    print(f"- status: {report['real_csv_validation']['status']}")
    print(f"- real_csv_exists: {str(report['real_csv_validation']['real_csv_exists']).lower()}")
    print(f"- rows_validated: {report['real_csv_validation']['rows_validated']}")
    print(f"- validation_errors: {_safe(report['real_csv_validation']['validation_errors'])}")
    print(f"- source_coverage: {_safe(report['real_csv_validation']['source_coverage'])}")
    print(f"- retrieved_at_coverage: {_safe(report['real_csv_validation']['retrieved_at_coverage'])}")
    print(f"- confidence_valid: {str(report['real_csv_validation']['confidence_valid']).lower()}")
    print(f"- would_write_db: {str(report['real_csv_validation']['would_write_db']).lower()}")
    print("")
    print("3. Feature readiness")
    print(f"- status: {report['feature_readiness']['status']}")
    print(f"- teams: {_safe(report['feature_readiness']['teams'])}")
    print(f"- missing_indicators: {_safe(report['feature_readiness']['missing_indicators'])}")
    print(f"- performance_coverage: {_safe(report['feature_readiness']['performance_coverage'])}")
    print(f"- gbm_ready: {str(report['feature_readiness']['gbm_ready']).lower()}")
    print(f"- would_write_db: {str(report['feature_readiness']['would_write_db']).lower()}")
    print("")
    print("4. GBM status")
    print(f"- lightgbm_available: {str(report['gbm_status']['lightgbm_available']).lower()}")
    print(f"- status: {report['gbm_status']['status']}")
    print(f"- w_gbm: {report['gbm_status']['w_gbm']}")
    print(f"- affects_p1_predictions: {str(report['gbm_status']['affects_p1_predictions']).lower()}")
    print("")
    print("5. Data audit")
    print(f"- result: {report['data_audit']['result']}")
    print(f"- blocker: {report['data_audit']['blocker']}")
    print(f"- summary: {_safe(report['data_audit']['summary'])}")
    print(f"- next_backlog_count_shown: {len(report['data_audit']['next_backlog'])}")
    print("")
    print(f"- blocker: {report['blocker']}")
    print(f"result: {report['result']}")


def _validation_errors(validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, detail in validation["details"].items():
        errors.extend(f"{name}: missing column {column}" for column in detail.get("missing_columns", []))
        errors.extend(detail.get("errors", []))
    return errors


def _safe(value: Any) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _source_coverage(validation: dict[str, Any]) -> dict[str, int]:
    return {name: int(detail.get("rows", 0)) for name, detail in validation["details"].items()}


def _blocker(report: dict[str, Any]) -> str | None:
    if report["real_csv_validation"]["validation_errors"]:
        return "real CSV validation failed"
    if report["real_csv_validation"]["rows_validated"] == 0:
        return "no_real_data_csv"
    if report["data_audit"]["result"] != "PASS":
        return str(report["data_audit"]["blocker"] or "player_data_audit_wait")
    if not report["feature_readiness"]["gbm_ready"]:
        return "gbm_coverage_below_threshold"
    return None


def _result(report: dict[str, Any]) -> str:
    if report["real_csv_validation"]["validation_errors"]:
        return "FAIL"
    if report["gbm_status"]["w_gbm"] not in (0, 0.2) or report["gbm_status"]["affects_p1_predictions"]:
        return "FAIL"
    if report["real_csv_validation"]["rows_validated"] == 0:
        return "WAIT"
    if report["data_audit"]["result"] != "PASS":
        return "WAIT"
    if not report["feature_readiness"]["gbm_ready"]:
        return "WAIT"
    return "PASS"


def _gbm_status(features: dict[str, Any], gbm: dict[str, Any], dry_run: bool) -> str:
    if not features.get("gbm_ready"):
        return "coverage_below_threshold"
    if dry_run:
        return "gbm_gray_ready_dry_run"
    if not gbm.get("lightgbm_available", False):
        return "gbm_gray_weight_ready_lightgbm_unavailable"
    return "gbm_gray_weight_ready"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3-D real data readiness report")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args(argv)
    report = generate_report(dry_run=args.dry_run)
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
