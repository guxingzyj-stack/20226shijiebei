# P2-A API

FastAPI backend for the simulated World Cup Jingcai game.

This service is for virtual balance simulation only. It does not place real
bets, buy lottery tickets, or provide purchasing services.

## Environment

- `DATABASE_URL`: PostgreSQL connection string.
- `JWT_SECRET`: HS256 signing secret.

Both values must be provided through environment variables. Do not commit real
credentials.

## Run

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Endpoints

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/matches?status=upcoming`
- `GET /api/matches/{id}`
- `GET /api/matches/{id}/odds-history?play_type=had`
- `POST /api/bets`
- `GET /api/bets/me`
- `GET /api/leaderboard`
- `GET /api/model/suggestion?match_id=...`
- `GET /api/health`

Bet placement always uses latest server-side `odds_snapshots` odds and ignores
client-provided odds.
