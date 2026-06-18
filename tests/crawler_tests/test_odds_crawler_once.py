from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_crawler_odds_crawler_once_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "crawler.odds_crawler_once", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "--full-scan" in result.stdout


def test_crawler_odds_crawler_once_does_not_import_api() -> None:
    source = (ROOT / "crawler" / "odds_crawler_once.py").read_text(encoding="utf-8")

    assert "import api" not in source
    assert "from api" not in source


def test_crawler_odds_crawler_once_full_scan_calls_m500(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "crawler"))
    from crawler import odds_crawler_once
    from sources.common import MatchOdds, OddsEntry

    calls: dict[str, object] = {}

    def fake_fetch_full_scan(session, days_ahead=None):  # noqa: ANN001
        calls["days_ahead"] = days_ahead
        match = MatchOdds(
            match_id="500-999",
            match_num="001",
            league="World Cup",
            home_team="A",
            away_team="B",
            kickoff_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            odds=[OddsEntry(play_type="had", odds={"3": 2.0, "1": 3.0, "0": 4.0})],
        )
        return [match]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    monkeypatch.setattr(odds_crawler_once.m500, "fetch_full_scan", fake_fetch_full_scan)
    monkeypatch.setattr(odds_crawler_once.m500, "get_last_scan_summary", lambda: {"raw_events_seen": 1, "parsed_matches_seen": 1})
    monkeypatch.setattr(odds_crawler_once.db, "connect", lambda: FakeConn())
    monkeypatch.setattr(odds_crawler_once.db, "init_db", lambda conn: None)
    monkeypatch.setattr(odds_crawler_once.db, "start_run", lambda conn, source: 123)
    monkeypatch.setattr(
        odds_crawler_once.db,
        "upsert_matches",
        lambda conn, matches: {"new_matches_inserted": 1, "existing_matches_updated": 0},
    )
    monkeypatch.setattr(odds_crawler_once.db, "write_odds_snapshots", lambda conn, matches, source: 1)
    monkeypatch.setattr(odds_crawler_once.db, "max_match_kickoff", lambda conn: datetime(2026, 6, 20, tzinfo=timezone.utc))
    monkeypatch.setattr(odds_crawler_once.db, "finish_run", lambda *args, **kwargs: None)

    report = odds_crawler_once.run_once(full_scan=True, days_ahead=5)

    assert calls["days_ahead"] == 5
    assert report["new_matches_inserted"] == 1
    assert report["odds_rows_written"] == 1
