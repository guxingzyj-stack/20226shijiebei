# WorldCup Live Mapping 061

Status: dry-run local mapping added. This layer maps `WorldCupLiveMatch` rows
from the 060 zhibo8/qiumibao live chain to local `matches.match_id` candidates.

It does not write the database.

## Safety Boundary

This task does not:

```text
change BETTING_ENABLED
open betting
write matches.result_home/result_away
write halftime scores
modify bets/users/balance
modify predictions
modify odds_snapshots
modify P1/P3 weights
run migrations
commit secrets, .env files, probe JSON, or backups
```

## CLI

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --recent
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --match-id 500-1359189
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --upcoming
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --all-overdue
```

Each report includes:

```text
mode: dry-run
writes_db: false
source_fetch_ok
zhibo8_matches_seen
qiumibao_matches_seen
merged_matches_count
mapping_status_summary
comparison_status_summary
conflicts_count
overdue_count
```

## Team Normalization

`normalize_team_name()` is shared with the 058/059 mapping layer and is used only
for matching diagnostics. It does not change page display names.

Normalization handles:

```text
half-width spaces
full-width spaces
invisible whitespace
spaces between Chinese characters
Unicode NFKC normalization
English aliases
bracket variants
```

Covered examples:

```text
美 国 -> 美国
巴 拉 圭 -> 巴拉圭
加 拿 大 -> 加拿大
墨 西 哥 -> 墨西哥
USA / United States -> 美国
Brazil -> 巴西
Morocco -> 摩洛哥
Germany -> 德国
Scotland -> 苏格兰
Turkey -> 土耳其
```

## Candidate Scoring

Function:

```python
score_live_to_local_match(live_match, local_match)
```

Scoring:

```text
normalized home team matches: +0.35
normalized away team matches: +0.35
kickoff delta <= 30 minutes: +0.20
kickoff delta <= 120 minutes: +0.10
local 500 numeric id matches zhibo8_ref/qiumibao_id: +0.20
match_num/code related: +0.10
```

Confidence:

```text
high: matched and score >= 0.90
medium: score >= 0.75
low: score >= 0.50
none: below 0.50
```

## Mapping Status

```text
matched:
  both teams match after normalization and kickoff is within 30 minutes.

mapping_missing:
  no candidate has enough team/time/id evidence.

team_name_mismatch:
  kickoff is close but normalized team names do not both match.

kickoff_time_mismatch:
  both teams match but kickoff time is too far away.

ambiguous_candidates:
  multiple candidates have close scores, so the system refuses to pick one.

low_confidence:
  partial signals exist but are not enough for a safe match.

source_window_missing:
  live source returned no row for the local match window.
```

## Comparison Status

After a live row maps to a local match, the report compares scores read-only:

```text
OK_MATCH:
  local score and live score both exist and agree.

LOCAL_DB_ONLY:
  local score exists but live source has no usable mapped score.

LIVE_SOURCE_ONLY:
  live source has a result not represented locally.

NEEDS_VERIFIED_FALLBACK:
  local score is missing and live source says finished with score.

CONFLICT_NEEDS_REVIEW:
  local score and live score conflict.

WAIT_SOURCE:
  live source is mapped but not finished.

MAPPING_MISSING:
  no safe local-live mapping.

AMBIGUOUS_CANDIDATES:
  mapping candidates are too close to choose.
```

`NEEDS_VERIFIED_FALLBACK` is a human-review signal only. It is not permission to
write scores automatically.

## Relationship To 058 / 059 / 060

```text
058: lower-level source comparison rules.
059: source discovery and qiumibao/FIFA mapping diagnostics.
060: BaiLongma-style zhibo8 + qiumibao live source chain.
061: higher-level local match_id mapping and candidate scoring.
```

`api.worldcup_live_probe` should be the preferred diagnostic entry point after
061. 058/059 remain useful for lower-level parser and source-shape debugging.

## Shadow Observation Path

Before any automatic fallback can be considered:

```text
run --map-local --recent and --map-local --all-overdue for multiple matchdays
confirm no CONFLICT_NEEDS_REVIEW rows
confirm ambiguous candidates are not auto-selected
confirm NEEDS_VERIFIED_FALLBACK rows are manually verified
keep writes_db=false
require explicit approval before any writer is added
```

## 061-B Hardening Notes

061-B hardens diagnostics in three ways:

```text
1. zhibo8 dump now prints raw links and possible qiumibao id candidates.
2. zhibo8 rows and local mapping rows print raw and normalized team names.
3. a zhibo8/local match without a qiumibao id reports:
   qiumibao_link_status: zhibo8_matched_but_qiumibao_unlinked
   next_step: EXTRACT_QIUMIBAO_ID_FROM_ZHIBO8_LINKS
