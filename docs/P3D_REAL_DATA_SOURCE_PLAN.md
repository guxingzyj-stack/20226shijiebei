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

When real reviewed data is ready, place it in:

```text
data/p3/manual_real_squad.csv
data/p3/manual_real_player_stats.csv
data/p3/manual_real_injuries.csv
```

The dry-run loader prefers these real CSV files when present. If they are absent, it validates the header-only templates and returns `WAIT`.

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

First small-batch real CSV rows are now present for:

```text
Mexico
South Africa
Germany
Curaçao
```

Current dry-run status:

```text
status: ok
result: PASS
rows_validated: 68
source_coverage: squad=40, player_stats=16, injuries=12
would_write_db: false
w_gbm: 0
```

This is a small-batch data-readiness PASS only. It is not full P3-D completion, does not write production DB, and does not enable GBM. Many numeric performance fields remain intentionally blank because no reliable public source was collected for recent minutes, goals, assists, xG, or xA in this dry-run.
