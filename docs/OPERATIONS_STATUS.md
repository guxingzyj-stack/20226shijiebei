# Operations Status

Current production posture:

- Production read-only version is stable.
- Read-only prediction, odds, EV, leaderboard, and recap skeleton features are open.
- Betting remains closed: `BETTING_ENABLED=false`.
- GBM remains zero-weight and does not affect P1 production predictions.

## Production Status Summary

### Scheduler

- `settlement_runner`: `PASS`
- `results_sync`: `PASS`
- `ops_health_check`: code ready; enable through API scheduler after deployment
- stale threshold: latest `ops_log` older than 90 minutes is `FAIL` in `api.health_report`
- required production env: `ENABLE_API_SCHEDULER=true`, `RUN_SCHEDULER_ON_STARTUP=true`, `BETTING_ENABLED=false`
- API startup now explicitly runs `results_sync`, `settlement_runner`, and `ops_health_check` once before waiting for the next interval
- startup errors are exposed through `/api/health.scheduler_startup_error` and force `scheduler_stale=true`
- `/api/health` exposes `scheduler_last_seen`, `scheduler_last_seen_age_minutes`, `scheduler_stale`, `scheduler_startup_error`, `latest_ops_health_check_at`, `ops_health_status`, `ops_health_blockers`, latest `results_sync` summary, and overdue closed-result counts
- current main result source: `500_trade_jczq` HTML page, not an official structured source
- result-overdue CLI: `python -m api.result_overdue_report`
- multi-source dry-run compare CLI: `python -m api.result_source_compare --all-overdue`
- source mapping probe CLI: `python -m api.result_source_mapping_probe --source qiumibao --recent`
- BaiLongma-style live source dry-run CLI: `python -m api.worldcup_live_probe --recent`
- live source overdue compare CLI: `python -m api.worldcup_live_probe --compare-local --all-overdue`
- live source local mapping CLI: `python -m api.worldcup_live_probe --map-local --recent`
- live source overdue mapping CLI: `python -m api.worldcup_live_probe --map-local --all-overdue`
- qiumibao time mapping CLI: `python -m api.worldcup_live_probe --map-qiumibao-by-time --upcoming`
- qiumibao overdue time mapping CLI: `python -m api.worldcup_live_probe --map-qiumibao-by-time --all-overdue`
- qiumibao raw field dump CLI: `python -m api.worldcup_live_probe --dump-qiumibao-raw --limit 3`
- qiumibao known-result candidate CLI: `python -m api.worldcup_live_probe --qiumibao-known-result-candidates --recent-finished --limit 20`
- multi-source compare 058-B rule: `OK_MATCH` requires at least one external
  score source to confirm the local DB score; local-only scores now report
  `LOCAL_DB_ONLY`
- qiumibao events are only fetched after `qiumibao_score` maps a real qiumibao
  match id; missing mapping is reported as `mapping_missing` instead of
  producing avoidable 404s
- source matching normalizes odd spaced team names such as `加 拿 大`, `墨 西 哥`,
  `韩 国`, and full-width/invisible whitespace
- 059 qiumibao mapping probe can distinguish `matched`, `source_fetch_error`,
  `source_empty`, `source_available_but_match_not_in_window`,
  `parser_missing_team_fields`, `team_name_mismatch`,
  `kickoff_time_mismatch`, and `ambiguous_candidates`
- 059-B qiumibao schema dump shows some score rows expose scores as
  `left.score/right.score` but only team ids as `left.id/right.id`; if no team
  names are present, the correct status is `parser_missing_team_fields`
- FIFA Match Centre remains `fifa_mapping_missing` until a durable local
  match_id to FIFA id/url mapping is built
- ESPN scoreboard is now a controlled structured result fallback candidate.
  It remains dry-run/explicit-confirm only and must not write scheduled/live
  scores. ESPN `dates=YYYYMMDD` uses the US Eastern Time match day, while local
  `kickoff_at` is UTC; for ESPN, `external_result_sync` checks ET date, UTC
  date, UTC date - 1, and UTC date + 1 buckets before applying the normal
  team/time/final/score/unique-candidate gate.
- 060 live-source chain combines zhibo8 homepage schedule context with qiumibao
  score/event JSON. It is dry-run only and must not auto-write scores.
- 061 local mapping scores live rows against local `matches.match_id` with
  normalized team names, kickoff windows, external refs, confidence, and
  ambiguity protection. It is still dry-run only.
- 061-B adds zhibo8 raw link diagnostics, possible qiumibao ids, and explicit
  `zhibo8_matched_but_qiumibao_unlinked` status when schedule mapping works but
  the qiumibao score/event id is still missing.
- 061-C splits id diagnostics into `possible_zhibo8_ids`,
  `possible_qiumibao_ids`, and `possible_external_ids`; zhibo8 links such as
  `match1869145v.htm` must not be treated as qiumibao score ids.
