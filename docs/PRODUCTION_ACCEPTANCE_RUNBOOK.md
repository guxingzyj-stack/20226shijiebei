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

## 5. Scheduler Deployment

Deploy scheduler code with scheduling disabled first:

```text
ENABLE_API_SCHEDULER=false
BETTING_ENABLED=false
```

Run inside the P2 API container:

```bash
python -m api.apply_migrations
python -m api.acceptance_report
```

After acceptance passes and settlement smoke has already returned `PASS`, enable scheduling in the Zeabur API service environment:

```text
ENABLE_API_SCHEDULER=true
RESULTS_SYNC_INTERVAL_MINUTES=60
SETTLEMENT_RUNNER_INTERVAL_MINUTES=30
OPS_HEALTH_CHECK_INTERVAL_MINUTES=30
OPS_HEALTH_STALE_THRESHOLD_MINUTES=90
ODDS_STALE_THRESHOLD_MINUTES=30
OPS_ALERT_ENABLED=false
OPS_ALERT_WEBHOOK_URL=
RUN_SCHEDULER_ON_STARTUP=true
BETTING_ENABLED=false
```

Redeploy the API service, then observe logs and `ops_log` through:

```bash
python -m api.acceptance_report
```

Do not enable betting as part of scheduler rollout.

If `RUN_SCHEDULER_ON_STARTUP=true`, the API scheduler runs these jobs once at
startup and then on their intervals:

```text
results_sync
settlement_runner
ops_health_check
```

The startup run is part of deployment acceptance. Within one minute after every
`wc-p2-api` deployment or restart, verify all of these:

```bash
curl -sS https://fifa2026.zeabur.app/api/health
PYTHONPATH=. python -m api.acceptance_report
PYTHONPATH=. python -m api.result_consistency_report
PYTHONPATH=. python -m api.result_overdue_report
PYTHONPATH=. python -m api.ops_health_check
```

Required evidence:

```text
api logs contain event=api_scheduler_started
api logs contain scheduler_job_finished for results_sync
api logs contain scheduler_job_finished for settlement_runner
api logs contain scheduler_job_finished for ops_health_check
scheduler_last_seen is within 5 minutes
scheduler_stale=false
scheduler_startup_error=null
latest_ops_health_check_at is within 5 minutes
ops_log has recent results_sync ok
ops_log has recent settlement_runner ok
/api/health exposes latest_results_sync_skipped_reasons
/api/health exposes result_overdue_closed_count
```

If `scheduler_last_seen` is older than 5 minutes, `scheduler_stale=true`, or
`scheduler_startup_error` is non-empty, the deployment is not complete. Do not
wait and observe passively; fix the API scheduler before relying on result sync.

The watchdog can also be run manually:

```bash
python -m api.ops_health_check
python scripts/run_daily_ops_check.py
```

It writes `ops_log.job_name='ops_health_check'` with status `ok`, `warn`, or
`fail`. A no-op settlement state because there are no open bets is `WARN`; it is
not proof that real bet settlement has passed.

The daily runner is pure Python and is intended for production containers where
shell HTTP/database clients may be unavailable. Do not run debug shell tracing
because it may expand environment variables. The runner prints
`DATABASE_URL_SET=true/false` only.

## 6. 014-C Operations Closeout

Current status:

```text
Read-only features are open.
BETTING_ENABLED=false.
Scheduler is enabled and waiting for real ops_log observation.
P1-C historical market backtest numbers are still pending.
P3 real data import is pending.
P4 recap API and frontend MVP are read-only and can display finished matches with results.
```

Always back up PostgreSQL before cleanup, restore, migration, or host movement:

```bash
bash deploy/backup_postgres.sh
```

