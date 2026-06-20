import pytest

from api import cleanup_dirty_match_id as cleanup


def _state(**overrides):
    state = {
        "dirty_counts": {
            "matches": 1,
            "odds_snapshots": 88,
            "predictions": 49,
            "ev_signals": 0,
            "gbm_predictions": "table_not_found_skipped",
            "result_ingest_observations": 0,
        },
        "correct_match": {"match_id": cleanup.CORRECT_MATCH_ID},
        "correct_pre_kickoff_predictions": 1,
        "bets_with_dirty_match_id": 0,
        "script_predictions_count": 64,
        "split_identity_count": 1,
    }
    state.update(overrides)
    return state


def test_validate_state_requires_correct_pre_kickoff_prediction():
    errors = cleanup.validate_state(_state(correct_pre_kickoff_predictions=0), require_dirty_match=True)

    assert any("no pre-kickoff prediction" in error for error in errors)


def test_validate_state_requires_correct_match_when_dirty_exists():
    errors = cleanup.validate_state(_state(correct_match=None), require_dirty_match=True)

    assert any(cleanup.CORRECT_MATCH_ID in error for error in errors)


def test_validate_state_refuses_to_touch_dirty_bets():
    errors = cleanup.validate_state(_state(bets_with_dirty_match_id=1), require_dirty_match=True)

    assert any("bets reference dirty match id" in error for error in errors)


def test_validate_state_allows_missing_gbm_predictions_table():
    errors = cleanup.validate_state(_state(), require_dirty_match=True)

    assert errors == []
    assert _state()["dirty_counts"]["gbm_predictions"] == "table_not_found_skipped"


def test_verify_after_delete_requires_all_dirty_tables_zero():
    before = _state()
    after = _state(
        dirty_counts={
            "matches": 0,
            "odds_snapshots": 1,
            "predictions": 0,
            "ev_signals": 0,
            "gbm_predictions": "table_not_found_skipped",
            "result_ingest_observations": 0,
        }
    )

    errors = cleanup._verify_after_delete(after, before)

    assert any("odds_snapshots still has 1 rows" in error for error in errors)


def test_verify_after_delete_protects_correct_id_and_script_predictions():
    before = _state(script_predictions_count=64)
    after = _state(
        dirty_counts={
            "matches": 0,
            "odds_snapshots": 0,
            "predictions": 0,
            "ev_signals": 0,
            "gbm_predictions": "table_not_found_skipped",
            "result_ingest_observations": 0,
        },
        correct_match={"match_id": cleanup.CORRECT_MATCH_ID},
        correct_pre_kickoff_predictions=1,
        script_predictions_count=64,
        split_identity_count=1,
    )

    assert cleanup._verify_after_delete(after, before) == []


def test_verify_after_delete_rejects_script_predictions_change():
    before = _state(script_predictions_count=64)
    after = _state(
        dirty_counts={
            "matches": 0,
            "odds_snapshots": 0,
            "predictions": 0,
            "ev_signals": 0,
            "gbm_predictions": "table_not_found_skipped",
            "result_ingest_observations": 0,
        },
        script_predictions_count=63,
    )

    errors = cleanup._verify_after_delete(after, before)

    assert "script_predictions count changed" in errors


class _Cursor:
    def __init__(self, table_name):
        self.table_name = table_name
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())

    def fetchone(self):
        return {"table_name": self.table_name}


def test_table_exists_uses_explicit_gbm_regclass_query():
    cur = _Cursor(None)

    assert cleanup.table_exists(cur, "gbm_predictions") is False
    assert "to_regclass('public.gbm_predictions')" in cur.sql


def test_cli_rejects_wrong_confirm_token():
    with pytest.raises(SystemExit):
        cleanup.main(["--confirm", "--confirm-token", "WRONG"])
