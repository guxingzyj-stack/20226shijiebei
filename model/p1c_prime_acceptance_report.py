from __future__ import annotations

import argparse

from model import p1c_prime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P1-C prime acceptance report")
    parser.parse_args(argv)
    report = p1c_prime.run(dry_run=True)
    p1c_prime.print_report(report)
    return 0 if report["result"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
