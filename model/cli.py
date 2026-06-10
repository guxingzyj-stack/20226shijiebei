from __future__ import annotations

import argparse

from model.apply_migrations import main as apply_migrations_main
from model.apply_predictions import predict_once
from model.backtest import backtest_with_market_odds, print_market_backtest_report
from model.fit_dc import fit_dixon_coles_with_diagnostics, prepare_training_frame
from model.history import download_results
from model.history import load_results
from model.production_checks import production_check
from model.sanity import main as sanity_main
from model.smoke_check import main as smoke_check_main
from model.train import train_once


def main() -> int:
    parser = argparse.ArgumentParser(description="P1 model command line")
    parser.add_argument(
        "command",
        choices=[
            "apply-migrations",
            "smoke-check",
            "download-history",
            "fit-dc",
            "backtest-market",
            "predict-once",
            "sanity-check",
            "production-check",
        ],
    )
    args = parser.parse_args()
    if args.command == "apply-migrations":
        return apply_migrations_main()
    if args.command == "smoke-check":
        return smoke_check_main()
    if args.command == "download-history":
        path = download_results()
        print(f"downloaded: {path}")
        return 0
    if args.command == "fit-dc":
        try:
            print(train_once())
            return 0
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 1
    if args.command == "backtest-market":
        matches = load_results()
        matches_with_elo, _ = prepare_training_frame(matches)
        fit_result = fit_dixon_coles_with_diagnostics(matches_with_elo)
        report = backtest_with_market_odds(matches_with_elo, fit_result.params)
        print_market_backtest_report(report)
        return 1 if report.matched_odds_matches == 0 else 0
    if args.command == "predict-once":
        try:
            print(predict_once())
            return 0
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 1
    if args.command == "sanity-check":
        return sanity_main()
    if args.command == "production-check":
        return production_check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
