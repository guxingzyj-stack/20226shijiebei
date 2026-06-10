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
python -m model.cli backtest-market
python -m model.cli discover-odds-api
python -m model.cli fetch-validation-odds
python -m model.cli backtest-market --source the_odds_api
python -m model.cli predict-once
python -m model.smoke_check
python -m model.cli apply-migrations
python -m model.cli smoke-check
python -m model.model_worker
```

Database credentials must come from `DATABASE_URL` in the environment or `.env`.
The Odds API historical backtest credentials must come from `THE_ODDS_API_KEY`
in the environment. The key is never written to cache files or logs.

Unified test command:

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="."; python -m pytest tests/ -q
```

P1-B uses the martj42 international results CSV, rolling Elo features, Dixon-Coles
time-decayed likelihood fitting, Shin devig for `had`/`hhad`, proportional devig
for score-derived market probabilities, and EV writes based on latest P0 odds snapshots.

P1-D can fetch 2022 World Cup historical `h2h` snapshots from The Odds API into
`data/validation_odds/the_odds_api_2022_world_cup_h2h.csv`. The market backtest
uses the cached decimal 1X2 odds and fails validation when fewer than 30 matches
are matched.
