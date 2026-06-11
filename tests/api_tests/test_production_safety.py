import pytest

from api.production_safety import assert_test_match_id, cleanup_sql_statements, validate_cleanup_sql


def test_settlement_closed_loop_helper_rejects_real_500_match_id():
    with pytest.raises(ValueError):
        assert_test_match_id("500-1359172")


def test_test_match_must_use_test_prefix():
    with pytest.raises(ValueError):
        assert_test_match_id("manual-settlement-1")
    assert_test_match_id("test-settlement-123")


def test_cleanup_sql_only_targets_test_prefixes():
    statements = cleanup_sql_statements()

    assert statements
    assert all(validate_cleanup_sql(statement) for statement in statements)
    assert not validate_cleanup_sql("DELETE FROM users;")
    assert not validate_cleanup_sql("DELETE FROM matches WHERE match_id LIKE '500-%';")
