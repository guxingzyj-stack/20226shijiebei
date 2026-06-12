# Settlement E2E Test Plan

This plan validates the settlement loop without opening public betting and
without writing fake scores to real production matches.

## 1. Goal

Validate the full controlled flow:

```text
open bet -> finished match with result -> settlement_runner once
-> won/lost/void status -> balance change -> leaderboard update
-> second settlement_runner once is idempotent
```

Passing this plan is required before considering any broader simulated betting
opening. A no-op settlement run is not a real bet settlement pass.

## 2. Preferred Environment

Use a test database or local temporary database with the same schema as
production.

Do not use production for this flow unless the user explicitly confirms:

```text
allow creating one production internal test bet
```

Production constraints still apply:

- `BETTING_ENABLED=false`
- no public betting entry opened
- no fake score on real `500-` matches
- no manual balance edits
- all test data must be scoped and cleanable

## 3. Test Data Preparation

Create only test-prefixed entities:

```text
match_id = test-settlement-e2e-<timestamp>
match_num = TEST-E2E
home_team = Test Home
away_team = Test Away
status = finished
result_home = 2
result_away = 1
ht_home = 1
ht_away = 0
username = test_user_settlement_e2e_<timestamp>
```

For void-leg testing, create a second test match:

```text
match_id = test-settlement-e2e-void-<timestamp>
status = postponed
```

Never use `match_id LIKE '500-%'` for synthetic settlement tests.

## 4. Open Bet Creation

Create at least these controlled open bets in the test environment:

```text
A. winning single
play_type = had
selection = 3
stake = 10
odds_at_bet = 2.0
expected status = won

B. losing single
play_type = had
selection = 0
stake = 10
odds_at_bet = 2.0
expected status = lost

C. parlay with void leg
leg 1 = winning test match at odds 2.0
leg 2 = postponed test match at odds treated as 1.0
expected payout = stake * 2.0 * 1.0
```

Use the existing application bet schema and settlement code. Do not update
balances by hand.

## 5. Settlement Runner Command

Run once:

```bash
PYTHONPATH=. python -m api.settlement_runner once
```

Then run it a second time:

```bash
PYTHONPATH=. python -m api.settlement_runner once
```

The second run must not change settled bet payouts or user balance.

## 6. Verification SQL

Before settlement:

```sql
SELECT status, COUNT(*) FROM bets GROUP BY status ORDER BY status;
SELECT username, balance FROM users WHERE username LIKE 'test_user_settlement_e2e_%';
```

After first settlement:

```sql
SELECT id, status, stake, odds_at_bet, payout, settled_at
FROM bets
WHERE legs::text LIKE '%test-settlement-e2e-%'
ORDER BY id;

SELECT username, balance
FROM users
WHERE username LIKE 'test_user_settlement_e2e_%';

SELECT username, balance, roi, settled_bets
FROM leaderboard_or_api_equivalent;
```

After second settlement:

```sql
SELECT id, status, payout, settled_at
FROM bets
WHERE legs::text LIKE '%test-settlement-e2e-%'
ORDER BY id;

SELECT username, balance
FROM users
WHERE username LIKE 'test_user_settlement_e2e_%';
```

The second set of results must match the first post-settlement result.

## 7. Idempotency Criteria

Pass criteria:

- winning bet pays exactly once
- losing bet does not pay
- void leg contributes odds `1.0`
- user balance changes only from settlement logic
- second runner execution does not change balance, payout, or settled status
- `ops_log` records `settlement_runner` with `status=ok`

## 8. Cleanup

Clean only scoped test rows:

```sql
DELETE FROM bets WHERE legs::text LIKE '%test-settlement-e2e-%';
DELETE FROM matches WHERE match_id LIKE 'test-settlement-e2e-%';
DELETE FROM users WHERE username LIKE 'test_user_settlement_e2e_%';
```

Run a dry-run/select first and confirm no real `500-` rows are included.

## 9. Production Prohibitions

Do not:

- enable `BETTING_ENABLED=true`
- create public user-facing betting access
- insert fake results into real matches
- manually update real user balances
- mark no-op settlement as real bet settlement pass
- run this on production without explicit user confirmation

## 10. Evidence Required

The final E2E report must include:

- commands executed
- before/after bet status counts
- before/after user balance
- settlement runner output
- latest `ops_log` rows
- idempotency proof from the second runner run
- cleanup proof

## 11. Automated Local Gate Test

The repository includes a production-safe automated E2E gate test:

```bash
PYTHONPATH=. python -m pytest tests/api_tests/test_settlement_e2e.py -q
```

This test uses an in-memory repository, not production PostgreSQL. It covers:

```text
winning single
losing single
parlay with postponed/void leg
closed match without result remains not ready
finished match with NULL result remains not ready
second settlement run idempotency
leaderboard output contains roi and no internal id
```

Passing this test is required before the betting gate can be considered, but it
is not sufficient by itself. Opening simulated betting still requires an
internal production test bet to settle successfully without public betting
being enabled.
