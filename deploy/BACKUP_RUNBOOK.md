# PostgreSQL Backup Runbook

Back up PostgreSQL before migrations, restores, infrastructure moves, or cleanup operations.

## Critical Tables

The most important tables are:

- `odds_snapshots`
- `matches`
- `crawl_runs`
- `model_versions`
- `predictions`
- `ev_signals`
- `users`
- `bets`

`odds_snapshots` is time-sensitive and cannot be regenerated after the fact. Protect it first.

## Linux / macOS

```bash
bash deploy/backup_postgres.sh
```

The script reads database settings from environment variables or `.env` and writes:

```text
backups/worldcup_YYYYMMDD_HHMMSS.sql
```

It does not print database passwords.

## Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File deploy/backup_postgres.ps1
```

## Restore

Only restore after taking a fresh backup and confirming the SQL file path:

```bash
bash deploy/restore_postgres.sh backups/worldcup_YYYYMMDD_HHMMSS.sql
```

The restore script requires typing `RESTORE`.
