# Result Source Mapping 059

Status: qiumibao / FIFA match-id mapping probe added. This is a read-only
source-discovery layer and never writes scores.

## Reference Findings

Reference reviewed:

```text
C:\Users\Administrator\Documents\nova-agent\BaiLongma\src\worldcup.js
```

Confirmed qiumibao rules:

```text
score URL today: https://bifen4pc.qiumibao.com/json/v2/list.htm
score URL by date: https://bifen4pc.qiumibao.com/json/{date}/v2/list.htm
events URL: https://dc4pc.qiumibao.com/dc/matchs/data/{date}/match_event_{match_id}.htm
external_id source: score JSON row field id
events match_id: qiumibao score JSON id, not local 500-... match_id
referer: https://www.zhibo8.cc/
```

The qiumibao score feed may only expose a current/recent window. If the target
match is not in that window, the probe reports
`source_available_but_match_not_in_window` instead of pretending the source is
unavailable.

## CLI

```bash
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --recent
PYTHONPATH=. python -m api.result_source_mapping_probe --source qiumibao --match-id 500-1359182
PYTHONPATH=. python -m api.result_source_mapping_probe --source fifa --recent
PYTHONPATH=. python -m api.result_source_mapping_probe --all
```

All reports include:

```text
mode: dry-run
writes_db: false
```

## Mapping Status Values

```text
matched:
  external match reliably maps to the local match.

source_fetch_error:
  external source cannot be fetched or parsed.

source_empty:
  external source is reachable but returned no match list.

source_available_but_match_not_in_window:
  external source is reachable, but the target match is absent from its returned
  current/recent window.

team_name_mismatch:
  kickoff time is close but team names do not match.

kickoff_time_mismatch:
  team names match but kickoff time is outside the safety window.

ambiguous_candidates:
  multiple candidates matched; do not choose automatically.

mapping_missing:
  required external id is missing or mapping cannot be trusted.

fifa_mapping_missing:
  FIFA Match Centre needs a separate local match_id to FIFA id/url mapping.
```

## Team Normalization

Normalization is only used for matching. It does not alter user-facing display
names.

Rules:

```text
remove half-width spaces
remove full-width spaces
remove invisible whitespace / BOM / zero-width characters
apply Unicode NFKC normalization
map common English aliases and country short names
```

Covered examples:

```text
加 拿 大 / Canada -> 加拿大
波 黑 / Bosnia / Bosnia and Herzegovina -> 波黑
墨 西 哥 / Mexico -> 墨西哥
南 非 / South Africa -> 南非
韩 国 / Korea Republic / South Korea -> 韩国
捷 克 / Czechia / Czech Republic -> 捷克
美 国 / United States / USA -> 美国
巴拉圭 / Paraguay -> 巴拉圭
```

## qiumibao Events

`qiumibao_events` only fetches after `qiumibao_score` has produced a mapped
external id.

Output fields:

```text
seen
mapping_status
external_id
minute
events_count
goals_count
score_from_events
parser_error
```

`score_from_events` is report-only evidence derived from event scores. It is not
allowed to write results automatically.

## FIFA Match Centre

Current status:

```text
mapping_status: fifa_mapping_missing
suggested_next_step: build_fifa_match_id_mapping
```

FIFA should remain a separate 060-style task because it needs a durable mapping
file or table:

```text
local match_id
FIFA match id or URL
home_team
away_team
kickoff_at
source_url
verified_by / provenance
```

## Why This Still Does Not Auto-Write Scores

This layer is still read-only because:

```text
qiumibao is not an official result source
source coverage windows can be incomplete
mapping can be ambiguous
events are secondary evidence, not a final score writer
FIFA mapping is not complete
conflicts require human review
```

Only after repeated dry-run evidence shows stable mapping and no conflicts can
qiumibao be considered as a backup automatic comparison source. It should not
become a score writer without explicit approval.
