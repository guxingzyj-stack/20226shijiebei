# 063 Result Ingest Monitor

`result_ingest_monitor` replaces manual time-point patrols with append-only
observation snapshots.

## Safety

- Does not write `matches.result_home/result_away`.
- Does not write `ht_home/ht_away`.
- Does not trigger `official_result_fallback`.
- Does not trigger `settlement_runner`.
- Does not change betting state.
- Writes only `result_ingest_observations` and `ops_log`.

`result_ingest_observations` is an observation log. Business logic may read it
for dashboards and summaries, but it must not drive settlement, score writes, or
betting gates directly.

## Migration

```text
db/migrations/008_result_ingest_observations.sql
```

The table allows repeated snapshots for the same `match_id`. There is no unique
constraint on `match_id`.

## Manual Commands

Deploy first with the scheduler disabled:

```text
ENABLE_RESULT_INGEST_MONITOR=false
```

Then run manually inside the API container:

```bash
PYTHONPATH=. python -m api.result_ingest_monitor --run-once --source 500 --window-hours 36
PYTHONPATH=. python -m api.result_ingest_monitor --summary --since-hours 48
```

## Scheduler

Optional environment variables:

```text
ENABLE_RESULT_INGEST_MONITOR=false
RESULT_INGEST_MONITOR_INTERVAL_MINUTES=30
RESULT_INGEST_MONITOR_WINDOW_HOURS=36
```

Default is disabled. Only after manual `--run-once` succeeds repeatedly should
the scheduler be enabled:

```text
ENABLE_RESULT_INGEST_MONITOR=true
```

The scheduler job name is:

```text
result_ingest_monitor
```

Failures are caught and logged; monitor failure must not stop the API process.

## Summary Status

- `RESULT_INGEST_BASELINE_ONLY`: scored matches were already scored before the
  monitor first observed them, so no real ingest-delay sample exists yet.
- `RESULT_INGEST_HEALTHY`: observed finished results appeared within 60 minutes and no consistency issue exists.
- `RESULT_INGEST_SLOW_OBSERVE`: a match is 60-120 minutes past estimated full time without a result, or ingest delay is over 60 minutes.
- `RESULT_INGEST_SLOW_NEEDS_ACTION`: a match is more than 120 minutes past estimated full time without a result, or ingest delay is over 120 minutes.
- `RESULT_INGEST_INCONSISTENT`: finished-with-null or non-finished-with-result state is observed.

## Observation Fields

Important fields:

```text
match_id
home_team
away_team
kickoff_at
estimated_fulltime_at
first_result_seen_at
result_ingest_delay_minutes
results_sync_run_at
audit_status
```

`estimated_fulltime_at = kickoff_at + 120 minutes` is only an observation
estimate. It must not be used to write scores or settle bets.

## Baseline Versus Measured Delay

When the monitor is enabled for the first time, historical matches may already
have `result_home/result_away`. Those matches are classified as
`baseline_result_present`.

Baseline matches:

- do not prove the real ingest time
- do not participate in median/max delay
- must not trigger `RESULT_INGEST_SLOW_NEEDS_ACTION`

Only this transition creates a true delay sample:

```text
result_missing -> result_present
```

If `matches.updated_at` is later than `kickoff_at` and a missing-to-present
transition was observed, the monitor may use `updated_at` as the best available
first-result time. Otherwise, it uses the first monitor observation time, whose
precision is approximately the monitor interval.

Summary fields:

```text
baseline_result_present_matches
true_delay_measured_matches
delay_unknown_matches
delay_precision_note
delay_precision_minutes
```

`result_ingest_delay_minutes` is estimated relative to `kickoff_at + 120min`.
It includes stoppage time, final-score confirmation, 500 source update timing,
`results_sync` interval, and monitor observation precision. It is not pure
"time spent fetching after the score appeared on 500".

## Frequency Policy

The current 500 source is sufficient for the first four started matches, but the
next match batch still needs delay observation. If multiple matches remain
missing more than one hour after full time, evaluate a temporary 15 minute
`results_sync` interval during peak windows. Do not change frequency
preemptively.
