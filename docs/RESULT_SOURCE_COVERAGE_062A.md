# 062-A 500 Result Source Coverage Audit

This document describes the read-only audit for the current 500 / m500 result
chain. It does not add a new result source and does not write production data.

## Purpose

The current primary result path is `500_trade_jczq`. qiumibao remains downgraded
to a diagnostic source because its rolling feed is mixed and does not expose a
stable World Cup competition filter yet.

Before starting any external structured source project, run the 500 audit to
answer:

- how many started matches already have full-time results
- how many started matches are still missing results
- whether missing results are recent waiting windows or overdue gaps
- whether `results_sync` recently fetched and parsed source data
- whether half-time scores are available for hafu settlement

## Commands

Run inside the API container:

```bash
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --recent
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --all-started
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --closed-missing
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --finished
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --half-time-fields
```

Every mode prints:

```text
mode: dry-run
writes_db: false
```

The command only reads `matches` and `ops_log`. The optional half-time probe may
fetch the existing 500 result page, but it does not write or trigger fallback
logic.

## Status Meanings

Per-match audit statuses:

- `OK_RESULT_PRESENT`: full-time score is present.
- `WAIT_NOT_STARTED`: kickoff is in the future.
- `WAIT_RECENTLY_STARTED`: kickoff was less than 120 minutes ago.
- `MISSING_RESULT_OVERDUE`: kickoff was at least 120 minutes ago and no score is present.
- `FINISHED_NULL_ERROR`: status is finished/completed but full-time score is missing.
- `NON_FINISHED_HAS_RESULT_ERROR`: a non-finished row already has a full-time score.

Report conclusions:

- `500_RESULT_SOURCE_SUFFICIENT`: current 500 path covers started results well.
- `500_RESULT_SOURCE_PARTIAL`: 500 covers some results but has clear gaps or state issues.
- `500_RESULT_SOURCE_INSUFFICIENT`: 500 is structurally insufficient for World Cup results.

Half-time conclusions:

- `HT_SOURCE_AVAILABLE_PARSER_MISSING`
- `HT_SOURCE_UNAVAILABLE`
- `HT_COVERAGE_UNKNOWN`
- `HT_COVERAGE_OK`

## Half-Time Score Rule

Missing `ht_home` / `ht_away` directly affects hafu settlement.

If half-time scores are missing:

- hafu cannot be settled.
- full-time score must not be used to infer half-time score.
- a verified half-time source or parser support is required before hafu settlement.

## Current Source Roles

500 / m500 currently provides:

- odds snapshots
- sale-closed state
- candidate full-time results

It is not treated as a verified half-time source until the audit shows available
fields and parser extraction.

## External Source Candidate Pool

No external source is added in 062-A. Candidate sources remain only as future
options:

- FIFA official match data / existing P3 FIFA MatchData adapters
- TheSportsDB
- football-data.org
- Reuters/AP as a manually verified fallback only, not as an automatic structured source

Do not start external source integration until the 500 coverage audit has a
clear conclusion.
