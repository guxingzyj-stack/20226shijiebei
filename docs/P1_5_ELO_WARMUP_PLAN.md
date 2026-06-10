# P1.5 Elo Warmup Plan

## Goal

- Use international results from 2000-01-01 onward for Elo rolling warmup.
- Use matches from 2015-01-01 onward for Dixon-Coles training.
- Feed pre-match Elo values into Dixon-Coles fitting to avoid future leakage.
- Keep P2 unblocked while P1-Full historical market odds backtest continues separately.

## Implementation Steps

1. Update `model/history.py` so downloads stay unchanged but loaders can request a warmup window from 2000-01-01 and a training window from 2015-01-01.
2. Update `model/elo.py` to roll ratings from the 2000 warmup start date.
3. Update `model/fit_dc.py` so all matches receive pre-match Elo from the warmup pass, while the optimizer trains only on matches dated 2015-01-01 or later.
4. Continue writing latest ratings to `team_ratings`.
5. Extend `sanity-check` to compare the current P1 2015-only Elo behavior with the warmup version.
6. Extend backtest reports with `elo_start_date` and `training_start_date`.

## Acceptance

- `team_ratings` row count remains reasonable for international teams.
- Argentina, Brazil, France, Germany, Spain, England, Portugal, Netherlands and similar strong teams rank plausibly.
- Dixon-Coles `k` does not sit on an optimizer boundary.
- `sanity-check` continues to pass.
- DC RPS is not worse than the current P1 version.

## Notes

- The change must preserve the existing P0 tables and `crawler/` behavior.
- The warmup period is only for rating state. It must not train the Dixon-Coles likelihood before 2015-01-01.
- P1-Full historical market odds remains pending a paid historical odds source and should not block P2.
