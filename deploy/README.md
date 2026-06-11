# Docker Compose Self-Hosting Runbook

This is the emergency self-hosting plan for leaving Zeabur. The system remains
a virtual balance simulation game only. It does not provide real lottery
purchase, real betting, or proxy purchase features.

## Golden Rule

Back up PostgreSQL before any migration, restore, host move, or destructive
operation. Do not continue if you do not have a fresh PostgreSQL backup.

## Services

- `postgres`: PostgreSQL database, persistent Docker volume.
- `crawler`: P0 odds crawler.
- `model-worker`: P1 predictions and EV worker.
- `api`: P2 FastAPI backend.
- `web`: P2 React/Vite static frontend served by nginx.

## VPS Size

- Minimum: 2 vCPU / 4 GB RAM
- Recommended: 4 vCPU / 8 GB RAM
- Disk: start at 40 GB SSD or larger, monitor PostgreSQL backup growth.

## Install Docker On Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in after adding your user to the `docker` group.

## Configure Environment

```bash
cp .env.example .env
nano .env
```

Set strong local values:

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `JWT_SECRET`
- `VITE_API_BASE_URL`
- `CORS_ORIGINS`
- `MODEL_WORKER_ENABLED`
- `THE_ODDS_API_KEY` only if paid historical odds fetch is needed

Do not commit `.env`.

For Compose internal networking, `DATABASE_URL` should use host `postgres`, for
example:

```text
postgresql://worldcup_app:REPLACE_ME@postgres:5432/worldcup
```

## Start

Before starting on a migrated host, restore a verified PostgreSQL backup first.

```bash
docker compose up -d --build
docker compose ps
bash deploy/check_health.sh
```

## Backup

Always run this before migration or restore:

```bash
bash deploy/backup_postgres.sh
```

Backups are written to:

```text
backups/worldcup_YYYYmmdd_HHMMSS.sql
```

## Restore

Restore only after confirming you have selected the correct SQL file:

```bash
bash deploy/restore_postgres.sh backups/worldcup_YYYYmmdd_HHMMSS.sql
```

The script requires typing `RESTORE` before it writes to PostgreSQL.

## Logs

```bash
docker compose logs -f crawler
docker compose logs -f api
docker compose logs -f model-worker
docker compose logs -f postgres
docker compose logs -f web
```

## Optional Host Nginx

`deploy/nginx.conf` is a host-level reverse proxy template:

- `/api/` -> `localhost:8000`
- `/` -> `localhost:8080`

Install it only if you want a single public domain in front of the Compose
ports. Remember to add the public web origin to `CORS_ORIGINS`.

## Failure Priority

1. Protect PostgreSQL. Stop risky services before database damage spreads.
2. Protect `crawler`, because current odds snapshots are the most time-sensitive data.
3. Restore `api` and `web`.
4. Restore `model-worker` after database and crawler are stable.

Useful emergency commands:

```bash
docker compose stop model-worker api web
docker compose logs -f postgres
docker compose logs -f crawler
bash deploy/backup_postgres.sh
```

## Model Worker Switch

Set this in `.env`:

```text
MODEL_WORKER_ENABLED=false
```

Then restart:

```bash
docker compose up -d model-worker
```

When disabled, the container sleeps instead of running predictions.