On Windows self-hosting:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/backup_postgres.ps1
```

`odds_snapshots` is not reproducible and must be treated as the highest-priority backup table.

Read-only health checks:

```bash
curl -sS https://fifa2026.zeabur.app/api/health
python -m api.health_report
python -m api.ops_health_check
python scripts/run_daily_ops_check.py
python -m api.result_consistency_report
python -m api.result_overdue_report
python -m api.worldcup_live_probe --recent
python -m api.worldcup_live_probe --compare-local --all-overdue
python -m api.worldcup_live_probe --map-local --recent
python -m api.worldcup_live_probe --map-local --all-overdue
python -m api.worldcup_live_probe --map-qiumibao-by-time --upcoming
python -m api.worldcup_live_probe --map-qiumibao-by-time --all-overdue
python -m api.scheduler_observe
python -m api.cleanup_test_data dry-run
```

`/api/health` should include `scheduler_last_seen`, `scheduler_last_seen_age_minutes`,
`scheduler_stale`, `latest_ops_health_check_at`, `ops_health_status`, and
`ops_health_blockers`. If latest `ops_log` is older than 90 minutes,
`api.health_report` must return `FAIL`.

The `api.worldcup_live_probe` commands are BaiLongma-style zhibo8/qiumibao
live-source dry-runs. The `--map-local` variants score candidate mappings to
local `matches.match_id`. They print `writes_db: false` and must not be used as
a score writer without explicit approval.

For 061-B diagnostics, confirm:

```text
--dump-zhibo8 shows zhibo8_raw_links and possible_qiumibao_ids
--map-local shows qiumibao_link_status and next_step
zhibo8_matched_but_qiumibao_unlinked is WAIT_SOURCE, not score evidence
possible_zhibo8_ids and possible_qiumibao_ids are separate
```

For 061-D diagnostics, use the qiumibao direct UTC time mapping path:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --upcoming
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --all-overdue
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id <match_id>
```

Expected:

```text
Qiumibao Time Mapping Report
writes_db: false
qiumibao start_time is interpreted as UTC Unix timestamp
local kickoff_at is compared in UTC
safe window is <= 15 minutes
```

Do not treat `possible_zhibo8_ids` as qiumibao score ids. If qiumibao time
mapping returns `ambiguous_qiumibao_candidates` or `ambiguous_local_candidates`,
the row is not safe for any future writer.

