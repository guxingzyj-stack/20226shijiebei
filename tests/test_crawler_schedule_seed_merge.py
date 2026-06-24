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


class FakeDriftCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, tuple | None]] = []
        self.fetchone_result = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "SELECT 1 FROM matches WHERE match_id" in sql:
            self.fetchone_result = None

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.rows


def _drift_match(match_id: str, source: str) -> MatchOdds:
    return MatchOdds(
        match_id=match_id,
        match_num="周三001",
        league="World Cup",
        home_team="Cape Verde",
        away_team="Saudi Arabia",
        kickoff_at=datetime(2026, 6, 24, 19, 0, tzinfo=timezone.utc),
        match_id_source=source,
    )


def test_crawler_routes_untrusted_500_drift_id_to_existing_identity_match() -> None:
    cur = FakeDriftCursor([("500-1359210", "Cape Verde", "Saudi Arabia")])
    match = _drift_match("500-2040123", "data-id")

    result = db._merge_drifted_500_id_if_needed(cur, match)

    assert result == "merged"
    assert match.match_id == "500-1359210"
    assert match.match_id_source == "identity_match"
    assert match.persistence_skip_reason is None


def test_crawler_skips_untrusted_500_id_without_unique_identity_match() -> None:
    cur = FakeDriftCursor([])
    match = _drift_match("500-2040123", "data-processid")

    result = db._merge_drifted_500_id_if_needed(cur, match)

    assert result == "skipped"
    assert match.match_id == "500-2040123"
    assert match.persistence_skip_reason == "untrusted_500_match_id_without_unique_existing_identity_match"


def test_crawler_does_not_merge_untrusted_500_id_into_seed_row() -> None:
    cur = FakeCursor()
    match = _drift_match("500-2040123", "data-id")

    db._merge_seed_match_id_if_needed(cur, match)

    assert cur.updated is False
