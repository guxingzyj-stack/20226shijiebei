from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from api.db import connect


TARGET_FINISHED_MATCHES = 30


def generate_report(target_finished_matches: int = TARGET_FINISHED_MATCHES) -> dict[str, Any]:
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE status IN ('finished', 'completed')
                  AND result_home IS NOT NULL
                  AND result_away IS NOT NULL
              ) AS usable_finished_matches,
              count(*) FILTER (WHERE status IN ('finished', 'completed')) AS finished_matches,
              count(*) FILTER (
                WHERE status IN ('finished', 'completed')
                  AND (result_home IS NULL OR result_away IS NULL)
              ) AS finished_missing_result,
              count(*) FILTER (
                WHERE status NOT IN ('finished', 'completed')
                  AND result_home IS NOT NULL
                  AND result_away IS NOT NULL
              ) AS non_finished_with_result
            FROM matches
            """
        )
        row = dict(cur.fetchone())
    usable = int(row["usable_finished_matches"] or 0)
    return {
        "mode": "read-only",
        "writes_db": False,
        "usable_finished_matches": usable,
        "finished_matches": int(row["finished_matches"] or 0),
        "finished_missing_result": int(row["finished_missing_result"] or 0),
        "non_finished_with_result": int(row["non_finished_with_result"] or 0),
        "target_finished_matches": target_finished_matches,
        "remaining_to_p1c_prime": max(target_finished_matches - usable, 0),
        "p1c_ready": usable >= target_finished_matches,
    }


def print_report(report: dict[str, Any]) -> None:
    print("P1-C Prime Readiness Report")
    for key in (
        "mode",
        "writes_db",
        "usable_finished_matches",
        "finished_matches",
        "finished_missing_result",
        "non_finished_with_result",
        "target_finished_matches",
        "remaining_to_p1c_prime",
        "p1c_ready",
    ):
        print(f"- {key}: {report.get(key)}")


def main() -> int:
    report = generate_report()
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
