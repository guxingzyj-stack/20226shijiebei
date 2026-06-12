from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from model import p3_fifa_readiness


def generate_report(
    data_dir: str | Path | None = None,
    *,
    result_consistency_pass: bool = True,
    ops_health_status: str | None = "OK",
    consecutive_matchdays_ok: bool = False,
    p1c_prime_ready: bool = False,
    p3_feature_eval_not_degrade: bool = False,
    user_approved: bool = False,
) -> dict[str, Any]:
    readiness = p3_fifa_readiness.generate_report(
        data_dir=data_dir,
        result_consistency_pass=result_consistency_pass,
        ops_health_status=ops_health_status,
        consecutive_matchdays_ok=consecutive_matchdays_ok,
        p1c_prime_ready=p1c_prime_ready,
        p3_feature_eval_not_degrade=p3_feature_eval_not_degrade,
        user_approved=user_approved,
    )
    can_enter_shadow = readiness["matches_with_fifa_data"] >= 1 and readiness["player_rows_validated"] > 0
    can_enter_candidate = (
        readiness["matches_with_fifa_data"] >= 16
        and readiness["teams_with_fifa_data"] >= 16
        and readiness["player_rows_validated"] > 0
        and result_consistency_pass
        and str(ops_health_status or "").upper() != "FAIL"
    )
    can_enter_active_ready = (
        can_enter_candidate
        and readiness["matches_with_fifa_data"] >= 32
        and readiness["teams_with_fifa_data"] >= 32
        and consecutive_matchdays_ok
        and p1c_prime_ready
        and p3_feature_eval_not_degrade
        and user_approved
    )
    return {
        "p3_mode": readiness["p3_mode"],
        "p3_status": readiness["p3_status"],
        "can_enter_shadow": can_enter_shadow,
        "can_enter_candidate": can_enter_candidate,
        "can_enter_active_ready": can_enter_active_ready,
        "candidate_w_p3": readiness["candidate_w_p3"],
        "production_w_p3": 0,
        "production_w_gbm": 0,
        "requires_user_approval_before_production_use": readiness["p3_status"] in {"CANDIDATE", "ACTIVE_READY"} or can_enter_active_ready,
        "production_weight_changed": False,
        "blockers": readiness["blockers"],
    }


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("P3 Auto Enable Gate")
    print("")
    for key in (
        "p3_status",
        "can_enter_shadow",
        "can_enter_candidate",
        "can_enter_active_ready",
        "candidate_w_p3",
        "production_w_p3",
        "production_w_gbm",
        "requires_user_approval_before_production_use",
        "production_weight_changed",
        "blockers",
    ):
        print(f"- {key}: {_safe(report.get(key))}")


def _safe(value: Any) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 automatic enable gate")
    parser.parse_args(argv)
    print_report(generate_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
