# P1-A Model Core

This package contains the P1-A model foundations:

- Elo helpers
- Dixon-Coles score probability helpers
- Market devig helpers
- RPS metrics
- Team name mapping
- Minimal PostgreSQL migration and smoke-check commands

Commands:

```bash
python -m model.cli download-history
python -m model.apply_migrations
python -m model.cli fit-dc
python -m model.cli predict-once
python -m model.smoke_check
python -m model.cli apply-migrations
python -m model.cli smoke-check
python -m model.model_worker
```

Database credentials must come from `DATABASE_URL` in the environment or `.env`.

P1-B uses the martj42 international results CSV, rolling Elo features, Dixon-Coles
time-decayed likelihood fitting, Shin devig for `had`/`hhad`, proportional devig
for score-derived market probabilities, and EV writes based on latest P0 odds snapshots.
