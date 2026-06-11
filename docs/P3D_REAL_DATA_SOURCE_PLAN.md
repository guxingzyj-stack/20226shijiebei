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
data/p3/real_performance_*.csv
```

The dry-run loader prefers these real CSV files when present. If they are absent, it validates the header-only templates and returns `WAIT`.

Required fields:

```text
team,player_name,position,age,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,injury_status,source,retrieved_at,confidence,notes
```

Performance CSV files must use:

```text
team,player_name,club,minutes_recent,goals_recent,assists_recent,xg_recent,xa_recent,source,retrieved_at,confidence,notes
```

The `real_performance_*.csv` rows are strict: `minutes_recent`, `goals_recent`, `assists_recent`, `xg_recent`, and `xa_recent` must all be present and numeric. Empty performance values are rejected instead of silently treated as real model input.

Validation rules:

- `source` must be nonempty.
- `retrieved_at` must be nonempty.
- `confidence` must be `high`, `medium`, or `low`.
- Numeric fields must parse as numbers when provided.
- GBM gray release requires every tournament team to have complete recent performance rows for at least 70% of its official squad.

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

Official FIFA squad profile CSV rows are now present for all 48 teams:

```text
teams: 48
players: 1,248
squad rows: 1,248
player_stats rows: 1,248
injury rows: 1,248
official profile rows: 1,248
```

Current dry-run status:

```text
status: ok
result: WAIT
rows_validated: 3744
source_coverage: squad=1248, player_stats=1248, injuries=1248
teams_with_official_profile: 48 / 48
teams_with_numeric_recent_stats: 0 / 48
performance_files: none
gbm_ready: false
would_write_db: false
w_gbm: 0
```

This is full official squad/profile coverage, not full P3-D model readiness. It does not write production DB and does not enable GBM. Numeric performance fields remain intentionally blank because no permitted reviewed source has been collected for recent minutes, goals, assists, xG, or xA.

When compliant `real_performance_*.csv` files are added and every team reaches the 70% coverage threshold, dry-run reports `gbm_ready=true` but keeps `w_gbm=0`. Non-dry-run local/test mode can report gray `w_gbm=0.2`; production P1 fusion weights are not changed automatically.

Official source:

```text
https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf
```

Use the player data audit before claiming P3 completion:

```bash
python -m model.p3_data_audit --write-backlog
```

Regenerate the official CSVs from a local copy of the FIFA PDF:

```bash
python -m model.p3_fifa_squad_pdf --pdf path/to/SquadLists-English.pdf --output-dir data/p3 --retrieved-at 2026-06-12
```