- 061-D fixes the production team-normalization call chain and adds a qiumibao
  direct time-mapping diagnostic. qiumibao `start_time` is converted to UTC and
  compared with local `kickoff_at` in a 15 minute window. The report is
  dry-run only and prints `writes_db=false`.
- 061-E adds qiumibao raw field inspection, coarse football-like filtering,
  candidate detail output, and known-result team-id discovery. qiumibao remains
  a mixed rolling feed until raw fields prove a football/world-cup-only filter.
  Time matching and team-id discovery are dry-run diagnostics only.
- 062-A adds a read-only 500 result coverage audit:
  `python -m api.result_source_coverage_audit --source 500 --recent`.
  It reports started result coverage, overdue missing results, latest
  `results_sync` evidence, and optional half-time score field capability.
  Every mode prints `writes_db=false`.
- 062-A does not add a new external result source. It audits the current
  500/m500 chain first. 500 currently acts as odds source, sale-closed source,
  and candidate result source.
- 062-A production finding: `500_RESULT_SOURCE_SUFFICIENT` is currently valid
  for the first four started matches; `HT_SOURCE_UNAVAILABLE` is currently
  valid; qiumibao remains a generic diagnostic source.
- `--closed-missing` may legitimately return no rows. In that case the
  conclusion is `NO_CLOSED_MISSING_MATCHES`, meaning there is no current
  closed/scheduled started match missing a score. It is not a source gap.
- Half-time scores are audited separately. Missing `ht_home` / `ht_away` means
  hafu cannot be settled; full-time scores must not be used to infer half-time
  scores.
- Watch point: record 500 result ingest delay for the next match batch
  (`match_id`, teams, `kickoff_at`, estimated full time, first result seen time,
  delay minutes, and `results_sync` run time). If multiple matches remain
  missing more than one hour after full time, evaluate a temporary 15 minute
  `results_sync` interval during peak finished-match windows. Do not change the
  frequency preemptively.
- Watch point: postponed, abandoned, cancelled, and rescheduled matches remain
  an untested blind spot. They must not auto-settle, must not write full-time
  scores without clear source evidence, and must not be misclassified as
  `finished`.
- 063 adds `result_ingest_monitor`, an append-only observation monitor. It
  writes `result_ingest_observations` and `ops_log`, but never writes
  `matches`, scores, settlement, betting state, predictions, or odds snapshots.
- 063 monitor scheduler defaults to disabled:
  `ENABLE_RESULT_INGEST_MONITOR=false`,
  `RESULT_INGEST_MONITOR_INTERVAL_MINUTES=30`,
  `RESULT_INGEST_MONITOR_WINDOW_HOURS=36`.
- 063-hotfix: first-observed historical scored matches are
  `baseline_result_present`. They do not represent real ingest delay, do not
  participate in median/max delay, and must not trigger
  `RESULT_INGEST_SLOW_NEEDS_ACTION`. Only observed `result_missing ->
  result_present` transitions are true delay samples.
- `result_ingest_delay_minutes` is relative to `kickoff_at + 120min` and may
  include stoppage time, final-score confirmation, 500 source update timing,
  `results_sync` interval, and monitor observation precision. It is not pure
  post-score fetch latency.
- Do not adjust `results_sync` frequency until true measured delay samples
  exist.
- 063 abnormal status probe is non-production/test-only. Confirm mode is refused
  in production unless `ALLOW_TEST_PROBES=true`, uses only fixed `test-` match
  ids, and cleans up probe-created data.

### 042 Watchdog

- CLI: `python -m api.ops_health_check`
- daily runner: `python scripts/run_daily_ops_check.py`
- scheduler job: `ops_health_check_job`
- default interval: `OPS_HEALTH_CHECK_INTERVAL_MINUTES=30`
- stale threshold: `OPS_HEALTH_STALE_THRESHOLD_MINUTES=90`
- odds threshold: `ODDS_STALE_THRESHOLD_MINUTES=30`
- alert env: `OPS_ALERT_ENABLED=false`, `OPS_ALERT_WEBHOOK_URL=`
- alerts are optional; missing webhook must not fail health checks
- every run writes `ops_log.job_name='ops_health_check'`
- no-open-bets is `WARN`, not real settlement PASS

### Daily Operations Check

Daily manual SQL/curl bundles from task 041 are no longer the normal path.
Routine observation should use:

```bash
curl https://fifa2026.zeabur.app/api/health
```

The system runs `ops_health_check` every 30 minutes through the API scheduler and
writes `ops_log`. If `/api/health` reports `ops_health_status=FAIL`, enter the
API container and run:

```bash
python scripts/run_daily_ops_check.py
python -m api.ops_health_check
```

The Python runner does not require shell HTTP/database clients and prints only
`DATABASE_URL_SET=true/false`, never the connection string.

