# P4 Recap And Knockout Plan

P4 is not active yet. This document records the safe activation rules.

## Recap

- User and model recap curves require enough settled bets and finished matches.
- If finished matches are insufficient, API functions must return `insufficient_finished_matches`.
- Do not fabricate user curves, model-follow returns, or calibration charts.
- Mid-group-stage reports start only after enough finished group matches exist.

## Knockout

- Knockout advancement probabilities are enabled only after real qualified teams are known.
- Champion simulation starts only after the 32-team field and knockout bracket are clear.
- No pre-bracket champion claims should be surfaced as production predictions.

## Safety

- P4 remains read-only until explicitly promoted.
- P4 must not modify P0 tables or betting balances.
