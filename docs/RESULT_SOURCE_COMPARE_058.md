# Result Source Compare 058

Status: dry-run comparison layer added and 058-B mapping/decision rules fixed.
It does not write scores and does not change the main result source.

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

Each match comparison also includes:

```text
external_confirmed: true/false
external_confirming_sources: [...]
mapping_status:
  qiumibao_score: mapped/missing/unknown
  qiumibao_events: mapped/missing/unknown
  fifa_match_centre: mapped/missing/unknown
next_step: ...
```

For source discovery and candidate diagnostics, use the 059 mapping probe first:

```bash
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --match-id 500-1359182
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --recent
PYTHONPATH=. python -m api.result_source_mapping_probe --source fifa --recent
```

For the 060 BaiLongma-style live chain dry-run, use:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --recent
PYTHONPATH=. python -m api.worldcup_live_probe --compare-local --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --compare-local --all-overdue
```

This adds zhibo8 schedule context around qiumibao score/event rows. It is still a
comparison source only and returns `writes_db: false`.

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
1. Normalize both local and external team names before matching.
2. external_id equals local match_id or local numeric id without 500-
3. home_team + away_team + kickoff_at within a four-hour window
4. otherwise MAPPING_MISSING
```

Team normalization removes half-width spaces, full-width spaces, invisible
whitespace, BOM/zero-width characters, and applies NFKC normalization. This is
only for matching; it does not change display names.

Examples:

```text
加 拿 大 -> 加拿大
波 黑 -> 波黑
墨 西 哥 -> 墨西哥
南 非 -> 南非
韩 国 -> 韩国
捷 克 -> 捷克
```

It still does not fuzzy-match uncertain team names. If mapping is unclear, the
output must be `MAPPING_MISSING`.

`qiumibao_events` requires qiumibao's own match id from the mapped
`qiumibao_score` row. It must not use local `500-...` ids. If no qiumibao match
id is available, the events source returns `mapping_missing` and does not fetch
the event URL, avoiding false HTTP 404 noise.

059 adds a dedicated mapping probe that reports candidate rows with raw team
names, normalized team names, kickoff deltas, `external_id`, candidate count,
and specific mapping statuses such as `team_name_mismatch`,
`kickoff_time_mismatch`, `ambiguous_candidates`, and
`source_available_but_match_not_in_window`.

059-B adds `parser_missing_team_fields` for qiumibao rows that are reachable and
parsed but do not expose home/away team names, for example rows containing only
`left.id`, `left.score`, `right.id`, and `right.score`. Those rows must not be
classified as `source_available_but_match_not_in_window`.

## Decision Rules

```text
OK_MATCH:
  local DB already has a result, at least one external score source is seen=true,
  that external score agrees with local DB, and no source conflicts exist

LOCAL_DB_ONLY:
  local DB has a result, but all external sources are missing, unmapped, not
  found, or unavailable. This is not an OK confirmation; it means external
  mapping/confirmation still needs work.

NEEDS_VERIFIED_FALLBACK:
  local DB is missing result, but qiumibao_score says finished with score

CONFLICT_NEEDS_REVIEW:
  local DB / 500 / qiumibao scores disagree

MAPPING_MISSING:
  no reliable mapping from external source to local match_id

WAIT_SOURCE:
  source is not finished, not available, or not enough evidence yet
```

The 058 initial production dry-run exposed this important bug: finished local
matches were returned as `OK_MATCH` even when `500_trade_jczq`,
`qiumibao_score`, `qiumibao_events`, and `fifa_match_centre` had not actually
confirmed the score. 058-B fixes that by requiring `external_confirmed=true`
for `OK_MATCH`.

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
