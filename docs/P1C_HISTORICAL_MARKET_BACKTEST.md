# P1-C Historical Market Backtest

P1-C is the market-fusion backtest gate. It must use real historical national-team market odds. It must not invent odds, reuse club-league odds as national-team evidence, or report fake RPS metrics.

## Commands

```bash
python -m model.p1c_backtest discover-sources
python -m model.p1c_backtest validate
python -m model.p1c_backtest run --dry-run
python -m model.p1c_backtest report
python -m model.p1c_backtest fetch-odds-api --dry-run
python -m model.p1c_acceptance_report
```

## Source Priority

1. The Odds API historical endpoint, only when `THE_ODDS_API_KEY` is present. The key must never be printed, saved, or committed. If historical quota or paid access is unavailable, report `NOT_AVAILABLE`.
2. Football-Data CSV, only if it contains international/national-team market odds. Club-league CSV is not acceptable for this validation.
3. Manual CSV import using `data/p1c/manual_historical_market_odds_template.csv`.

## Manual CSV Fields

```text
match_date,home_team,away_team,home_score,away_score,market_home_odds,market_draw_odds,market_away_odds,bookmaker,snapshot_time,source
```

The current template contains only a header. Header-only data is valid as a template but is not enough to compute official metrics.

## Metrics

When enough real rows exist, the backtest reports:

```text
market_rps
dc_rps
blended_rps
best_w_dc
```

Weights are searched over `w_dc` in `[0, 1]` at step `0.05`.

## Current Acceptance State

The 500.com historical route was probed after the temporary service reported page access. A stricter backfill probe rejected the page because `https://trade.500.com/jczq/?date=2022-11-20` returned current/future World Cup rows with `data-matchdate` in 2026, not the requested 2022 historical date.

Current blocker:

```text
500.com date parameter does not return 2022 historical rows in the probed trade page.
manual_validation_odds.csv has not been generated.
```

If no real historical market odds source is available, the correct result is:

```text
status: insufficient_historical_market_data
result: WAIT
```

Do not write `PASS` until real historical market odds are available and the report produces real metrics.
