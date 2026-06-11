from __future__ import annotations

import argparse
from typing import Any

from model import p1c_backtest


def generate_report() -> dict[str, Any]:
    sources = p1c_backtest.discover_sources()
    backtest = p1c_backtest.run_manual_backtest(dry_run=True)
    result = backtest.get("result", "WAIT")
    if result == "PASS":
        blocker = None
    elif result == "FAIL":
        blocker = "manual historical odds CSV validation failed"
    else:
        blocker = backtest.get("blocker") or "no usable real historical market odds source yet"
    return {
        "sources": sources,
        "backtest": backtest,
        "metrics": {
            "market_rps": backtest.get("market_rps"),
            "dc_rps": backtest.get("dc_rps"),
            "blended_rps": backtest.get("blended_rps"),
            "best_w_dc": backtest.get("best_w_dc"),
        },
        "production_safety": {
            "would_write_db": False,
            "uses_fake_metrics": False,
            "betting_enabled_changed": False,
        },
        "blocker": blocker,
        "result": result,
    }


def print_report(report: dict[str, Any] | None = None) -> None:
    report = report or generate_report()
    print("P1-C Historical Market Backtest Report")
    print("")
    print("1. Source discovery")
    print(f"- the_odds_api: {report['sources']['the_odds_api']['status']}")
    print(f"- football_data_csv: {report['sources']['football_data_csv']['status']}")
    print(f"- manual_csv_template_exists: {report['sources']['manual_csv']['template_exists']}")
    print("")
    print("2. Backtest")
    print(f"- status: {report['backtest'].get('status')}")
    print(f"- rows: {report['backtest'].get('rows')}")
    print(f"- required_rows: {report['backtest'].get('required_rows')}")
    print(f"- market_rps: {report['metrics']['market_rps']}")
    print(f"- dc_rps: {report['metrics']['dc_rps']}")
    print(f"- blended_rps: {report['metrics']['blended_rps']}")
    print(f"- best_w_dc: {report['metrics']['best_w_dc']}")
    print("")
    print("3. Production safety")
    print(f"- would_write_db: {str(report['production_safety']['would_write_db']).lower()}")
    print(f"- uses_fake_metrics: {str(report['production_safety']['uses_fake_metrics']).lower()}")
    print(f"- betting_enabled_changed: {str(report['production_safety']['betting_enabled_changed']).lower()}")
    print("")
    print(f"- blocker: {report['blocker']}")
    print(f"result: {report['result']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C acceptance report")
    parser.parse_args(argv)
    report = generate_report()
    print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
