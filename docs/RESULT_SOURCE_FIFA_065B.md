# 065-B FIFA Result Source and P1-C Prime Readiness

## Current conclusion

- FIFA official schedule page is reachable.
- The current public schedule page does not expose stable Match Centre URLs in the initial HTML.
- `data/fifa_match_targets.csv` is an auditable starter mapping file, but all six rows currently have blank `fifa_url` and `source_status=missing_url_mapping`.
- No FIFA result fallback write is allowed until each row has a verified, fetchable official URL.
- TheSportsDB free endpoint is reachable, but current-day World Cup rows can remain `scheduled` for hours after kickoff; it is only a T+ historical backfill candidate, not a near-real-time primary result source.

## FIFA target starter rows

The starter file covers:

- `500-1359227` Qatar vs Switzerland
- `500-1359195` Brazil vs Morocco
- `500-1359230` Haiti vs Scotland
- `500-1359233` Australia vs Turkey
- `500-1359200` Germany vs Curaçao
- `500-1359203` Netherlands vs Japan

Every row must remain `missing_url_mapping` until a real official FIFA Match Centre URL is discovered and fetch-tested.

## Probe commands

```bash
PYTHONPATH=. python -m api.external_result_source_probe --source fifa --discover-url --date 2026-06-13 --limit 5
PYTHONPATH=. python -m api.external_result_source_probe --source fifa --date 2026-06-13
PYTHONPATH=. python -m api.external_result_source_probe --source fifa --date 2026-06-14
PYTHONPATH=. python -m api.external_result_source_probe --source thesportsdb --date 2026-06-13
PYTHONPATH=. python -m api.external_result_source_probe --source thesportsdb --date 2026-06-14
```

## External result sync gate

Do not run confirm unless dry-run shows one safe candidate and all of these are true:

- local match is `closed` or `scheduled`
- local result fields are empty
- kickoff is at least 120 minutes old
- 500 current window does not contain the match
- external source status is final
- external score fields are non-empty
- team names match in the same order
- kickoff time window is within 120 minutes
- candidate is unique

Confirm command remains explicit:

```bash
PYTHONPATH=. python -m api.external_result_sync --confirm APPLY_EXTERNAL_RESULTS --source fifa --date 2026-06-14
```

## P1-C Prime readiness

Use the read-only report:

```bash
PYTHONPATH=. python -m api.p1c_readiness_report
```

Target:

- `target_finished_matches=30`
- `p1c_ready=false` until at least 30 finished matches have full-time results.

## P0 crawler root-cause checklist

After manually restarting `wc-p0-odds-crawler`, check:

- service is running
- latest `crawl_runs` has `ok=true`
- selected source is healthy
- `odds_snapshots` receives new rows
- `DATABASE_URL` exists in the service environment
- Start Command still points to the crawler entrypoint
- no recent deployment changed crawler configuration
- m500 request failures are visible in logs
- DB write errors are not swallowed

If stale odds repeats, add a crawler heartbeat/watchdog or stale alert before considering betting open.

## Safety

- Do not manually update scores.
- Do not lower external result sync gates.
- Do not write TheSportsDB `scheduled` rows.
- Do not use qiumibao mixed feed as World Cup score source.
- Keep `BETTING_ENABLED=false`.
- Do not change P1/P3 weights.