### 019 Emergency Repair

- backup: `PASS`
- migrations 001-007: `PASS`
- cleanup: `PASS`
- public probes: `PASS`

### 023 Security Closeout

- PostgreSQL public port closed: `PASS`
- password rotated: user confirmed
- `wc-p0-odds-crawler`, `wc-p1-model-worker`, `wc-p2-api` `DATABASE_URL` updated: user confirmed
- three services redeployed: user confirmed
- public probe after rotation: `PASS`

### P1-C

- status: `WAIT`
- blocker: 500.com trade date page returned current/future rows for requested 2022 dates; valid historical market odds CSV is still missing
- note: do not mark as `PASS` until real historical national-team market odds produce real RPS metrics.

### P1-C Prime

- status: framework ready / `WAIT`
- blocker: waiting for at least 30 evaluable finished matches
- command: `python -m model.p1c_prime_acceptance_report`
- note: any `best_w_dc` produced later is candidate evidence only and must not automatically update production fusion weights.

### P3-D

- status: WAIT
- official profile coverage: 48 / 48 teams
- players: 1,248 official FIFA squad rows
- rows: squad=1248, player_stats=1248, injuries=1248
- production DB writes: no
- GBM: `w_gbm=0`
- full tournament complete teams: 0 / 48
- teams with numeric recent stats: 0 / 48
- performance files: no committed `data/p3/real_performance_*.csv` yet
- GBM gray readiness: false, `w_gbm=0`
- note: FIFA official squad/profile data is complete, but recent minutes/goals/assists/xG/xA are still missing. This does not affect production predictions. Continue with `python -m model.p3_data_audit --write-backlog`.

### Betting

- status: disabled
- required environment: `BETTING_ENABLED=false`
- open gate: `python -m api.betting_open_gate`
- rule: the gate can recommend `READY`, but it never changes `BETTING_ENABLED`
- current expected blocker: `need_two_matchdays_auto_result_sync` until two matchdays of automatic result sync are observed

### Result State Guard

- `closed` means sale closed / stop selling, not match finished.
- P0 odds crawler must not set `status=finished` from `data-isend`.
- `closed` matches remain visible in upcoming lists and remain eligible for model-worker prediction while waiting for real results.
- `finished` / `completed` is settlement- and recap-ready only when `result_home` and `result_away` are both present.
- Diagnostic command: `python -m api.result_consistency_report`

## Safe Commands

```bash
python -m api.health_report
python -m api.ops_health_check
python scripts/run_daily_ops_check.py
python -m api.result_consistency_report
python -m api.result_overdue_report
python -m api.result_source_mapping_probe --source qiumibao --recent
python -m api.result_source_compare --all-overdue
python -m api.result_source_coverage_audit --source 500 --recent
python -m api.result_source_coverage_audit --source 500 --all-started
python -m api.result_source_coverage_audit --source 500 --closed-missing
python -m api.result_source_coverage_audit --source 500 --half-time-fields
python -m api.result_ingest_monitor --run-once --source 500 --window-hours 36
python -m api.result_ingest_monitor --summary --since-hours 48
python -m api.abnormal_status_probe --dry-run
python -m api.worldcup_live_probe --recent
python -m api.worldcup_live_probe --compare-local --all-overdue
python -m api.worldcup_live_probe --map-local --recent
python -m api.worldcup_live_probe --map-local --all-overdue
python -m api.worldcup_live_probe --dump-qiumibao-raw --limit 3
python -m api.worldcup_live_probe --map-qiumibao-by-time --upcoming
python -m api.worldcup_live_probe --map-qiumibao-by-time --all-overdue
python -m api.worldcup_live_probe --qiumibao-known-result-candidates --recent-finished --limit 20
python -m api.scheduler_observe
python -m api.betting_open_gate
python -m api.cleanup_test_data dry-run
python -m model.p1c_acceptance_report
python -m model.p1c_prime_acceptance_report
python -m model.p3_acceptance_report --real-dry-run
python -m ops.next_phase_acceptance
```

Cleanup writes require explicit confirmation:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

## Backup First

Before cleanup, restore, migration, or host movement:

```bash
bash deploy/backup_postgres.sh
```

`odds_snapshots` is not reproducible after the fact and must be protected first.

## Do Not Do

- Do not set `BETTING_ENABLED=true`.
- Do not treat betting gate `READY` as automatic permission to open betting; explicit user approval is still required.
- Do not run real `settlement_runner once` for a docs-only task.
- Do not write fake scores to real `500-` matches.
- Do not scrape external football data sites.
- Do not mark P1-C as `PASS` without real historical national-team market odds.
- Do not mark full P3-D as complete without full reviewed real CSV data and reliable numeric performance fields.
- Do not enable GBM weight from sample or header-only P3 data.
