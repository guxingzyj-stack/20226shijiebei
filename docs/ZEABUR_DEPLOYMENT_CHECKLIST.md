# Zeabur Deployment Checklist

Zeabur UI fields require user confirmation. Do not mark them verified unless the user provides evidence from the Zeabur UI or public probes.

## wc-p2-api

User should confirm:

- watch path: `/api`
- auto deploy: enabled
- current deployment commit: latest expected commit
- start command uses the normal API server command, not a temporary acceptance command
- env `ENABLE_API_SCHEDULER=true`
- env `RUN_SCHEDULER_ON_STARTUP=false`
- env `BETTING_ENABLED=false`
- env `DATABASE_URL` uses the internal PostgreSQL connection, not the temporary public endpoint
- env `CORS_ORIGINS` includes `https://worldcup2026.zeabur.app`

## wc-p2-web

User should confirm:

- watch path: `/web`
- auto deploy: enabled
- current deployment commit: latest expected commit
- env `VITE_API_BASE_URL=https://fifa2026.zeabur.app`
- env `VITE_BETTING_ENABLED=false`
- exposed container port matches nginx configuration

## wc-p1-model-worker

User should confirm:

- watch path: `/model`
- auto deploy: enabled
- current deployment commit: latest expected commit
- start command: `python -m model.model_worker`
- env `DATABASE_URL` uses the internal PostgreSQL connection
- env `PYTHONUNBUFFERED=1`

## wc-p0-odds-crawler

User should confirm:

- `crawler/` remains frozen unless a dedicated P0 task is opened
- service is running
- m500 source is selected when available
- crawl ok logs are present
- env `DATABASE_URL` uses the internal PostgreSQL connection
- one-off full scan command, when needed:
  `PYTHONPATH=. python -m crawler.odds_crawler_once --source 500 --full-scan`

## PostgreSQL

User should confirm:

- public endpoint is closed
- password was rotated after the temporary public exposure
- services use the new internal connection string
- no public connection string is kept in docs, code, logs, or chat

## Public Verification After UI Check

```powershell
curl.exe -sS https://fifa2026.zeabur.app/api/health -o .\probe_health.json
curl.exe -sS https://fifa2026.zeabur.app/api/leaderboard -o .\probe_leaderboard.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359172" -o .\probe_mexico.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359200" -o .\probe_germany.json
$env:PYTHONPATH="."; python -m ops.probe_summary --mexico .\probe_mexico.json --germany .\probe_germany.json --leaderboard .\probe_leaderboard.json
```

Do not commit `probe_*.json`.
