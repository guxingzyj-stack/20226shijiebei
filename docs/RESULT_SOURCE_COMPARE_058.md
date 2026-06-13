# Result Source Compare 058

Status: dry-run comparison layer added. It does not write scores and does not
change the main result source.

## CLI

```bash
PYTHONPATH=. python -m api.result_source_compare --match-id 500-1359182
PYTHONPATH=. python -m api.result_source_compare --recent-finished
PYTHONPATH=. python -m api.result_source_compare --all-overdue
```

The report always includes:

```text
mode: dry-run
writes_db: false
```

## Source Roles

### 500_trade_jczq

```text
role: current results_sync main path and Jingcai odds/status source
official: no
structured: no, HTML page parser
best use: odds, Jingcai match numbers, sale/closed state, current main result path
limitation: should not be treated as the only reliable final-result source
```

### qiumibao_score

```text
role: score/status comparison source
official: no
structured: yes, JSON
best use: dry-run score/status cross-check, backup automatic-source candidate
write policy: candidate only; do not auto-write until mapping and reliability are proven
```

### qiumibao_events

```text
role: event and match-clock comparison source
official: no
structured: yes, JSON
best use: goal/event timeline, minute/status evidence, score-change audit
write policy: not a direct score writer
```

### zhibo8

```text
role: schedule/team/basic match information helper
official: no
structured: HTML
best use: schedule context and external match discovery
write policy: not recommended as final result source
```

### FIFA Match Centre

```text
role: future official structured-result candidate
official: yes
structured: potentially, pending stable adapter and mapping
current status: mapping missing in this layer
next step: build stable local match_id to FIFA match mapping
```

### Reuters / AP / FIFA Match Report

```text
role: human verified fallback evidence
official: Reuters/AP no, FIFA report yes
structured: no for news articles
best use: manual verified fallback CSV
write policy: never auto-write directly from article text
```

## Mapping Strategy

The comparison layer maps external rows to local matches conservatively:

```text
1. external_id equals local match_id or local numeric id without 500-
2. home_team + away_team + kickoff_at within a four-hour window
3. otherwise MAPPING_MISSING
```

It does not fuzzy-match uncertain team names. If mapping is unclear, the output
must be `MAPPING_MISSING`.

## Decision Rules

```text
OK_MATCH:
  local DB already has a result and external score agrees

NEEDS_VERIFIED_FALLBACK:
  local DB is missing result, but qiumibao_score says finished with score

CONFLICT_NEEDS_REVIEW:
  local DB / 500 / qiumibao scores disagree

MAPPING_MISSING:
  no reliable mapping from external source to local match_id

WAIT_SOURCE:
  source is not finished, not available, or not enough evidence yet
```

## Why No Automatic Score Write

This layer is intentionally read-only because:

```text
qiumibao is not an official source
500_trade_jczq is HTML and can miss final results
FIFA Match Centre mapping is not complete yet
news sources need human verification
multi-source conflicts must never auto-write
```

When the report returns `NEEDS_VERIFIED_FALLBACK`, use the verified fallback CSV
flow with:

```text
source_url
verified_by
retrieved_at
```

Do not use ad hoc SQL to write scores.

## Path To FIFA As Main Source

Before FIFA can become the main result source:

```text
build local match_id to FIFA match id mapping
write parser tests for final score and halftime score
run dry-run comparisons for multiple matchdays
prove no conflicts with existing verified results
keep 500_trade_jczq as odds/Jingcai source
require explicit approval before switching main source
```
