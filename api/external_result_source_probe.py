from __future__ import annotations

import argparse
import sys

from api.external_result_sources import discover_fifa_urls, print_probe_report, probe_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="probe structured external result sources")
    parser.add_argument("--source", choices=("thesportsdb", "fifa"), required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--discover-url", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)

    if args.discover_url:
        if args.source != "fifa":
            print("ERROR: --discover-url is only supported for --source fifa", file=sys.stderr)
            return 2
        report = discover_fifa_urls(args.date, limit=args.limit)
    else:
        report = probe_source(args.source, args.date)
    print_probe_report(report)
    return 0 if report["source_fetch_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
