# P3 Player Data Execution Plan

P3 is not blocked by code anymore. It is blocked by reviewed player data coverage and usable recent performance numbers.

## Current Truth

Current real CSV state:

```text
teams_total: 48
complete_teams: 0
partial_teams: 4
missing_teams: 44
teams_with_numeric_stats: 0
result: WAIT
```

The four partial teams are useful for validating the pipeline, but they are not enough to enable GBM or change P1 predictions.

## Acceptance Gates

A team is considered complete only when it has:

```text
>= 10 reviewed squad rows
>= 4 reviewed player_stats rows
>= 4 player_stats rows with numeric recent performance fields
>= 1 injury/status row
source, retrieved_at, confidence on all rows
```

Numeric recent performance fields are:

```text
minutes_recent
goals_recent
assists_recent
xg_recent
xa_recent
```

Blank values are allowed during collection, but they keep the team incomplete.

## Commands

Audit current coverage:

```bash
PYTHONPATH=. python -m model.p3_data_audit
```

Generate collection backlog:

```bash
PYTHONPATH=. python -m model.p3_data_audit --write-backlog
```

Validate real CSV:

```bash
PYTHONPATH=. python -m model.p3_ingest validate-real --dry-run
```

Preview team features:

```bash
PYTHONPATH=. python -m model.p3_ingest build-team-features-real --dry-run
```

Overall P3-D readiness:

```bash
PYTHONPATH=. python -m model.p3d_acceptance_report
```

## Backlog File

The audit writes:

```text
data/p3/p3_collection_backlog.csv
```

Use that file as the working queue. Do not delete rows manually to make the report pass; fix the source CSV coverage instead.

## Data Rules

- No FBref / Transfermarkt automated scraping.
- No fake players, fake minutes, fake xG/xA, or assumed injury status.
- Each row must keep `source`, `retrieved_at`, and `confidence`.
- If a source only confirms squad membership but not recent minutes or xG/xA, leave numeric fields blank and keep the team incomplete.
- `w_gbm` remains `0` until the P3 feature model beats or matches P1 in backtest.
- P3 data does not open betting; keep `BETTING_ENABLED=false`.

## Immediate Work Order

1. Fill teams from `data/p3/p3_collection_backlog.csv`.
2. For each team, collect at least 10 squad rows.
3. For core players, collect recent minutes/goals/assists/xG/xA only from allowed reviewed sources.
4. Add one injury/status row per team; use `unknown` when no reliable injury source exists, with a note.
5. Re-run `model.p3_data_audit`.
6. Import to production only after audit is `PASS` and a database backup exists.
