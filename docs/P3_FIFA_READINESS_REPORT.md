# P3 FIFA Readiness Report

Current track:

```text
p3_mode=fifa_matchdata
```

Current expected status before FIFA MatchData CSV exists:

```text
p3_status=WAIT
candidate_w_p3=0
production_w_p3=0
production_w_gbm=0
blocker=missing_fifa_matchdata
```

## Data Inputs

The readiness gate reads:

```text
data/p3/real_performance_fifa_match_sample.csv
data/p3/real_performance_unmatched_fifa.csv
docs/P3_FIFA_MATCH_DATA_REPORT.md
```

If the sample CSV is missing, the report remains `WAIT`.

## Health Integration

`/api/health` includes a compact, safe summary:

```json
{
  "p3_mode": "fifa_matchdata",
  "p3_status": "WAIT",
  "p3_candidate_w": 0,
  "p3_production_w": 0,
  "p3_blockers": ["missing_fifa_matchdata"]
}
```

`api.ops_health_check` includes:

```json
{
  "p3_fifa_status": "WAIT",
  "p3_fifa_matches_with_data": 0,
  "p3_fifa_teams_with_data": 0,
  "p3_fifa_candidate_w": 0,
  "p3_fifa_production_w": 0
}
```

P3-FIFA `WAIT` or `SHADOW` is informational and must not cause production
health to fail.

## Relationship To P4

P4 may read P3-FIFA MatchData once available for:

- starting lineup stability
- player minutes
- goals and assists contribution
- in-tournament team form changes

P3-FIFA is World Cup in-match/post-match data. It is not pre-tournament club
recent form and does not replace the missing P3-A club recent form dataset.
