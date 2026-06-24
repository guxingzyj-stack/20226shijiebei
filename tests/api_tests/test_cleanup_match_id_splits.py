from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api import cleanup_match_id_splits as cleanup


def _match(match_id: str, home: str = "Cape Verde", away: str = "Saudi Arabia") -> dict:
    return {
        "match_id": match_id,
        "match_num": "TEST001",
        "league": "World Cup",
        "home_team": home,
        "away_team": away,
        "kickoff_at": datetime(2026, 6, 24, 19, 0, tzinfo=timezone.utc),
        "status": "scheduled",
        "result_home": None,
        "result_away": None,
        "ht_home": None,
        "ht_away": None,
    }


def test_build_split_plans_selects_single_1359_id_as_protected() -> None:
    plans = cleanup._build_split_plans([
        _match("500-1359210"),
        _match("500-2040123"),
        _match("500--1"),
    ])

    assert len(plans) == 1
    assert plans[0]["correct_id"] == "500-1359210"
    assert plans[0]["dirty_ids"] == ["500--1", "500-2040123"]
    assert plans[0]["errors"] == []


def test_build_split_plans_blocks_group_without_unique_protected_id() -> None:
    plans = cleanup._build_split_plans([
        _match("500-2040123"),
        _match("500-2040456"),
    ])

    assert plans[0]["correct_id"] is None
    assert "no unique protected" in plans[0]["errors"][0]


def test_validate_state_refuses_dirty_bet_references() -> None:
    state = {
        "plans": [{"correct_id": "500-1359210", "dirty_ids": ["500-2040123"], "errors": []}],
        "dirty_ids": ["500-2040123"],
        "bets_by_dirty_id": {"500-2040123": 1},
        "correct_pre_kickoff_predictions": {"500-1359210": 2},
    }

    errors = cleanup.validate_state(state, require_dirty=True)

    assert any("bets reference dirty match_id 500-2040123" in error for error in errors)


def test_validate_state_requires_correct_pre_kickoff_prediction() -> None:
    state = {
        "plans": [{"correct_id": "500-1359210", "dirty_ids": ["500-2040123"], "errors": []}],
        "dirty_ids": ["500-2040123"],
        "bets_by_dirty_id": {"500-2040123": 0},
        "correct_pre_kickoff_predictions": {"500-1359210": 0},
    }

    errors = cleanup.validate_state(state, require_dirty=True)

    assert any("has no pre-kickoff prediction" in error for error in errors)


def test_verify_after_delete_allows_split_to_disappear_when_tracked_correct_prediction_remains() -> None:
    before = {
        "plans": [{"correct_id": "500-1359210", "dirty_ids": ["500-2040123"], "errors": []}],
        "dirty_ids": ["500-2040123"],
        "script_predictions_count": 72,
    }
    after = {
        "plans": [],
        "dirty_ids": ["500-2040123"],
        "dirty_counts": {"500-2040123": {table: 0 for table in cleanup.MATCH_ID_TABLES}},
        "correct_matches": {"500-1359210": _match("500-1359210")},
        "correct_pre_kickoff_predictions": {"500-1359210": 112},
        "script_predictions_count": 72,
    }

    assert cleanup._verify_after_delete(after, before) == []


def test_verify_after_delete_still_rejects_missing_tracked_correct_prediction() -> None:
    before = {
        "plans": [{"correct_id": "500-1359210", "dirty_ids": ["500-2040123"], "errors": []}],
        "dirty_ids": ["500-2040123"],
        "script_predictions_count": 72,
    }
    after = {
        "plans": [],
        "dirty_ids": ["500-2040123"],
        "dirty_counts": {"500-2040123": {table: 0 for table in cleanup.MATCH_ID_TABLES}},
        "correct_matches": {"500-1359210": _match("500-1359210")},
        "correct_pre_kickoff_predictions": {"500-1359210": 0},
        "script_predictions_count": 72,
    }

    errors = cleanup._verify_after_delete(after, before)

    assert "correct match 500-1359210 lost pre-kickoff predictions" in errors


def test_verify_after_delete_still_rejects_dirty_id_residue() -> None:
    before = {
        "plans": [{"correct_id": "500-1359210", "dirty_ids": ["500-2040123"], "errors": []}],
        "dirty_ids": ["500-2040123"],
        "script_predictions_count": 72,
    }
    after = {
        "plans": [],
        "dirty_ids": ["500-2040123"],
        "dirty_counts": {
            "500-2040123": {
                **{table: 0 for table in cleanup.MATCH_ID_TABLES},
                "odds_snapshots": 1,
            }
        },
        "correct_matches": {"500-1359210": _match("500-1359210")},
        "correct_pre_kickoff_predictions": {"500-1359210": 112},
        "script_predictions_count": 72,
    }

    errors = cleanup._verify_after_delete(after, before)

    assert "odds_snapshots still has 1 rows for 500-2040123" in errors


class _TrackedStateCursor:
    def __init__(self):
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params

    def fetchone(self):
        if "to_regclass" in self.sql:
            return {"table_name": "public.table"}
        if "FROM predictions" in self.sql:
            return {"count": 112}
        if "FROM bets" in self.sql:
            return {"count": 0}
        if "FROM script_predictions" in self.sql:
            return {"count": 72}
        if "SELECT count(*) AS count" in self.sql:
            return {"count": 0}
        if "FROM matches WHERE match_id = %s" in self.sql:
            return _match(str(self.params[0]))
        raise AssertionError(f"unhandled fetchone SQL: {self.sql}")

    def fetchall(self):
        if "FROM matches WHERE match_id LIKE '500-%%'" in self.sql:
            return [_match("500-1359210")]
        return []


def test_collect_state_counts_tracked_correct_predictions_after_split_disappears() -> None:
    state = cleanup._collect_state(
        _TrackedStateCursor(),
        tracked_dirty_ids=["500-2040123"],
        tracked_correct_ids=["500-1359210"],
    )

    assert state["plans"] == []
    assert state["correct_matches"]["500-1359210"]["match_id"] == "500-1359210"
    assert state["correct_pre_kickoff_predictions"]["500-1359210"] == 112


def test_cli_defaults_to_dry_run(monkeypatch) -> None:
    called = False

    def fake_dry_run():
        nonlocal called
        called = True
        return {"ok": True, "errors": [], "state": {"split_group_count": 0, "dirty_ids": []}}

    monkeypatch.setattr(cleanup, "dry_run", fake_dry_run)

    assert cleanup.main([]) == 0
    assert called is True


def test_cli_rejects_wrong_confirm_token() -> None:
    with pytest.raises(SystemExit):
        cleanup.main(["--confirm", "--confirm-token", "WRONG"])
