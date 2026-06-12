# Betting Open Gate Report

Date: 2026-06-12

This report documents the automated simulated-betting readiness gate. The gate
only judges whether the system is ready for a controlled simulated-betting
grey rollout. It never changes `BETTING_ENABLED`, never deploys services, and
never opens betting by itself.

```text
automatic judgment
manual opening only
```

## 1. Status Values

```text
READY:
  All hard safety checks passed.
  recommend_open_betting=true.
  User approval is still required before setting BETTING_ENABLED=true.

WAIT:
  Core health is acceptable, but observation or evidence is incomplete.
  This is expected while waiting for two matchdays of automatic result sync.

BLOCKED:
  A production safety risk exists.
  Do not open betting.
```

## 2. CLI

Run inside the API container or an equivalent environment with `DATABASE_URL`:

```bash
PYTHONPATH=. python -m api.betting_open_gate
```

Output includes:

```text
Betting Open Gate Report
- status: READY / WAIT / BLOCKED
- recommend_open_betting: true / false
- blockers:
- warnings:
- scheduler_stale:
- odds_stale:
- finished_null_count:
- non_finished_with_result_count:
- settlement_probe_pass:
- settlement_idempotency_pass:
- leaderboard_safe:
- two_matchdays_auto_result_sync:
- betting_enabled:
```

## 3. Hard Blockers

Any of these makes the gate `BLOCKED`:

```text
scheduler_stale=true
odds_stale=true
finished_null_count>0
non_finished_with_result_count>0
settlement_runner_error=true
leaderboard exposes internal id
leaderboard has test/probe user pollution
BETTING_ENABLED=true before the gate is satisfied
```

## 4. WAIT Conditions

These keep the gate at `WAIT` but do not necessarily mean the system is broken:

```text
settlement_e2e_probe_not_passed
settlement_idempotency_not_passed
need_two_matchdays_auto_result_sync
p1c_prime_insufficient_samples
p3_wait
```

## 5. Two Matchdays Auto Result Sync

The gate is intentionally conservative:

```text
two_matchdays_auto_result_sync=true only when:
- at least two matchdays have finished/completed matches with real scores
- recent results_sync ops_log records are ok
- official_result_fallback has not been used for those results
```

If scores were written by `official_result_fallback`, they are valid for
result consistency and settlement, but they do not count as automatic result
sync evidence for opening betting.

## 6. 045 Evidence

The gate reads production evidence from `ops_log`, not from this document.

Expected settlement probe evidence:

```json
{
  "job_name": "settlement_e2e_probe",
  "status": "ok",
  "summary": {
    "ok": true,
    "idempotency_pass": true,
    "cleanup_success": true,
    "leaderboard": {
      "leaderboard_no_internal_id": true,
      "leaderboard_no_probe_user_pollution": true
    }
  }
}
```

## 7. API Health

`/api/health` exposes:

```json
{
  "betting_open_gate_status": "WAIT",
  "recommend_open_betting": false,
  "betting_open_blockers": ["need_two_matchdays_auto_result_sync"],
  "betting_open_warnings": ["p3_wait"]
}
```

DB errors must not expose credentials or crash the health endpoint.

## 8. Prohibited Actions

Do not:

- set `BETTING_ENABLED=true` without explicit user approval
- treat `READY` as automatic permission to open betting
- treat `official_result_fallback` as automatic result sync evidence
- write fake scores
- edit bets, users, balances, or model weights for the gate
- paste or commit database URLs, tokens, passwords, or API keys
