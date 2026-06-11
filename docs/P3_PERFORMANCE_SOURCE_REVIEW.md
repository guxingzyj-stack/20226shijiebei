# P3 Performance Source Review

This project currently does not have a compliant recent performance CSV. Official 48-team squad/profile rows are present, but recent club minutes, goals, assists, xG, and xA still require a reviewed source.

## Reviewed Options

### Kaggle player stat datasets

Status: not adopted.

Reason: common public player-stat CSVs are often derived from FBref or similar sites. Because this task forbids FBref scraping or bypassing site restrictions, these datasets are not accepted without a clear license and source audit.

### FootyStats CSV exports

Status: not adopted.

Reason: may be usable only with the correct plan/license and explicit export permission. No authorized export has been provided to this repository yet.

### Understat and third-party API wrappers

Status: not adopted.

Reason: coverage is league-specific and may not cover all national-team squad players. Third-party wrappers also need license and usage review before use.

### FBref / Transfermarkt

Status: prohibited for this stage.

Reason: do not scrape, bypass, or automate collection from these sites. Do not paste scraped rows into the CSV and label them as reviewed data.

## Accepted Path

Use one of:

- user-provided CSV with documented source permission;
- official or licensed data export with redistribution/use rights checked;
- manual reviewed CSV where every row includes `source`, `retrieved_at`, and `confidence`.

## Current Decision

`data/p3/real_performance_squad_template.csv` is a preparation template only. It is not production data.

Current gate:

```text
real_performance_csv_exists=false
performance_rows_validated=0
gbm_ready=false
w_gbm=0
result=WAIT
```
