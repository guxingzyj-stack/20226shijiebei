# P3-D Real Data Source Plan

P3-D prepares real team/player feature ingestion without enabling production GBM and without scraping sites that restrict automated access.

## Current Scope

- Manual real CSV templates are provided first.
- Dry-run validation and feature preview are available.
- No full production import is enabled by default.
- `w_gbm` remains `0`.
- P1 predictions are not affected.

## Commands

```bash
python -m model.p3_ingest validate-real --dry-run
python -m model.p3_ingest build-team-features-real --dry-run
python -m model.p3_acceptance_report --real-dry-run
python -m model.p3d_acceptance_report
```

## Templates

```text
data/p3/manual_real_squad_template.csv
data/p3/manual_real_player_stats_template.csv
data/p3/manual_real_injuries_template.csv
```

Required fields:

```text
team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes
```

Validation rules:

- `source` must be nonempty.
- `retrieved_at` must be nonempty.
- `confidence` must be `high`, `medium`, or `low`.
- Numeric fields must parse as numbers when provided.

## Source Policy

Allowed:

- Human-reviewed CSV from permitted sources.
- Public data explicitly licensed for reuse.
- Manual notes with source and confidence metadata.

Not allowed:

- FBref / Transfermarkt scraping that bypasses terms, login, or anti-bot restrictions.
- Fabricated player or injury data.
- Treating engineering sample CSV as production data.

## Current Acceptance State

With no real CSV rows, the correct result is:

```text
status: no_real_data_csv
result: WAIT
w_gbm: 0
```

This is safe and expected. It is not a production feature-model PASS.

