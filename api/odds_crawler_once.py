from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import requests


ROOT = Path(__file__).resolve().parents[1]
CRAWLER_ROOT = ROOT / "crawler"
if str(CRAWLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CRAWLER_ROOT))

import db  # noqa: E402
from sources import m500  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one safe odds crawler pass.")
    parser.add_argument("--source", default="500", choices=["500", "m500"], help="odds source")
    parser.add_argument("--full-scan", action="store_true", help="scan the configured future 500.com date window")
    parser.add_argument("--days-ahead", type=int, default=None, help="future days to scan for 500.com")
    return parser


def run_once(*, full_scan: bool, days_ahead: int | None) -> dict[str, object]:
    session = requests.Session()
    if full_scan:
        matches = m500.fetch_full_scan(session, days_ahead=days_ahead)
    else:
        matches = m500.fetch_all(session)

    with db.connect() as conn:
        db.init_db(conn)
        run_id = db.start_run(conn, "500")
        try:
            upsert_stats = db.upsert_matches(conn, matches)
            rows_written = db.write_odds_snapshots(conn, matches, m500.SOURCE_NAME)
            max_kickoff = db.max_match_kickoff(conn)
            db.finish_run(conn, run_id, m500.SOURCE_NAME, len(matches), rows_written, True, None)
        except Exception as exc:
            db.finish_run(conn, run_id, m500.SOURCE_NAME, len(matches), 0, False, str(exc))
            raise

    summary = m500.get_last_scan_summary()
    return {
        "source": "500",
        "full_scan": full_scan,
        "matches_seen": len(matches),
        "rows_written": rows_written,
        "new_matches_inserted": upsert_stats["new_matches_inserted"],
        "existing_matches_updated": upsert_stats["existing_matches_updated"],
        "latest_kickoff_seen": summary.get("latest_kickoff_seen"),
        "max_kickoff_in_db_after": max_kickoff.isoformat() if max_kickoff else None,
        "scan_summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_once(full_scan=args.full_scan, days_ahead=args.days_ahead)
    print("Odds Crawler Once Report")
    for key, value in report.items():
        if key == "scan_summary":
            print(f"- {key}: {json.dumps(value, ensure_ascii=False, default=str)}")
        else:
            print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
