# 2026 World Cup Prediction System

This repository powers a 2026 World Cup Jingcai prediction system and virtual-bankroll simulation game. It provides research, odds tracking, model predictions, EV signals, and read-only recap views. It does not provide real betting, ticket purchase, agency purchase, payment, or gambling services.

## Current Production Status

- Read-only prediction features are live.
- Odds collection is running in production.
- Model predictions and EV risk controls are live.
- Web and API are live.
- Recap skeleton is live.
- Betting remains closed: `BETTING_ENABLED=false`.
- 019 emergency production repair: `PASS`.
- 023 production security closeout: `PASS`.
- P1-C historical market backtest: `WAIT`, 500.com trade date probe did not yield valid 2022 historical rows.
- P3-D real team/player data: `WAIT`, missing reviewed real CSV.
- GBM remains disabled for production impact: `w_gbm=0`.

## Production Endpoints

- Web: https://worldcup2026.zeabur.app
- API: https://fifa2026.zeabur.app

## Core Modules

- `crawler/`: P0 odds crawler. Treat as frozen unless a dedicated P0 task is opened.
- `model/`: P1/P3 modeling, market processing, acceptance reports, and worker commands.
- `api/`: P2 API, auth, simulation betting gate, settlement utilities, scheduler, and health reports.
- `web/`: P2/P4 web UI.
- `db/migrations/`: additive database migrations.
- `ops/`: public probe and acceptance summarizers.
- `docs/`: production runbooks and status documents.

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection string from the deployment environment only.
- `JWT_SECRET`: API auth signing secret from the deployment environment only.
- `THE_ODDS_API_KEY`: optional historical odds key; never commit or print it.
- `BETTING_ENABLED=false`: must remain false until settlement and risk gates are explicitly approved.
- `ENABLE_API_SCHEDULER=true` in production after scheduler acceptance.
- `RESULTS_SYNC_INTERVAL_MINUTES=60`
- `SETTLEMENT_RUNNER_INTERVAL_MINUTES=30`
- `RUN_SCHEDULER_ON_STARTUP=false`
- `CORS_ORIGINS=https://worldcup2026.zeabur.app,http://localhost:5173`
- `VITE_API_BASE_URL=https://fifa2026.zeabur.app`
- `VITE_BETTING_ENABLED=false`

## Validation Commands

Python tests:

```powershell
$env:PYTHONPATH="."; python -m pytest tests/ -q
```

Web build and typecheck:

```bash
cd web
npm ci
npm run build
npm run typecheck
```

Production read-only probes:

```powershell
curl.exe -sS https://fifa2026.zeabur.app/api/health -o .\probe_health.json
curl.exe -sS https://fifa2026.zeabur.app/api/leaderboard -o .\probe_leaderboard.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359172" -o .\probe_mexico.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359200" -o .\probe_germany.json
$env:PYTHONPATH="."; python -m ops.probe_summary --mexico .\probe_mexico.json --germany .\probe_germany.json --leaderboard .\probe_leaderboard.json
```

P1-C/P3-D readiness:

```bash
python -m model.p1c_acceptance_report
python -m model.p3_acceptance_report --real-dry-run
python -m ops.next_phase_acceptance
```

## Backup And Restore

Self-hosted scripts live in `deploy/`:

```bash
bash deploy/backup_postgres.sh
bash deploy/restore_postgres.sh backups/worldcup_YYYYMMDD_HHMMSS.sql
```

Always back up PostgreSQL before migration, restore, cleanup, or infrastructure movement. `odds_snapshots` is a non-reproducible odds time series and must be protected first.

Do not commit:

- `backups/*.sql`
- `.env`
- `probe_*.json`
- real connection strings, passwords, JWT secrets, API keys, or tokens

## Safety Rules

- Do not modify original P0 table fields: `matches`, `odds_snapshots`, `crawl_runs`.
- Do not write fake scores to real `500-` match IDs or real Jingcai match numbers.
- Do not set `BETTING_ENABLED=true`.
- Do not mark P1-C as `PASS` without real historical national-team market odds.
- Do not mark P3-D as `PASS` without reviewed real team/player/injury CSV data.
- Do not enable GBM production weight from sample or header-only data.
- Do not scrape external sites in ways that bypass terms, login, or anti-bot restrictions.

## Disclaimer

竞彩返还率约 71%-73%，长期期望为负。本系统仅用于世界杯预测研究与虚拟资金模拟，不提供真实购彩服务，不构成投注建议，请理性娱乐。
