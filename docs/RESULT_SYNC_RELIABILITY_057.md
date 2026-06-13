# Result Sync Reliability 057

Status: observability hardening complete. This document describes the current
result-sync main path and the fallback decision flow.

## Current Main Result Source

```text
source_name: 500_trade_jczq
source_type: html_page
default URL: https://trade.500.com/jczq/
official: no
structured: no
```

`api.results_sync` fetches the 500.com Jingcai page HTML, decodes GB18030/UTF-8,
parses table rows, and extracts `500-...` match ids plus status/score fields.

It is not currently using:

```text
FIFA Match Centre structured result API
m500 structured result API
Jingcai official structured result API
Reuters/AP automatic writer
```

## Status Mapping

The parser marks a row as:

```text
finished: text or attributes contain finished / 完场 / 已完 / 赛果
postponed: text or attributes contain postponed / abandoned / cancelled / 延期 / 推迟 / 取消
live: text contains live / 进行 / 中场
scheduled: default
```

Only `finished` rows with full-time score are eligible to update real matches.

## Score Parsing

Full-time score comes from:

```text
data-score
data-full-score
data-result-score
score
first score-like text in a finished row
```

Half-time score comes only from:

```text
data-half-score
data-ht-score
half-score
ht-score
second explicit score-like text in a finished row
```

If half-time score is missing, `ht_home/ht_away` stay `NULL`. The system must
never infer half-time from full-time score.

## Skipped Reasons

`results_sync` now reports `skipped_reasons`:

```text
not_finished_status: source row is not finished
missing_result_score: source row says finished but full-time score is missing
match_id_not_found: source row match_id does not exist in local matches
already_finished_with_result: local match already has a completed result
row_error: row-level exception
```

The CLI prints these reasons, and `ops_log.summary` stores them for `/api/health`.

## Overdue Closed Matches

The read-only command:

```bash
PYTHONPATH=. python -m api.result_overdue_report
```

lists matches that satisfy:

```text
status IN ('closed', 'scheduled')
result_home/result_away are NULL
kickoff_at < now() - 3 hours
```

Suggested actions:

```text
RUN_RESULTS_SYNC: scheduler is stale, no recent results_sync, or latest results_sync errored
NEEDS_VERIFIED_FALLBACK: recent results_sync ran but the match is still overdue
```

The report only generates a checklist. It never writes scores.

For deeper dry-run source comparison, use:

```bash
PYTHONPATH=. python -m api.result_source_compare --match-id 500-1359182
PYTHONPATH=. python -m api.result_source_compare --all-overdue
PYTHONPATH=. python -m api.result_source_compare --recent-finished
```

This compares local DB, 500_trade_jczq, qiumibao score JSON, qiumibao events,
and FIFA mapping status without writing the database.

058-B tightened the comparison rules:

```text
OK_MATCH now requires external_confirmed=true.
LOCAL_DB_ONLY means the local DB has a score but no external source confirmed it.
qiumibao_events only fetches after qiumibao_score maps a real qiumibao match id.
Team-name matching normalizes visible, full-width, and invisible spaces.
```

If a recently finished match returns `LOCAL_DB_ONLY`, treat it as a mapping or
confirmation gap, not as a verified multi-source result.

## Health Fields

`/api/health` now includes:

```json
{
  "latest_results_sync_at": "...",
  "latest_results_sync_status": "ok",
  "latest_results_sync_source": "500_trade_jczq",
  "latest_results_sync_finished_updated": 0,
  "latest_results_sync_skipped": 20,
  "latest_results_sync_skipped_reasons": {
    "not_finished_status": 14,
    "missing_result_score": 3
  },
  "result_overdue_closed_count": 0,
  "result_overdue_closed_matches": []
}
```

If `result_overdue_closed_count > 0`, `ops_health_blockers` includes
`result_overdue_closed_matches`.

## Why Canada vs Bosnia Was Missed

The observed production run:

```text
matches_seen: 20
finished_updated: 0
skipped: 20
errors: 0
```

means the main HTML source was reachable and parsed rows, but no parsed row
qualified as "finished with full-time score for a local match that still needed
an update." With the new diagnostics, the next equivalent event will show
whether the cause was:

```text
source_not_found / match_id_not_found
source_not_finished / not_finished_status
missing_result_score / parser_no_score_field
already_finished_with_result
```

## Fallback Source Policy

Recommended main source:

```text
current: 500_trade_jczq HTML source
future candidate: FIFA Match Centre structured result data, if a stable mapping exists
```

Recommended automatic backup candidates:

```text
official structured source with stable match ids or reviewed match mapping
FIFA Match Centre only after mapping and parser tests pass
```

Manual verified fallback sources:

```text
Reuters
AP
FIFA official match report pages
other reputable sources reviewed by a human
```

Do not automatically write from news articles. News sources may support the
verified CSV fallback only when the row includes:

```text
source_url
verified_by
retrieved_at
```

If multiple sources disagree, do not write scores automatically. Mark the match
as `NEEDS_VERIFIED_FALLBACK`.

## Safety

```text
Do not enable betting.
Do not manually UPDATE matches.result_home/result_away.
Do not overwrite existing results.
Do not infer half-time score.
Do not expose DATABASE_URL or secrets.
```
