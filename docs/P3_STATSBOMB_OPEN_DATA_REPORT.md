# P3 StatsBomb Open Data Report

## 1. Source Structure
StatsBomb Open Data is read from `data/competitions.json`, `data/matches/*/*.json`, `data/events/*.json`, and `data/lineups/*.json`. The adapter does not read `players/players.json`.

## 2. Counts
- statsbomb_root: `data\p3\statsbomb_open_data`
- competitions_count: 80
- matches_count: 64
- events_files_count: 64
- lineups_files_count: 64

## 3. Outputs
- matched_players: 4
- unmatched_players: 667
- sample_csv: `data\p3\real_performance_statsbomb_sample.csv`
- unmatched_csv: `data\p3\real_performance_unmatched_statsbomb.csv`

## 4. Coverage
- coverage_by_team: `{'Algeria': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Argentina': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Australia': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Austria': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Belgium': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Bosnia & Herzegovina': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Brazil': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Canada': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Cape Verde': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Colombia': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Croatia': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Curacao': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Czech Republic': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'DR Congo': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Ecuador': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Egypt': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'England': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'France': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Germany': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Ghana': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Haiti': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Iran': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Iraq': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Ivory Coast': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Japan': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Jordan': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Mexico': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Morocco': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Netherlands': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'New Zealand': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Norway': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Panama': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Paraguay': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Portugal': {'players': 26, 'complete': 1, 'ratio': 0.038461538461538464}, 'Qatar': {'players': 26, 'complete': 3, 'ratio': 0.11538461538461539}, 'Saudi Arabia': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Scotland': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Senegal': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'South Africa': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'South Korea': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Spain': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Sweden': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Switzerland': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Tunisia': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Turkey': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'USA': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Uruguay': {'players': 26, 'complete': 0, 'ratio': 0.0}, 'Uzbekistan': {'players': 26, 'complete': 0, 'ratio': 0.0}}`
- teams_below_70_percent: `['Algeria', 'Argentina', 'Australia', 'Austria', 'Belgium', 'Bosnia & Herzegovina', 'Brazil', 'Canada', 'Cape Verde', 'Colombia', 'Croatia', 'Curacao', 'Czech Republic', 'DR Congo', 'Ecuador', 'Egypt', 'England', 'France', 'Germany', 'Ghana', 'Haiti', 'Iran', 'Iraq', 'Ivory Coast', 'Japan', 'Jordan', 'Mexico', 'Morocco', 'Netherlands', 'New Zealand', 'Norway', 'Panama', 'Paraguay', 'Portugal', 'Qatar', 'Saudi Arabia', 'Scotland', 'Senegal', 'South Africa', 'South Korea', 'Spain', 'Sweden', 'Switzerland', 'Tunisia', 'Turkey', 'USA', 'Uruguay', 'Uzbekistan']`

## 5. Policies
- minutes_policy: conservative lineups positions intervals only; uncertain minutes omitted
- goals_policy: Shot events with shot.outcome.name=Goal; own goals excluded
- assists_policy: pass.goal_assist=true plus conservative assisted_shot_id/key_pass_id linkage
- xg_xa_policy: left blank for P3-Light; notes include unavailable_xg_xa
- source: https://github.com/statsbomb/open-data

## 6. Status
This is a partial sample and does not guarantee 70% coverage across the 48-team roster.
- result: PASS
- blocker: coverage_below_threshold
- gbm_ready: false
- candidate_w_gbm: 0
- production_w_gbm: 0
- would_write_db: false

## 7. Safety
P3-Light remains WAIT when coverage is below threshold. Betting should not be enabled from this report.
