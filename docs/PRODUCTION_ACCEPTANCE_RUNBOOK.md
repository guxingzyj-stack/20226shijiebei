# Production Acceptance Runbook

This runbook is for production acceptance only. Do not paste or commit `DATABASE_URL`, `JWT_SECRET`, tokens, passwords, or API keys.

## 1. Service Names

The following service names must use the actual names shown in the Zeabur console:

- P0 crawler 服务：以 Zeabur 实际服务名为准
- P1 model-worker 服务：以 Zeabur 实际服务名为准
- P2 API 服务：以 Zeabur 实际服务名为准
- P2 Web 服务：以 Zeabur 实际服务名为准
- PostgreSQL 服务：以 Zeabur 实际服务名为准

Do not assume any hard-coded Zeabur service name.

## 2. Production Execution Steps

Run these commands inside the matching Zeabur container terminal. Codex does not have Zeabur console access and does not run production operations.

### P1 model-worker container

```bash
python -m model.cli acceptance-report
```

### P2 API container

```bash
python -m api.acceptance_report
python -m api.results_sync dry-run
python -m api.settlement_runner dry-run
```

### Optional settlement closed-loop smoke

Only run a production settlement smoke after manual SQL review. The current code does not provide a dangerous default `--test-only` writer.

If a test match is required, it must use:

```text
match_id = test-settlement-<timestamp>
match_num = TEST001
home_team = 测试主队
away_team = 测试客队
```

Test bets may only reference `test-` prefixed `match_id` values.

## 3. Production Database Prohibited Actions

Never write fake scores to real matches. Real matches include but are not limited to:

- `match_id` values starting with `500-`
- real Jingcai match numbers such as `周四001` or `周五003`

These real match fields may only be written by `results_sync` from real results:

```text
result_home
result_away
ht_home
ht_away
status
```

Also prohibited:

- Do not set `BETTING_ENABLED=true` before settlement acceptance passes.
- Do not test against real user balances.
- Do not output `DATABASE_URL` or `JWT_SECRET`.
- Do not connect to real betting or purchase flows.

## 4. Safe Cleanup SQL

Before deletion, confirm the target rows are test-only and do not include real users or real matches.

```sql
DELETE FROM bets WHERE legs::text LIKE '%test-settlement-%';
DELETE FROM matches WHERE match_id LIKE 'test-%';
DELETE FROM users WHERE username LIKE 'test_user_%' OR username LIKE 'codex_blocker_%';
```

These statements intentionally only target test prefixes.
