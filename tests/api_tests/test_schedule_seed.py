from __future__ import annotations

from datetime import datetime, timezone

from api import schedule_seed


def test_schedule_seed_contains_104_matches() -> None:
    rows = schedule_seed.load_schedule_rows()

    assert len(rows) == 104
    assert rows[0].match_id == "wc26-001"
    assert rows[0].home_team == "Mexico"
    assert rows[0].away_team == "South Africa"
    assert rows[0].kickoff_at == datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
    assert rows[-1].match_id == "wc26-104"
    assert rows[-1].stage == "Final"
    assert schedule_seed.validate_schedule_rows(rows) == []


def test_schedule_seed_import_requires_confirm(monkeypatch) -> None:
    monkeypatch.setattr(schedule_seed, "connect", lambda: None)

    report = schedule_seed.run_import(dry_run=False, confirm=None)

    assert report["ok"] is False
    assert "IMPORT_WC26_SCHEDULE" in report["errors"][0]


def test_schedule_seed_plan_matches_existing_500_row() -> None:
    rows = schedule_seed.load_schedule_rows()[:2]
    existing = [
        {
            "match_id": "500-1359172",
            "home_team": "墨 西 哥 ",
            "away_team": "南 非 ",
            "kickoff_at": rows[0].kickoff_at,
            "status": "closed",
        }
    ]

    plan = schedule_seed.build_import_plan(rows, existing)

    assert plan["would_update_existing"] == 1
    assert plan["would_insert"] == 1
    assert plan["equivalent_matches"] == [{"seed_match_id": "wc26-001", "existing_match_id": "500-1359172"}]


def test_canonical_team_handles_current_chinese_spacing() -> None:
    assert schedule_seed._canonical_team("墨 西 哥 ") == "mexico"
    assert schedule_seed._canonical_team("South Africa") == schedule_seed._canonical_team("南非")
