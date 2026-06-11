# P3 Manual Data Guide

P3-B uses manual CSV files only. Do not scrape FBref, Transfermarkt, or other sites in this stage, and do not invent player data.

## Files

Place controlled CSV data in:

- `data/p3/manual_squad_template.csv`
- `data/p3/manual_player_stats_template.csv`
- `data/p3/manual_injuries_template.csv`

The checked-in files are templates. If they only contain headers, validation passes but import writes zero player rows.

## Required Columns

Squad:

```text
player_key,name,team,position,birth_date,market_value,source
```

Player season stats:

```text
player_key,season,club,minutes,goals,assists,xg,xa,source
```

Injuries:

```text
player_key,team,status,injury_type,expected_return,source
```

All imported rows are stored with `source='manual_csv'`. The original CSV row is preserved in `raw`.

## Commands

```bash
python -m model.p3_ingest validate
python -m model.p3_ingest import --dry-run
python -m model.p3_ingest import
python -m model.p3_ingest build-team-features --dry-run
python -m model.p3_ingest build-team-features
```

P3-C sample pipeline commands:

```bash
python -m model.p3_ingest validate --sample
python -m model.p3_ingest import --sample --dry-run
python -m model.p3_ingest build-team-features --sample --dry-run
python -m model.p3_train train --sample --dry-run
python -m model.p3_acceptance_report --sample
```

The files in `data/p3/samples/` are a minimal engineering sample for pipeline tests, not official production player data. P3-C validates the engineering chain only:

```text
manual CSV -> validate -> dry-run import -> team_features dry-run -> GBM unavailable/insufficient -> w_gbm=0
```

This does not mean real player data has been connected. It does not affect P1 production predictions, and GBM weight remains `0`.

## Recent Performance Gate

P3-D recent performance data must use reviewed files matching:

```text
data/p3/real_performance_*.csv
```

Use `data/p3/real_performance_squad_template.csv` only as a schema example. Rows marked `EXAMPLE_ONLY_DO_NOT_USE` are rejected by validation and must never be treated as real data.

Recent performance files require `source`, `retrieved_at`, and `confidence` for every row. `minutes_recent`, `goals_recent`, and `assists_recent` are required numeric fields. `xg_recent` and `xa_recent` may be blank only when `notes` contains `unavailable`.

GBM remains gated until every team reaches at least 70% complete recent performance coverage. Until then, `w_gbm=0` and P1 production predictions are unchanged.

## Safety

- Missing player data should produce `missing_*` feature flags, not a crash.
- `team_features` is additive and does not change P1 predictions.
- Do not write fake injuries, market values, minutes, xG, or xA.
- Keep `BETTING_ENABLED=false`; P3 data does not open betting.
- `import --sample` without `--dry-run` requires `--confirm IMPORT_SAMPLE_DATA`.
