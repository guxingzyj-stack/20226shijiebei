# 2026 World Cup Full Schedule Seed

This project now keeps a 104-match schedule seed at:

```text
data/schedule/worldcup2026_schedule.csv
```

Sources used for the seed:

- FIFA official match schedule page: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums
- Sky Sports day-by-day schedule with UK kick-off times: https://www.skysports.com/football/news/11095/13481245/world-cup-2026-fixture-schedule-and-uk-kick-off-times-day-by-day-breakdown-of-all-104-matches-including-england-scotland

Sky lists kick-off times in UK time. June/July 2026 UK time is BST, so the seed stores `kickoff_at` as UTC by subtracting one hour.

## Status Model

Seeded matches use:

```text
status = no_market
```

Meaning:

```text
The match is on the official tournament schedule, but current Jingcai/500.com market odds are not available yet.
```

`no_market` matches:

- are visible in `/api/matches?status=upcoming`
- show `暂未开售，等待竞彩赔率`
- do not enter `model-worker` prediction generation
- do not enter settlement / recap finished samples
- do not contain fake odds or fake scores

When 500.com later opens a group-stage match, the crawler attempts to merge the matching `wc26-xxx` seed row into the real `500-xxx` row using kickoff time and canonical team names.

Knockout seed rows still contain placeholders such as `Match 89 winners`. They should stay as schedule placeholders until real teams are known.

## Commands

Validate the local seed:

```bash
PYTHONPATH=. python -m api.schedule_seed validate
```

Production dry-run:

```bash
PYTHONPATH=. python -m api.schedule_seed import --dry-run
```

Production import after dry-run is safe:

```bash
PYTHONPATH=. python -m api.schedule_seed import --confirm IMPORT_WC26_SCHEDULE
```

Expected effect in the current production database:

```text
matches count should move toward 104 total tournament rows.
Already-opened 500.com rows should not be duplicated.
Unopened rows should be inserted as wc26-xxx / no_market.
```

Do not run this before confirming that the existing database backup remains available.
