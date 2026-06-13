# WorldCup Live Source 060

Status: dry-run probe added. This layer does not write scores, predictions,
odds, bets, users, balances, or model weights.

## Reference

Reference reviewed:

```text
C:\Users\Administrator\Documents\nova-agent\BaiLongma\src\worldcup.js
```

The BaiLongma `/worldcup` chain uses three source layers:

```text
1. zhibo8 homepage: https://www.zhibo8.cc/
   Role: schedule, teams, basic match context, zhibo8 saishi id.

2. qiumibao score JSON: https://bifen4pc.qiumibao.com/json
   Role: score, status, qiumibao match id, left.id, right.id, half-score hints.

3. qiumibao event JSON: https://dc4pc.qiumibao.com/dc/matchs/data
   Role: minute/event timeline after a qiumibao match id is known.
```

## Implemented Files

```text
api/sources/zhibo8.py
api/worldcup_live_source.py
api/worldcup_live_probe.py
tests/api_tests/test_worldcup_live_source.py
```

## CLI

All commands are dry-run and include:

```text
mode: dry-run
writes_db: false
```

Commands:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --recent
PYTHONPATH=. python -m api.worldcup_live_probe --match-id 500-1359182
PYTHONPATH=. python -m api.worldcup_live_probe --dump-zhibo8 --limit 5
PYTHONPATH=. python -m api.worldcup_live_probe --dump-qiumibao --limit 5
PYTHONPATH=. python -m api.worldcup_live_probe --compare-local --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --compare-local --all-overdue
```

## Output Fields

Top-level output:

```text
source_fetch_ok
zhibo8_matches_seen
qiumibao_matches_seen
merged_matches_count
mapping_status_summary
conflicts_count
overdue_count
```

Merged `WorldCupLiveMatch` rows include:

```text
source_name
source_fetch_ok
zhibo8_match_ref
zhibo8_url
zhibo8_home_team
zhibo8_away_team
zhibo8_kickoff_at
qiumibao_match_id
qiumibao_left_id
qiumibao_right_id
qiumibao_status
qiumibao_period_cn
qiumibao_score_home
qiumibao_score_away
qiumibao_half_score_home
qiumibao_half_score_away
home_team
away_team
normalized_home_team
normalized_away_team
kickoff_at
status
score
half_score
minute
events
mapping_status
mapping_reason
parser_error
```

## Mapping

The merge prefers:

```text
zhibo8 saishi id == qiumibao score row id
```

If ids do not match, it can use a conservative kickoff-time fallback:

```text
exactly one qiumibao row within 30 minutes of the zhibo8 kickoff
```

Local DB comparison is stricter:

```text
normalized home team
normalized away team
kickoff within 4 hours
```

Multiple candidates produce `AMBIGUOUS_CANDIDATES`.

## Compare Status Values

```text
OK_MATCH:
  local score and live-source score agree.

LOCAL_DB_ONLY:
  reserved for reports where local score exists but live confirmation is absent.

LIVE_SOURCE_ONLY:
  live source has a row that does not map to local DB.

NEEDS_VERIFIED_FALLBACK:
  local DB is missing score, live source says finished with score.

CONFLICT_NEEDS_REVIEW:
  local score and live-source score conflict.

WAIT_SOURCE:
  live source is not finished or has no score yet.

MAPPING_MISSING:
  no reliable live row maps to local DB.

AMBIGUOUS_CANDIDATES:
  more than one live row could map to the local match.
```

## qiumibao Schema Notes

The qiumibao parser now preserves these fields when present:

```text
id -> external_id
code
period_cn
left.id -> left_id
right.id -> right_id
left.score / right.score
score_msg / score_msg_*
half-time score hints from score messages
```

Some qiumibao rows can expose only team ids and scores without team names. Those
rows are preserved for diagnostics, but they cannot be trusted for local mapping
without zhibo8 schedule context or a durable id mapping.

## Safety

This task deliberately does not:

```text
write production DB
write fake scores
write predictions or odds_snapshots
modify bets/users/balance
change BETTING_ENABLED
change P1/P3 weights
run migrations
replace results_sync main source
```

`NEEDS_VERIFIED_FALLBACK` is a review signal only. It is not permission to write
scores automatically.

## Recommended Next Step

Run the dry-run probe from the API container:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --recent
PYTHONPATH=. python -m api.worldcup_live_probe --compare-local --all-overdue
```

If output is stable for multiple matchdays and conflicts remain zero, this chain
can become a candidate comparison source. It should not become a score writer
without explicit approval.

## 061 Local Mapping

Task 061 adds local `matches.match_id` candidate scoring on top of this live
source chain:

```bash
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --recent
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --match-id 500-1359189
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --upcoming
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --recent-finished
PYTHONPATH=. python -m api.worldcup_live_probe --map-local --all-overdue
```

See `docs/WORLDCUP_LIVE_MAPPING_061.md`. The 061 mapping layer is still dry-run
and does not write results.

061-B hardens the diagnostic output:

```text
dump-zhibo8 prints zhibo8_raw_links and possible_qiumibao_ids
map-local prints qiumibao_link_status and next_step
zhibo8 matched but no qiumibao id becomes zhibo8_matched_but_qiumibao_unlinked
```
