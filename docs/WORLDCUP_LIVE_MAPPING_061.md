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
