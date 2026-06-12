# Official Result Fallback Runbook

`results_sync` is the primary path for match results. This fallback is a
controlled recovery path for cases where a verified official result exists but
the automatic source has not populated `matches`.

Do not use manual SQL updates for scores.

## 1. CSV File

Prepare:

```text
data/results/official_results_verified.csv
```

Required columns:

```text
match_id,home_team,away_team,result_home,result_away,ht_home,ht_away,status,source_name,source_url,retrieved_at,verified_by,notes
```

Rules:

- `match_id` must already exist in `matches`.
- `home_team` and `away_team` must match the database names after whitespace normalization.
- `result_home` and `result_away` are required non-negative integers.
- `ht_home` and `ht_away` may be blank when the official source does not provide a half-time score.
- `status` must be `finished` or `completed`.
- `source_name`, `source_url`, `retrieved_at`, and `verified_by` are required.
- Do not use `unknown`, `guessed`, or `guess` as source metadata.
- Existing scores are not overwritten by this flow.

The template is:

```text
data/results/official_results_verified_template.csv
```

## 2. Dry Run

Run inside the `wc-p2-api` container after deploying the code:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --dry-run
```

Review:

```text
would_update_count
error_count
each match before/after
source_url
verified_by
```

Continue only if the dry-run target list contains exactly the intended matches.

## 3. Confirm

Apply only after dry-run review:

```bash
PYTHONPATH=. python -m api.official_result_fallback --csv data/results/official_results_verified.csv --confirm APPLY_OFFICIAL_RESULTS
```

The command:

- uses a transaction
- updates only rows with `result_home IS NULL AND result_away IS NULL`
- allows only statuses `scheduled`, `closed`, `finished`, and `completed`
- writes `ops_log.job_name='official_result_fallback'`
- does not modify bets, users, balances, odds, predictions, or EV rows

## 4. Verification

Run:

```bash
PYTHONPATH=. python scripts/run_046_results_sync_check.py
PYTHONPATH=. python -m api.result_consistency_report
PYTHONPATH=. python -m api.ops_health_check
```

Expected after the two known finished matches are applied:

```text
target_results_synced=True
result_sync_status=PASS
evaluable_finished_matches >= 2
finished_null_count=0
non_finished_with_result_count=0
```

## 5. Safety

Do not:

- enable `BETTING_ENABLED=true`
- write fake scores
- update scores with ad hoc SQL
- overwrite existing results
- update bets/users/balances
- commit `data/results/official_results_verified.csv` unless it is intentionally reviewed and approved
- paste credentials, tokens, or database URLs into chat or docs
