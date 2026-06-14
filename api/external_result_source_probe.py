from __future__ import annotations

import argparse
import sys

from api.external_result_sources import print_probe_report, probe_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="probe structured external result sources")
    parser.add_argument("--source", choices=("thesportsdb", "fifa"), required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)

    report = probe_source(args.source, args.date)
    print_probe_report(report)
    return 0 if report["source_fetch_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
