# Security Rotation Runbook

This runbook closes the remaining 019 security risk after a public PostgreSQL connection was used for emergency backup and cleanup.

Do not paste or commit `DATABASE_URL`, PostgreSQL passwords, JWT secrets, tokens, or backup files.

## Current Risk

```text
PostgreSQL public endpoint was exposed during operations.
Observed public endpoint: 43.130.69.126:32644
Database connection material may have appeared in screenshots.
```

The target final state is:

```text
PostgreSQL public endpoint closed
PostgreSQL password rotated
All internal services use Zeabur internal DATABASE_URL
BETTING_ENABLED=false remains unchanged
Public probes pass after redeploy
```

## 1. Close PostgreSQL Public Port

In Zeabur:

```text
Zeabur -> postgresql service -> Network -> disable public port exposure -> save
```

Current public endpoint to close:

```text
43.130.69.126:32644
```

After closing the public port, local Windows connections to that endpoint should fail. That is expected.

Local verification:

```powershell
Test-NetConnection -ComputerName 43.130.69.126 -Port 32644
```

Expected:

```text
TcpTestSucceeded : False
```

## 2. Rotate PostgreSQL Password

In Zeabur:

```text
Zeabur -> postgresql service -> Database / Usage / Environment Variables -> reset password
```

After reset, copy only the new internal connection string into service environment variables. Do not send it to chat.

The internal host should be:

```text
postgresql.zeabur.internal
```

Do not keep using:

```text
43.130.69.126:32644
```

## 3. Update Service DATABASE_URL

Update these services:

```text
wc-p0-odds-crawler
wc-p1-model-worker
wc-p2-api
```

Requirement:

```text
DATABASE_URL uses Zeabur internal host postgresql.zeabur.internal
DATABASE_URL does not use 43.130.69.126:32644
```

Do not change:

```text
BETTING_ENABLED=false
ENABLE_API_SCHEDULER=true
RUN_SCHEDULER_ON_STARTUP=false
```

## 4. Redeploy Services

Redeploy:

```text
wc-p0-odds-crawler
wc-p1-model-worker
wc-p2-api
```

Do not redeploy `wc-p2-web` unless web code changed.

Do not run migrations as part of this security rotation. Migrations 001-007 are already recorded as applied.

## 5. Public Probe Recheck

After redeploying the three services:

```powershell
cd "C:\Users\Administrator\Documents\世界杯预测"
$env:PYTHONPATH="."

curl.exe -sS https://fifa2026.zeabur.app/api/health -o .\probe_health.json
curl.exe -sS https://fifa2026.zeabur.app/api/leaderboard -o .\probe_leaderboard.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359172" -o .\probe_mexico.json
curl.exe -sS "https://fifa2026.zeabur.app/api/matches/500-1359200" -o .\probe_germany.json

python -m ops.probe_summary --mexico .\probe_mexico.json --germany .\probe_germany.json --leaderboard .\probe_leaderboard.json
```

Targets:

```text
/api/health returns {"ok":true}
leaderboard has_roi: true
leaderboard exposes_internal_id: false
leaderboard test_user_count: 0
Mexico ev_model_version_aligned: true
Mexico unprotected_high_ev_count: 0
Germany ev_model_version_aligned: true
probe_summary result: PASS
```

## 6. Betting Stays Closed

Keep:

```text
BETTING_ENABLED=false
VITE_BETTING_ENABLED=false
```

Do not open betting until real finished-match settlement has been observed and P1-C historical market backtest numbers are complete.
