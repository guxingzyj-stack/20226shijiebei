# Validation Odds

`manual_validation_odds_template.csv` defines the auditable schema for historical single-match 1X2 odds when a machine-downloadable source does not cover the validation tournament.

Required columns:

```csv
competition,date,home_team,away_team,home_score,away_score,home_odds,draw_odds,away_odds,bookmaker,source_url,closing_or_opening,notes
```

Rules:

- Only fill this file with real, source-verifiable historical match odds.
- Do not use current 2026 odds as historical validation odds.
- Do not use futures/outright/champion/qualification odds.
- `source_url` must point to an auditable source page or downloadable file.
- `closing_or_opening` must state whether the price is closing, opening, or otherwise documented by the source.

The template is not used to pass P1 validation. P1-C requires at least 30 matched real historical 1X2 odds rows.
