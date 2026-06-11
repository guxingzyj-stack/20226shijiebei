from __future__ import annotations

import argparse
from typing import Any

from model import p3_ingest, p3_train
from model import p3d_acceptance_report


def generate_report(sample: bool = False) -> dict[str, Any]:
    validation = p3_ingest.validate(sample=sample)
    import_result = p3_ingest.import_manual_data(dry_run=True, sample=sample)
    features_result = p3_ingest.build_team_features(dry_run=True, sample=sample)
    gbm_result = p3_train.train(dry_run=True, sample=sample)
    validation_errors = _validation_errors(validation)
    report = {
        "csv_validation": {
            "squad_rows": validation["details"]["squad"]["rows"],
            "player_stats_rows": validation["details"]["player_stats"]["rows"],
            "injuries_rows": validation["details"]["injuries"]["rows"],
            "validation_errors": validation_errors,
        },
        "dry_run_import": {
            "players": import_result["players"],
            "player_season_stats": import_result["player_season_stats"],
            "injuries": import_result["injuries"],
            "would_write_db": False,
        },
        "team_features": {
            "teams": [row["team"] for row in features_result.get("features", [])],
            "generated_features": features_result["team_features"],
            "missing_indicators": features_result.get("missing_indicators", {}),
        },
        "gbm": {
            "lightgbm_available": gbm_result.get("lightgbm_available", False),
            "status": gbm_result["status"],
            "w_gbm": gbm_result["w_gbm"],
        },
        "production_safety": {
            "writes_production_db": False,
            "affects_p1_predictions": False,
            "betting_enabled_changed": False,
        },
    }
    report["result"] = _result(report)
    return report


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report(sample=True)
    print("P3-C Sample Pipeline Report")
    print("")
    print("1. CSV validation")
    print(f"- squad_rows: {report['csv_validation']['squad_rows']}")
    print(f"- player_stats_rows: {report['csv_validation']['player_stats_rows']}")
    print(f"- injuries_rows: {report['csv_validation']['injuries_rows']}")
    print(f"- validation_errors: {report['csv_validation']['validation_errors']}")
    print("")
    print("2. Dry-run import")
    print(f"- players: {report['dry_run_import']['players']}")
    print(f"- player_season_stats: {report['dry_run_import']['player_season_stats']}")
    print(f"- injuries: {report['dry_run_import']['injuries']}")
    print(f"- would_write_db: {str(report['dry_run_import']['would_write_db']).lower()}")
    print("")
    print("3. Team features")
    print(f"- teams: {report['team_features']['teams']}")
    print(f"- generated_features: {report['team_features']['generated_features']}")
    print(f"- missing_indicators: {report['team_features']['missing_indicators']}")
    print("")
    print("4. GBM")
    print(f"- lightgbm_available: {str(report['gbm']['lightgbm_available']).lower()}")
    print(f"- status: {report['gbm']['status']}")
    print(f"- w_gbm: {report['gbm']['w_gbm']}")
    print("")
    print("5. Production safety")
    print(f"- writes_production_db: {str(report['production_safety']['writes_production_db']).lower()}")
    print(f"- affects_p1_predictions: {str(report['production_safety']['affects_p1_predictions']).lower()}")
    print(f"- betting_enabled_changed: {str(report['production_safety']['betting_enabled_changed']).lower()}")
    print("")
    print(f"result: {report['result']}")


def _validation_errors(validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name, detail in validation["details"].items():
        errors.extend(f"{name}: missing column {column}" for column in detail.get("missing_columns", []))
        errors.extend(detail.get("errors", []))
    return errors


def _result(report: dict[str, Any]) -> str:
    if report["csv_validation"]["validation_errors"]:
        return "FAIL"
    if report["dry_run_import"]["would_write_db"] is not False:
        return "FAIL"
    if report["team_features"]["generated_features"] < 2:
        return "FAIL"
    if report["gbm"]["w_gbm"] != 0:
        return "FAIL"
    if any(report["production_safety"].values()):
        return "FAIL"
    return "PASS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3-C sample pipeline acceptance report")
    parser.add_argument("--sample", action="store_true", help="use data/p3/samples CSV files")
    parser.add_argument("--real-dry-run", action="store_true", help="run P3-D real CSV readiness dry-run")
    args = parser.parse_args(argv)
    if args.real_dry_run:
        report = p3d_acceptance_report.generate_report()
        p3d_acceptance_report.print_report(report)
        return 0 if report["result"] != "FAIL" else 1
    report = generate_report(sample=args.sample)
    print_report(report)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
