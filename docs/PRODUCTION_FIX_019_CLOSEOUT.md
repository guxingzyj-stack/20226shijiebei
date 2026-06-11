# Production Fix 019 Closeout

This document records the non-secret closeout state for the 019 production repair flow. It does not contain database URLs, passwords, tokens, or backup contents.

## Current Status

```text
019-A backup: PASS
backup_file: worldcup_20260611_201447.sql
backup_size: 8,078,281 bytes
contains_odds_snapshots: yes

019-B migration: PASS
001_model_core.sql applied
002_betting_core.sql applied
003_ev_research_only.sql applied
004_ops_log.sql applied
005_p3_features.sql applied
006_ev_model_version.sql applied
007_ev_suggestion_eligible.sql applied

scheduler settlement_runner: PASS
scheduler results_sync: PASS
health probe: PASS
leaderboard probe: PASS, has roi, no internal id exposed
betting: disabled
```

## Cleanup Status

Original `cleanup_test_data run` failed because `bets.user_id` still referenced test users. The cleanup tool has been fixed to delete in foreign-key-safe order:

```text
1. bet child rows: none in current schema; bet legs are stored in bets.legs JSONB
2. bets owned by test users or containing test-* match legs
3. test-* matches
4. test_user_* / codex_blocker_* users
```

The fixed cleanup still requires the user to run the production commands. Codex has not run production cleanup.

Dry-run must be first:

```bash
python -m api.cleanup_test_data dry-run
```

If dry-run shows any non-test-prefix data, do not run cleanup.

Only after dry-run confirms test-only rows:

```bash
python -m api.cleanup_test_data run --confirm CLEAN_TEST_DATA
```

Cleanup protections:

```text
Never delete match_id LIKE '500-%'
Never delete non-test users
Run requires --confirm CLEAN_TEST_DATA
Run is transaction wrapped; failure rolls back
```

## Probe Summary

Saved JSON probes can be summarized locally without network or database access:

```powershell
$env:PYTHONPATH="."; python -m ops.probe_summary --mexico .\probe_mexico.json --germany .\probe_germany.json --leaderboard .\probe_leaderboard.json
```

The summary checks:

```text
leaderboard has roi
leaderboard does not expose internal id
Mexico/Germany latest_prediction model_version aligns with ev_signals model_version
EV > 0.15 is protected by research_only=true or suggestion_eligible=false
test_user_* / codex_blocker_* accounts are WARN, not PASS
```

## Final 019 Evidence Still Required

Before declaring final 019 closeout, record:

```text
cleanup dry-run output summary
cleanup run output summary, if dry-run is safe
probe_summary output
BETTING_ENABLED remains false
```

Do not open betting as part of 019 closeout.
