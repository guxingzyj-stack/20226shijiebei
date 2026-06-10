from __future__ import annotations

import psycopg

from model.config import get_database_url
from model.db import fetch_latest_odds_snapshots, fetch_upcoming_matches


def smoke_check() -> int:
    try:
        database_url = get_database_url()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    try:
        with psycopg.connect(database_url) as conn:
            matches_count = conn.execute("SELECT count(*) FROM matches").fetchone()[0]
            snapshots_count = conn.execute("SELECT count(*) FROM odds_snapshots").fetchone()[0]
            latest_snapshots = fetch_latest_odds_snapshots(conn, 5)
            upcoming_matches = fetch_upcoming_matches(conn)
    except Exception as exc:
        print(f"ERROR: database smoke check failed: {exc}")
        return 1
    print(f"matches count: {matches_count}")
    print(f"odds_snapshots count: {snapshots_count}")
    print("latest odds snapshots:")
    for row in latest_snapshots:
        print(f"  {row['match_id']} {row['play_type']} {row['fetched_at']}")
    print(f"upcoming scheduled matches count: {len(upcoming_matches)}")
    return 0


def main() -> int:
    return smoke_check()


if __name__ == "__main__":
    raise SystemExit(main())
