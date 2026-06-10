from __future__ import annotations

import argparse

from model.apply_migrations import main as apply_migrations_main
from model.apply_predictions import predict_once
from model.backtest import backtest_market_from_source, print_market_backtest_report
from model.fit_dc import fit_dixon_coles_with_diagnostics, prepare_training_frame
from model.history import download_results
from model.history import load_results
from model.production_checks import production_check
from model.sanity import main as sanity_main
from model.smoke_check import main as smoke_check_main
from model.the_odds_api import (
    MISSING_API_KEY_MESSAGE,
    fetch_validation_odds_cache,
    find_world_cup_sport_keys,
    get_api_key,
    list_historical_sports,
)
from model.train import train_once


def main() -> int:
    parser = argparse.ArgumentParser(description="P1 model command line")
    parser.add_argument("command")
    parser.add_argument("--source", choices=["football_data", "the_odds_api"], default="football_data")
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
    if args.command == "discover-odds-api":
        try:
            api_key = get_api_key()
            sports = list_historical_sports(api_key, as_of_date="2022-11-20T00:00:00Z")
            candidates = find_world_cup_sport_keys(api_key)
        except RuntimeError as exc:
            if str(exc) == MISSING_API_KEY_MESSAGE:
                print(f"ERROR: {exc}")
                return 1
            raise
        print("The Odds API Discovery")
        print("- available soccer historical sport keys:")
        for sport in sports:
            print(f"  - {sport.get('key')}: {sport.get('title')}")
        print(f"- candidate world cup keys: {candidates}")
        print(f"- selected_key: {candidates[0] if candidates else 'no_supported_world_cup_sport_key'}")
        return 0 if candidates else 1
    if args.command == "fetch-validation-odds":
        try:
            matches = load_results()
            report = fetch_validation_odds_cache(matches)
        except RuntimeError as exc:
            if str(exc) == MISSING_API_KEY_MESSAGE:
                print(f"ERROR: {exc}")
                return 1
            raise
        print("The Odds API Validation Odds Fetch")
        print(f"- cache_file: {report.cache_file}")
        print(f"- sport_key: {report.sport_key or 'no_supported_world_cup_sport_key'}")
        print(f"- rows: {report.rows}")
        print(f"- matched_2022_world_cup_matches: {report.matched_matches}")
        print(f"- unmatched_matches: {report.unmatched_matches}")
        print(f"- bookmaker_strategy: {report.bookmaker_strategy}")
        print(f"- snapshots_tried: {report.snapshots_tried}")
        print(f"- api_quota_usage_estimate: {report.quota_usage_estimate}")
        print(f"- unmatched_reasons: {report.unmatched_reasons}")
        return 0 if report.matched_matches >= 30 else 1
    if args.command == "backtest-market":
        matches = load_results()
        matches_with_elo, _ = prepare_training_frame(matches)
        fit_result = fit_dixon_coles_with_diagnostics(matches_with_elo)
        report = backtest_market_from_source(matches_with_elo, fit_result.params, args.source)
        print_market_backtest_report(report)
        return 1 if report.matched_odds_matches < 30 else 0
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
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
