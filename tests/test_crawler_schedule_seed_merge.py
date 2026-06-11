from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler"))

import db  # noqa: E402
from sources.common import MatchOdds  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.calls: list[tuple[str, tuple | None]] = []
        self._result = None
        self.updated = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "SELECT 1 FROM matches WHERE match_id" in sql:
            self._result = None
        elif "SELECT match_id, home_team, away_team" in sql:
            self._result = [("wc26-001", "Mexico", "South Africa")]
        elif "UPDATE matches" in sql:
            self.updated = True
            self._result = None

    def fetchone(self):
        return self._result

    def fetchall(self):
        return self._result or []


def test_crawler_merges_seed_row_when_500_market_opens() -> None:
    cur = FakeCursor()
    match = MatchOdds(
        match_id="500-1359172",
        match_num="周四001",
        league="世界杯",
        home_team="墨 西 哥 ",
        away_team="南 非 ",
        kickoff_at=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
    )

    db._merge_seed_match_id_if_needed(cur, match)

    assert cur.updated is True
    update_call = [call for call in cur.calls if "UPDATE matches" in call[0]][0]
    assert update_call[1][0] == "500-1359172"
    assert update_call[1][-1] == "wc26-001"
