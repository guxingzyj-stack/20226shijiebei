from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EV_RESEARCH_ONLY_THRESHOLD = 0.15


def summarize(mexico_path: Path, germany_path: Path, leaderboard_path: Path) -> dict[str, Any]:
    try:
        leaderboard = _load_json(leaderboard_path)
        mexico = _load_json(mexico_path)
        germany = _load_json(germany_path)
    except Exception as exc:
        return {"result": "FAIL", "error": f"{type(exc).__name__}: {exc}"}

    leaderboard_summary = summarize_leaderboard(leaderboard)
    mexico_summary = summarize_match(mexico)
    germany_summary = summarize_match(germany)
    result = result_for(leaderboard_summary, mexico_summary, germany_summary)
    return {
        "leaderboard": leaderboard_summary,
        "mexico": mexico_summary,
        "germany": germany_summary,
        "result": result,
    }


def summarize_leaderboard(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    return {
        "has_roi": any(isinstance(row, dict) and ("roi" in row or "ROI" in row) for row in rows),
        "exposes_internal_id": any(isinstance(row, dict) and "id" in row for row in rows),
        "user_count": len(rows),
        "test_user_count": sum(1 for row in rows if isinstance(row, dict) and _is_test_username(str(row.get("username", "")))),
    }


def summarize_match(payload: dict[str, Any]) -> dict[str, Any]:
    prediction = payload.get("latest_prediction") or {}
    model_version = prediction.get("model_version")
    ev_signals = payload.get("ev_signals") or []
    prediction_status = payload.get("prediction_status")
    ev_aligned = all(signal.get("model_version") == model_version for signal in ev_signals if model_version is not None)
    unprotected_high_ev = [
        signal
        for signal in ev_signals
        if _float(signal.get("ev")) > EV_RESEARCH_ONLY_THRESHOLD
        and signal.get("research_only") is not True
        and signal.get("suggestion_eligible") is not False
    ]
    return {
        "match_id": payload.get("match_id"),
        "prediction_status": prediction_status,
        "model_version": model_version,
        "ev_count": len(ev_signals),
        "ev_model_version_aligned": ev_aligned,
        "unprotected_high_ev_count": len(unprotected_high_ev),
    }


def result_for(leaderboard: dict[str, Any], mexico: dict[str, Any], germany: dict[str, Any]) -> str:
    if leaderboard["exposes_internal_id"]:
        return "FAIL"
    if not mexico["ev_model_version_aligned"] or not germany["ev_model_version_aligned"]:
        return "FAIL"
    if mexico["unprotected_high_ev_count"] > 0 or germany["unprotected_high_ev_count"] > 0:
        return "FAIL"
    if leaderboard["test_user_count"] > 0:
        return "WARN"
    if _prediction_unavailable(mexico["prediction_status"]) or _prediction_unavailable(germany["prediction_status"]):
        return "WARN"
    if mexico["ev_count"] == 0 or germany["ev_count"] == 0:
        return "WARN"
    return "PASS"


def print_summary(summary: dict[str, Any]) -> None:
    print("Production Probe Summary")
    if "error" in summary:
        print(f"- error: {summary['error']}")
        print("")
        print("result: FAIL")
        return
    leaderboard = summary["leaderboard"]
    mexico = summary["mexico"]
    germany = summary["germany"]
    print("")
    print("1. leaderboard")
    print(f"- has_roi: {leaderboard['has_roi']}")
    print(f"- exposes_internal_id: {leaderboard['exposes_internal_id']}")
    print(f"- user_count: {leaderboard['user_count']}")
    print(f"- test_user_count: {leaderboard['test_user_count']}")
    print("")
    print("2. Mexico")
    print(f"- match_id: {mexico['match_id']}")
    print(f"- prediction_status: {mexico['prediction_status']}")
    print(f"- model_version: {mexico['model_version']}")
    print(f"- ev_count: {mexico['ev_count']}")
    print(f"- ev_model_version_aligned: {mexico['ev_model_version_aligned']}")
    print(f"- unprotected_high_ev_count: {mexico['unprotected_high_ev_count']}")
    print("")
    print("3. Germany")
    print(f"- match_id: {germany['match_id']}")
    print(f"- prediction_status: {germany['prediction_status']}")
    print(f"- model_version: {germany['model_version']}")
    print(f"- ev_count: {germany['ev_count']}")
    print(f"- ev_model_version_aligned: {germany['ev_model_version_aligned']}")
    print("")
    print(f"result: {summary['result']}")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_test_username(username: str) -> bool:
    return username.startswith("test_user_") or username.startswith("codex_blocker_")


def _prediction_unavailable(status: Any) -> bool:
    return isinstance(status, dict) and status.get("available") is False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize saved production probe JSON files")
    parser.add_argument("--mexico", required=True, type=Path)
    parser.add_argument("--germany", required=True, type=Path)
    parser.add_argument("--leaderboard", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = summarize(args.mexico, args.germany, args.leaderboard)
    print_summary(summary)
    return 0 if summary.get("result") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
