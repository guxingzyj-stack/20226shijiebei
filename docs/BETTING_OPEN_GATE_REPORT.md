# Betting Open Gate Report

Date: 2026-06-12

This report is an evidence checklist for the simulated betting gate. It does
not enable betting and does not authorize changing `BETTING_ENABLED`.

## 1. Production Watchdog

Public `/api/health` read-only probe:

```text
ok: true
scheduler_stale: false
ops_health_status: WARN
ops_health_blockers:
- no_open_bets_to_settle
- insufficient_finished_matches
- closed_prediction_pending
latest_ops_health_check_at: 2026-06-12T04:31:34.324015+00:00
```

Gate interpretation:

```text
watchdog_result: WARN_ACCEPTABLE
```

The blockers above are acceptable for the current tournament state. They do
not prove settlement with real open bets.

## 2. Settlement E2E

Automated non-production coverage:

```text
test_file: tests/api_tests/test_settlement_e2e.py
environment: in-memory isolated repository
production_db_written: false
real_500_match_touched: false
```

Covered cases:

```text
winning single: PASS
losing single: PASS
parlay with postponed/void leg: PASS
closed match without result remains open: PASS
finished match with NULL result remains open: PASS
second settlement run idempotency: PASS
leaderboard-safe fields include roi and exclude internal id: PASS
```

This satisfies the test-environment settlement loop requirement. It does not
replace production internal test-bet evidence.

## 3. Production Read-Only Checks

Public `/api/leaderboard` read-only probe:

```text
rows: 1
has_roi: true
exposes_internal_id: false
test_user_count: 0
sample_keys:
- balance
- roi
- settled_bets
- username
```

No production write was performed for this report.

## 4. Betting Gate

Required before opening simulated betting:

```text
scheduler_stale=false: PASS
ops health OK or acceptable WARN: PASS
finished+NULL result count=0: PASS by latest result_consistency_report evidence
non-finished rows with result count=0: PASS by latest result_consistency_report evidence
settlement E2E in test environment: PASS
production/internal real open bet settlement: NOT_CHECKED
settlement idempotency: PASS in test environment
leaderboard safety: PASS
explicit user confirmation to open betting: MISSING
```

Final gate decision:

```text
recommend_open_betting: no
BETTING_ENABLED: keep false
reason:
- production/internal real open bet settlement has not been observed
- the watchdog still reports no_open_bets_to_settle
- real match settlement has not yet completed through production data
- when automatic result sync misses an official result, use the controlled
  official_result_fallback flow before any settlement gate decision
```

## 5. Prohibited Actions

Do not:

- set `BETTING_ENABLED=true`
- write fake scores to real `500-` matches
- manually insert production predictions or settlements
- manually edit production balances
- treat a no-op settlement run as a real bet settlement pass
- paste or commit database URLs, tokens, passwords, or API keys
- apply scores with ad hoc SQL instead of the dry-run + confirm fallback