For 061-E diagnostics, inspect qiumibao raw fields and candidate details first:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --dump-qiumibao-raw --limit 3
PYTHONPATH=. python -m api.worldcup_live_probe --dump-qiumibao --limit 30
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id 500-1359182 --show-candidates --limit 10
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id 500-1359182 --football-like-only --show-candidates --limit 10
PYTHONPATH=. python -m api.worldcup_live_probe --qiumibao-known-result-candidates --recent-finished --limit 20
```

Expected:

```text
raw dump shows source_url, rows_seen, raw keys, and classification_field_candidates
missing sport/category/league fields are printed as not_found
ambiguous rows print candidate details
football-like-only prints before/after filter counts
known-result candidates print possible left_id/right_id directions
writes_db: false
```

The qiumibao feed is a mixed rolling feed unless raw fields prove otherwise.
`football_like` is only a coarse diagnostic filter. Team-id reverse discovery is
only an investigation aid and must not create automatic mappings or write
scores.

Before starting any external result-source project, audit the existing 500 chain:

```bash
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --recent
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --all-started
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --closed-missing
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --half-time-fields
```

Expected:

```text
500 Result Coverage Audit
mode: dry-run
writes_db: false
started_result_coverage_rate is visible
closed_missing_count is visible
finished_missing_count is visible
non_finished_with_result_count is visible
latest results_sync evidence is visible
half-time coverage conclusion is visible
```

062-A does not connect a new source. The current 500/m500 role is odds capture,
sale-closed status, and candidate full-time result capture. Half-time scores are
separate: if `ht_home` / `ht_away` are missing, hafu cannot be settled, and the
full-time score must not be used to infer half-time.

Normal daily operation no longer requires running the full 041 SQL bundle. Use
`/api/health` first. If it shows `FAIL`, run the Python daily runner and
`python -m api.ops_health_check` inside the API container, then inspect `ops_log`.

If `/api/health.result_overdue_closed_count > 0`, run:

```bash
PYTHONPATH=. python -m api.results_sync once
PYTHONPATH=. python -m api.result_overdue_report
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --recent
PYTHONPATH=. python -m api.result_source_compare --all-overdue
```

If `result_overdue_report` still returns `NEEDS_VERIFIED_FALLBACK`, use the
official verified fallback CSV process. Do not manually update scores with SQL.

For a single stuck match, run:

```bash
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --match-id <match_id>
PYTHONPATH=. python -m api.result_source_compare --match-id <match_id>
```

The mapping and compare reports are dry-run only. `LOCAL_DB_ONLY` means the
local DB has a score but no external source has confirmed it. `NEEDS_VERIFIED_FALLBACK`
means prepare a reviewed fallback CSV row; it does not authorize manual SQL
score writes.

Sale closed / stop selling is not a match result. The crawler may write `closed`,
but only `results_sync` may mark a real match `finished` after full-time scores are
available. `finished` rows with missing `result_home` or `result_away` must be
treated as not ready for settlement, recap, and P1-C Prime calibration.

If old data contains `finished/completed` rows with both full-time scores still
`NULL`, first inspect the exact target list:

```bash
python -m api.result_consistency_report repair-finished-null --dry-run
```

Only after the dry-run target list is confirmed safe, downgrade those rows to
`closed`:

```bash
python -m api.result_consistency_report repair-finished-null --confirm REPAIR_FINISHED_NULL
```

This repair command does not write scores. It only updates rows matching
`status IN ('finished','completed') AND result_home IS NULL AND result_away IS NULL`.

Test data cleanup requires explicit confirmation:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

Cleanup scope is limited to:

```text
users.username LIKE 'test_user_%'
users.username LIKE 'codex_blocker_%'
matches.match_id LIKE 'test-%'
bets.legs::text LIKE '%test-%'
```

Do not run real `settlement_runner once` as part of this closeout. Do not write fake scores to real `500-` matches.

## 7. Simulated Betting Open Gate

`BETTING_ENABLED` must remain `false` unless all gate checks pass and the user
explicitly confirms opening simulated betting.

Required gate checks:

```text
scheduler_stale=false
ops_health_status=OK, or WARN only for allowed blockers
finished/completed rows with NULL full-time result = 0
scheduled/closed rows with result populated = 0
test-environment settlement E2E = PASS
production/internal real open bet settlement = PASS
settlement idempotency = PASS
leaderboard exposes no internal id and includes roi
no test users remain in the public leaderboard
explicit user confirmation = yes
```

Allowed temporary watchdog blockers:

```text
no_open_bets_to_settle
insufficient_finished_matches
closed_prediction_pending
```

Disallowed blockers:

```text
scheduler_stale
odds_stale
finished_null_count
non_finished_with_result
settlement_runner_error
```

The current gate evidence is tracked in:

```text
docs/BETTING_OPEN_GATE_REPORT.md
```

Do not treat a no-op settlement runner execution as proof that real open-bet
settlement works.

## 8. Official Result Fallback

`results_sync` remains the primary result path. If it cannot populate a verified
finished result, use the controlled fallback instead of manual SQL.

Prepare a reviewed CSV:

```text
data/results/official_results_verified.csv
```

Run dry-run first:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --dry-run
```