```

`zhibo8_matched_but_qiumibao_unlinked` means the schedule layer can identify the
local match, but the score/event layer is not yet bound. It is not score
evidence and must not trigger result writes.

Additional normalization examples covered by tests:

```text
Qatar -> 卡塔尔
Switzerland -> 瑞士
Australia -> 澳大利亚
```

Expected production dry-run behavior:

```text
writes_db=false
dump-zhibo8 exposes zhibo8_raw_links and possible_qiumibao_ids
map-local exposes qiumibao_link_status and next_step
if qiumibao_match_id is null, the report must say unlinked explicitly
```

## 061-C ID Split And Normalization Fix

061-C corrects two production diagnostic issues:

```text
1. normalized_* output must use the shared api.result_source_mapping.normalize_team_name path.
2. zhibo8 match ids such as match1869145v.htm are not qiumibao ids.
```

ID fields are now split:

```text
possible_zhibo8_ids:
  ids from zhibo8 URLs or zhibo8 match refs, for example match1869145v.htm.

possible_qiumibao_ids:
  ids from qiumibao / bifen4pc / dc4pc / match_event links only.

possible_external_ids:
  numeric ids from other third-party links where the source is uncertain.
```

If `possible_qiumibao_ids` is empty but `possible_zhibo8_ids` is present, the
chain has schedule-level evidence only. It must still report qiumibao as
unlinked and must not infer a score/event binding.

## 061-D Qiumibao Time Mapping Diagnostic

061-D adds a separate dry-run path for qiumibao score rows. This path does not
depend on zhibo8 ids. It compares qiumibao `start_time` to local
`matches.kickoff_at` in UTC.

Command:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --upcoming
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --all-overdue
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id 500-1359172
```

Rules:

```text
qiumibao start_time Unix seconds -> UTC datetime
local kickoff_at -> UTC datetime
safe window: <= 15 minutes
writes_db: false
```

Status values:

```text
matched_by_time:
  exactly one qiumibao row matches one local match in the 15 minute window.

no_qiumibao_time_candidate:
  no qiumibao row is close enough by UTC kickoff time.

ambiguous_qiumibao_candidates:
  one local match has multiple qiumibao rows in the window.

ambiguous_local_candidates:
  one qiumibao row is close enough to multiple local matches.
```

This diagnostic is the preferred path for qiumibao score-id discovery. zhibo8
ids such as `match1869145v.htm` remain `possible_zhibo8_ids`; they are not
qiumibao score ids.

Team normalization now uses one shared path:

```text
Unicode NFKC
remove invisible whitespace
remove all regular whitespace with split/join
normalize bracket variants
apply normalized alias keys
```

It is used for zhibo8 rows, local rows, live candidates, and qiumibao time
diagnostics. It does not write normalized names back to the database.

## 061-E Raw Field Inspection And Candidate Details

061-E confirms that the qiumibao score endpoint is a mixed-event rolling feed,
not a World Cup-only or football-only endpoint. A pure `start_time` match is not
a stable unique key by itself.

Raw inspection:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --dump-qiumibao-raw --limit 3
```

The raw dump prints:

```text
source_url
rows_seen
raw row keys
one-level left/right fields
classification_field_candidates
writes_db: false
```

If classification fields such as `sport`, `category`, `league`, `competition`,
or `tournament` are absent, the system reports `not_found` and falls back to a
structural dry-run filter only.

Football-like filter:

```text
classified_football:
  explicit football/soccer/football-like classification field.

classified_non_football:
  explicit basketball/tennis/volleyball style classification field.

football_like:
  no explicit classification, period/score shape is compatible with football.

non_football_like:
  period contains quarter/set/game markers or score is too high for football.

unknown_sport:
  classification fields exist but do not clearly identify the sport.
```

Enhanced time mapping:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id 500-1359182 --show-candidates --limit 10
PYTHONPATH=. python -m api.worldcup_live_probe --map-qiumibao-by-time --match-id 500-1359182 --football-like-only --show-candidates --limit 10
```

Candidate details include qiumibao id, raw/UTC start time, time delta, status,
period, score, half score, left/right ids, sport filter status,
classification fields, and raw keys. When `--football-like-only` is used the
report also prints before/after candidate counts and filtered-out summaries.

Known-result team-id discovery:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --qiumibao-known-result-candidates --recent-finished --limit 20
```

This is only an investigation aid. It compares local finished scores to
qiumibao candidates within 30 minutes and prints possible `left_id/right_id`
directions (`same_order`, `reversed_order`, `no_score_match`). It does not build
a team-id mapping table and does not confirm any result automatically.
# 062-A Result Source Coverage Note

qiumibao remains a diagnostic source only. The feed is mixed and does not yet
provide a reliable World Cup-only result channel. Before adding any external
structured source, use the 500 coverage audit:

```bash
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --recent
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --all-started
PYTHONPATH=. python -m api.result_source_coverage_audit --source 500 --half-time-fields
```

The audit is read-only and prints `writes_db=false`. It treats 500/m500 as the
current odds, sale-closed, and candidate result source. Missing half-time fields
mean hafu cannot be settled; full-time scores must not be used to infer
half-time scores.
