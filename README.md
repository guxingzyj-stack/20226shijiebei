# 2026 World Cup Jingcai Prediction System

This repository powers a World Cup prediction and virtual-bankroll simulation system. It does not provide real betting, ticket purchase, agency purchase, or payment integration.

## Current Status

- P0 crawler: production odds collection is running; do not change `crawler/` without a dedicated P0 task.
- P1 model-worker: Dixon-Coles + market fusion is live; matrix recalibration, EV fuse, and model-version isolation are implemented.
- P2 API/Web: FastAPI and Web are live; `BETTING_ENABLED=false` remains mandatory.
- P3-A: feature-model infrastructure and optional GBM stubs are present; GBM is zero-weight unless explicitly trained and validated.
- P4: recap and knockout modules are skeletons only; no real knockout/champion probabilities are exposed yet.

## Production Services

Use the actual service names shown in Zeabur or your self-hosting platform. The logical services are:

- PostgreSQL database
- P0 crawler service
- P1 model-worker service
- P2 API service
- P2 Web service

Never commit production connection strings, passwords, JWT secrets, API keys, or tokens.

## Environment Variables

Required or commonly used variables:

- `DATABASE_URL`: PostgreSQL connection string, from the deployment environment only.
- `JWT_SECRET`: API auth signing secret, from the deployment environment only.
- `THE_ODDS_API_KEY`: optional historical odds key.
- `BETTING_ENABLED=false`: must remain false until settlement and risk gates are explicitly approved.
- `ENABLE_API_SCHEDULER=false`: scheduler is opt-in.
- `RESULTS_SYNC_INTERVAL_MINUTES=60`
- `SETTLEMENT_RUNNER_INTERVAL_MINUTES=30`
- `RUN_SCHEDULER_ON_STARTUP=false`
- `CORS_ORIGINS`: comma-separated browser origins.
- `VITE_API_BASE_URL`: Web build-time API base URL.
- `VITE_BETTING_ENABLED=false`

## Commands

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

Docker Compose validation:

```bash
docker compose config
```

P1 acceptance:

```bash
python -m model.cli acceptance-report
```

P2 acceptance:

```bash
python -m api.acceptance_report
python -m api.scheduler_observe
```

Safe settlement smoke, test data only:

```bash
python -m api.settlement_smoke run
python -m api.settlement_smoke cleanup --prefix test-settlement-...
```

## Backup And Restore

Self-hosted scripts live in `deploy/`:

```bash
bash deploy/backup_postgres.sh
bash deploy/restore_postgres.sh backups/worldcup_YYYYmmdd_HHMMSS.sql
```

Always back up PostgreSQL before migration, restore, or infrastructure move. Never print database passwords in logs.

## Safety Rules

- Do not modify P0 table original fields: `matches`, `odds_snapshots`, `crawl_runs`.
- Do not write fake scores to real `500-` match IDs or real Jingcai match numbers.
- Test settlement data must use `test-settlement-*` matches and `codex_blocker_*` users.
- Scheduler jobs must not create test data.
- EV over 15% is research-only and must not enter model suggestions.

## Disclaimer

竞彩返还率约 71%–73%，长期期望为负。本系统为预测研究与虚拟资金模拟游戏，理性娱乐，不构成投注建议，不接入真实购彩。
