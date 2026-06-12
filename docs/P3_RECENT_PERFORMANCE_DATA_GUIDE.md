# P3 Recent Performance Data Guide

P3 recent performance data now uses P3-Light by default. P3-Light uses reviewed `minutes_recent`, `goals_recent`, and `assists_recent` first, while `xg_recent` and `xa_recent` are optional. Do not scrape FBref or Transfermarkt, do not bypass rate limits or access controls, and do not invent player performance numbers.

## Modes

P3-Light:

- uses `minutes_recent`, `goals_recent`, and `assists_recent`;
- allows blank `xg_recent` and `xa_recent` only when `notes` contains `unavailable`;
- can report `candidate_w_gbm=0.2` after every team reaches 70% coverage;
- never changes production P1 fusion weights automatically.

P3-Full:

- future upgrade path for licensed xG/xA data;
- requires a higher-grade authorized data source;
- should be evaluated separately before raising any GBM production weight.

P3-FIFA-MatchData:

- uses FIFA World Cup official Match Centre match performance data;
- is `data_scope=fifa_world_cup_match_performance`;
- is not pre-match club recent form (`not_club_recent_form=true`);
- may only appear after real World Cup matches expose official player-level data;
- keeps P3-Light at `WAIT` when URL mapping or player-level data is unavailable.

## Target File

Create one or more reviewed files matching:

```text
data/p3/real_performance_*.csv
```

The recommended filename is:

```text
data/p3/real_performance_squad.csv
```

Do not rename `data/p3/real_performance_squad_template.csv` into production data until every example row has been removed and the source has been reviewed.

## Required Columns

```text
team,player_name,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,source,retrieved_at,confidence,notes
```

Required non-empty values:

```text
team
player_name
minutes_recent
goals_recent
assists_recent
source
retrieved_at
confidence
notes
```

`club` is recommended but may be blank when the source does not provide a current club. `xg_recent` and `xa_recent` may be blank only when `notes` contains `unavailable`.

## Validation Rules

- `team` and `player_name` must match the official 48-team FIFA squad CSV already in `data/p3/manual_real_squad.csv`.
- `minutes_recent`, `goals_recent`, and `assists_recent` must be numeric and greater than or equal to 0.
- `xg_recent` and `xa_recent` must be numeric and greater than or equal to 0 when present.
- `xg_recent` and `xa_recent` are not required for P3-Light; do not fill unknown values with fake `0`.
- `confidence` must be `high`, `medium`, or `low`.
- `source` must identify the licensed or manually reviewed source.
- `retrieved_at` must be present so the dataset can be audited later.
- Rows containing `EXAMPLE_ONLY_DO_NOT_USE` are rejected.

## GBM Gate

GBM remains disabled unless every team has at least 70% of official squad players with complete P3-Light recent performance rows.

Dry-run behavior:

```text
gbm_ready=false
w_gbm=0
would_write_db=false
```

When coverage is sufficient in a non-production build, the framework may report:

```text
candidate_w_gbm=0.2
production_w_gbm=0
```

This is only a candidate gray weight. It must not change P1 production fusion weights without a separate reviewed deployment.

## Source Probe

Before creating a real performance CSV, run:

```bash
PYTHONPATH=. python -m tools.p3_performance_source_probe
```

The probe does not collect player rows. It only checks whether a candidate source appears accessible, auditable, and capable of providing at least `minutes_recent`, `goals_recent`, and `assists_recent`.

Current status:

```text
real_performance_squad.csv: missing
blocker: no_legal_recent_performance_source
```

If the source probe returns `WAIT` or `FAIL`, do not generate `data/p3/real_performance_squad.csv`.

## FIFA MatchData Adapter

FIFA MatchData is an official World Cup match-performance layer, not a club recent-form source. It should be used for in-tournament performance tracking after matches start.

Prepare URL mapping:

```bash
PYTHONPATH=. python -m tools.p3_probe_fifa_match_centre --matches data/p3/fifa_match_targets.csv --report-out docs/P3_FIFA_MATCH_DATA_REPORT.md
```

If `data/p3/fifa_match_targets.csv` is missing, the probe writes `data/p3/fifa_match_targets_template.csv` and reports:

```text
result=WAIT
needs_fifa_match_url_mapping=true
```

Build the FIFA match sample only after official FIFA match URLs are mapped:

```bash
PYTHONPATH=. python -m tools.p3_build_fifa_match_performance_csv --matches data/p3/fifa_match_targets.csv --squad data/p3/manual_real_squad.csv --out data/p3/real_performance_fifa_match_sample.csv --unmatched-out data/p3/real_performance_unmatched_fifa.csv --report-out docs/P3_FIFA_MATCH_DATA_REPORT.md
```

Do not guess FIFA match URLs, do not bypass login or anti-bot controls, and do not fill players without official player-level evidence.

## Building From User-Provided CSV

If a compliant user-provided or licensed export exists, place it at:

```text
data/p3/real_performance_squad_source.csv
```

or put one or more CSV files in:

```text
data/p3/raw_performance/
```

Then run:

```bash
PYTHONPATH=. python -m tools.p3_build_real_performance_csv --dry-run
PYTHONPATH=. python -m tools.p3_build_real_performance_csv --out data/p3/real_performance_squad.csv
```

The build command rejects unmatched players, missing `source`, missing `retrieved_at`, invalid `confidence`, and template rows. It reports `coverage_by_team` before writing the final CSV.

## Commands

```bash
PYTHONPATH=. python -m model.p3_ingest validate-real --dry-run
PYTHONPATH=. python -m model.p3_ingest build-team-features-real --dry-run
PYTHONPATH=. python -m model.p3d_acceptance_report --dry-run
PYTHONPATH=. python -m ops.next_phase_acceptance
```

These commands must not write the production database.
