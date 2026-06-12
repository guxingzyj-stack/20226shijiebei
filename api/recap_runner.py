from __future__ import annotations

import argparse
import json

from api.recap_service import build_match_recap, recap_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P4 post-match recap runner")
    parser.add_argument("--match-id")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    if args.summary:
        _print_summary(recap_summary())
        return 0
    if not args.match_id:
        parser.error("--match-id or --summary is required")
    report = build_match_recap(args.match_id)
    if not report.get("available"):
        print("P4 Match Recap")
        print(f"available: false")
        print(f"reason: {report.get('reason')}")
        return 0
    _print_match(report["recap"])
    return 0


def _print_match(recap: dict) -> None:
    model = recap["model"]
    print("P4 Match Recap")
    print("")
    print(f"Match: {recap['home_team']} {recap['result']['scoreline']} {recap['away_team']}")
    print(f"Market favorite: {recap['market'].get('favorite') or 'unavailable'}")
    print(f"Model predicted: {model.get('predicted_outcome') or 'unavailable'}")
    result = "N/A" if model.get("prediction_correct") is None else "HIT" if model.get("prediction_correct") else "MISS"
    print(f"Prediction result: {result}")
    print(f"EV signals: {recap['ev']['total_ev_signals']}")
    print(f"Settlement: {recap['settlement']['settlement_status']}")


def _print_summary(summary: dict) -> None:
    print("P4 Recap Summary")
    for key, value in summary.items():
        print(f"- {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")


if __name__ == "__main__":
    raise SystemExit(main())