Only after the target list is reviewed:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --confirm APPLY_OFFICIAL_RESULTS
```

Requirements:

```text
source_url required
verified_by required
dry-run required before confirm
ops_log job_name=official_result_fallback
existing results are not overwritten
no manual SQL score update
```

See:

```text
docs/OFFICIAL_RESULT_FALLBACK_RUNBOOK.md
```

## 9. Production Internal Settlement Probe

After official results are present and result consistency is clean, use the
dedicated settlement E2E probe. Do not create ad hoc production bets by hand.

Dry-run:

```bash
PYTHONPATH=. python -m api.settlement_e2e_probe --dry-run
```

Confirm only after dry-run has no blockers:

```bash
PYTHONPATH=. python -m api.settlement_e2e_probe --confirm RUN_SETTLEMENT_E2E_PROBE
```

The probe:

```text
requires BETTING_ENABLED=false
creates username __internal_settlement_probe__
creates one stake=1 HAD home-win probe bet by default
uses latest server-side HAD odds
runs settlement_runner twice
checks balance delta and idempotency
cleans up probe bet and probe user
writes ops_log job_name=settlement_e2e_probe
```

Do not proceed if non-probe open/pending bets exist.

Even after a successful probe, keep betting closed until at least two
consecutive match days have automatic result sync working and the user
explicitly confirms opening simulated betting.

## 10. P4 Recap Layer

P4 is a read-only post-match review layer. It does not write scores, modify
bets/users/balances, change P1/P3 weights, or open betting.

After deploying `wc-p2-api`, verify:

```bash
curl -sS https://fifa2026.zeabur.app/api/recaps/matches/500-1359172
curl -sS https://fifa2026.zeabur.app/api/recaps/recent
curl -sS https://fifa2026.zeabur.app/api/recaps/summary
```

Container CLI:

```bash
PYTHONPATH=. python -m api.recap_runner --match-id 500-1359172
PYTHONPATH=. python -m api.recap_runner --summary
```

Expected:

```text
finished matches with full-time scores return available=true
unfinished or missing-score matches return available=false
settlement summaries do not expose user_id or bet_id
research_only EV is shown as research_signal, not betting advice
```

After deploying `wc-p2-web`, verify the frontend:

```text
https://worldcup2026.zeabur.app/recaps
https://worldcup2026.zeabur.app/recaps/500-1359172
https://worldcup2026.zeabur.app/recaps/model
https://worldcup2026.zeabur.app/recaps/ev
https://worldcup2026.zeabur.app/recaps/daily
```

Expected:

```text
/recaps shows recent finished recaps or a friendly empty state
/recaps/{match_id} shows result, market odds, model review, EV recap, settlement status, data quality, and summary
/recaps/model shows model performance and market/model agreement without changing weights
/recaps/ev labels EV as research signal, not betting advice
/recaps/daily generates copyable daily report text from recap API data
match detail shows "查看赛后复盘" only for finished/completed matches with scores
research_only EV is labelled as research signal, not betting advice
no user_id, bet_id, or internal id is rendered
```

## 11. P3 FIFA MatchData Readiness Gate

P3-FIFA is an automatic maturity gate for official FIFA MatchData. It can move
from `WAIT` to `SHADOW`, `CANDIDATE`, and `ACTIVE_READY` as audited match data
accumulates.

Run:

```bash
PYTHONPATH=. python -m model.p3_fifa_readiness
PYTHONPATH=. python -m model.p3_auto_enable_gate
```

Safety requirements:

```text
production_w_p3 remains 0
production_w_gbm remains 0
candidate_w_p3 is only a candidate value
P3-FIFA WAIT/SHADOW does not make health FAIL
P3-FIFA does not open betting
P3-A club recent form remains WAIT until compliant high-coverage data exists
```

## 12. Betting Open Gate

The API exposes an automated readiness gate for simulated betting:

```bash
PYTHONPATH=. python -m api.betting_open_gate
curl -sS https://fifa2026.zeabur.app/api/health
```

The gate may return `READY`, `WAIT`, or `BLOCKED`.

```text
READY means the system recommends considering a controlled simulated-betting grey rollout.
READY does not change BETTING_ENABLED.
WAIT means more evidence is needed, such as two matchdays of automatic result sync.
BLOCKED means a production safety issue exists and betting must remain closed.
```

Opening simulated betting still requires explicit user approval and a manual
environment change:

```text
BETTING_ENABLED=true
```

Do not treat official fallback result entry as automatic result sync evidence.
