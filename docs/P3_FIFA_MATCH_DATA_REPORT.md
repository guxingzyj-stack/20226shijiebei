# P3 FIFA MatchData Report

## Scope
- data_scope: fifa_world_cup_match_performance
- not_club_recent_form: true
- FIFA MatchData is official World Cup match performance data, not pre-match club recent form.

## CSV Summary
- result: WAIT
- blocker: missing_fifa_match_url_mapping
- fifa_match_targets: `data\p3\fifa_match_targets.csv`
- accessible_matches: 0
- matches_with_player_data: 0
- sample_csv: `data\p3\real_performance_fifa_match_sample.csv`
- sample_rows: 0
- unmatched_csv: `data\p3\real_performance_unmatched_fifa.csv`
- unmatched_rows: 0

## Coverage
- coverage_by_team: `{}`
- teams_below_70_percent: `[]`
- gbm_ready: false
- candidate_w_gbm: 0
- production_w_gbm: 0
- would_write_db: false

## Policies
- minutes_policy: FIFA player minutes or conservative lineups/substitutions
- goals_policy: FIFA official goal events only
- assists_policy: FIFA official assists only
- xg_xa_policy: blank with unavailable_xg_xa notes
- source_policy: FIFA match URL per row
- confidence_policy: high exact team+name; medium unique name; low unmatched only

## Safety
If FIFA player-level data or URL mapping is missing, the adapter reports WAIT. Do not fabricate match performance data, do not write production DB, and do not enable betting.
