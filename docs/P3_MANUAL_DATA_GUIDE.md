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

## Safety

- Missing player data should produce `missing_*` feature flags, not a crash.
- `team_features` is additive and does not change P1 predictions.
- Do not write fake injuries, market values, minutes, xG, or xA.
- Keep `BETTING_ENABLED=false`; P3 data does not open betting.
