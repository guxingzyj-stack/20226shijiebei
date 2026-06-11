from __future__ import annotations


TEST_MATCH_PREFIX = "test-"
TEST_SETTLEMENT_PREFIX = "test-settlement-"


def assert_test_match_id(match_id: str) -> None:
    if not str(match_id).startswith(TEST_MATCH_PREFIX):
        raise ValueError("production settlement smoke may only use match_id values starting with test-")
    if str(match_id).startswith("500-"):
        raise ValueError("never write fake scores for real 500- match_id values")


def cleanup_sql_statements() -> list[str]:
    return [
        "DELETE FROM bets WHERE legs::text LIKE '%test-settlement-%';",
        "DELETE FROM matches WHERE match_id LIKE 'test-%';",
        "DELETE FROM users WHERE username LIKE 'test_user_%' OR username LIKE 'codex_blocker_%';",
    ]


def validate_cleanup_sql(sql: str) -> bool:
    normalized = " ".join(sql.split()).lower()
    if "delete from matches" in normalized:
        return "match_id like 'test-%'" in normalized
    if "delete from users" in normalized:
        return "username like 'test_user_%'" in normalized and "username like 'codex_blocker_%'" in normalized
    if "delete from bets" in normalized:
        return "test-settlement-" in normalized
    return False
