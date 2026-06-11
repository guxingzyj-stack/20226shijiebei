from __future__ import annotations

import argparse
from typing import Any

from model import p3_ingest, p3_train


def generate_report() -> dict[str, Any]:
    validation = p3_ingest.validate_real(dry_run=True)
    features = p3_ingest.build_team_features_real(dry_run=True)
    gbm = p3_train.train(dry_run=True, sample=False)
    source_coverage = _source_coverage(validation)
    report = {
        "source_plan": {
            "mode": "manual_real_csv_first",
            "external_scraping_enabled": False,
            "full_production_import_enabled": False,
        },
        "real_csv_validation": {
            "status": validation["status"],
            "rows_validated": validation["rows_validated"],
            "validation_errors": _validation_errors(validation),
            "source_coverage": source_coverage,
            "would_write_db": False,
        },
        "feature_readiness": {
            "status": features["status"],
            "teams": features["teams"],
            "feature_preview": features["feature_preview"],
            "missing_indicators": features["missing_indicators"],
        },
        "gbm_status": {
            "status": "disabled_for_p3d_dry_run",
            "lightgbm_available": gbm.get("lightgbm_available", False),
            "w_gbm": 0,
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
    print(f"- rows_validated: {report['real_csv_validation']['rows_validated']}")
    print(f"- validation_errors: {report['real_csv_validation']['validation_errors']}")
    print(f"- source_coverage: {report['real_csv_validation']['source_coverage']}")
    print(f"- would_write_db: {str(report['real_csv_validation']['would_write_db']).lower()}")
    print("")
    print("3. Feature readiness")
    print(f"- status: {report['feature_readiness']['status']}")
    print(f"- teams: {report['feature_readiness']['teams']}")
    print(f"- missing_indicators: {report['feature_readiness']['missing_indicators']}")
    print("")
    print("4. GBM status")
    print(f"- lightgbm_available: {str(report['gbm_status']['lightgbm_available']).lower()}")
    print(f"- status: {report['gbm_status']['status']}")
    print(f"- w_gbm: {report['gbm_status']['w_gbm']}")
    print(f"- affects_p1_predictions: {str(report['gbm_status']['affects_p1_predictions']).lower()}")
    print("")
    print(f"- blocker: {report['blocker']}")
    print(f"result: {report['result']}")


def _validation_errors(validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, detail in validation["details"].items():
        errors.extend(f"{name}: missing column {column}" for column in detail.get("missing_columns", []))
        errors.extend(detail.get("errors", []))
    return errors


def _source_coverage(validation: dict[str, Any]) -> dict[str, int]:
    return {name: int(detail.get("rows", 0)) for name, detail in validation["details"].items()}


def _blocker(report: dict[str, Any]) -> str | None:
    if report["real_csv_validation"]["validation_errors"]:
        return "real CSV validation failed"
    if report["real_csv_validation"]["rows_validated"] == 0:
        return "no_real_data_csv"
    return None


def _result(report: dict[str, Any]) -> str:
    if report["real_csv_validation"]["validation_errors"]:
        return "FAIL"
    if report["gbm_status"]["w_gbm"] != 0 or report["gbm_status"]["affects_p1_predictions"]:
        return "FAIL"
    if report["real_csv_validation"]["rows_validated"] == 0:
        return "WAIT"
    return "PASS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3-D real data readiness report")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
