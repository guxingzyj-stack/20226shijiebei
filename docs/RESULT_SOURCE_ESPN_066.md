# 066 ESPN Scoreboard Structured Result Source

## Scope

ESPN scoreboard is a structured result fallback candidate for World Cup full-time scores.

It must not replace the normal 500 source. It is only allowed for closed/scheduled overdue matches when 500 current-window results do not contain the match and ESPN has a final score.

## Probe commands

```bash
PYTHONPATH=. python -m api.external_result_source_probe --source espn --date 2026-06-13
PYTHONPATH=. python -m api.external_result_source_probe --source espn --date 2026-06-14
```

The probe tries ESPN scoreboard endpoints in this order:

- `soccer/fifa.world`
- `soccer/fifa.world_cup`
- `soccer/fifa.worldcup`

Current local probe result:

- `2026-06-13`: ESPN reachable, target matches seen, final scores present for Qatar vs Switzerland, Brazil vs Morocco, Haiti vs Scotland.
- `2026-06-14`: ESPN reachable, target matches seen, but rows are still scheduled at probe time and must not be written.

## ESPN date bucket caveat

ESPN scoreboard `dates=YYYYMMDD` is organized by the event's US Eastern Time match day, while local `matches.kickoff_at` is stored in UTC.

This means a North American evening match can appear in ESPN's previous date bucket:

- local kickoff UTC: `2026-06-14T01:00:00+00:00`
- Eastern Time date: `2026-06-13`
- ESPN bucket: `dates=20260613`

For ESPN only, `external_result_sync` now builds candidate buckets from each local kickoff:

- kickoff converted to `America/New_York`
- kickoff UTC date
- kickoff UTC date minus one day
- kickoff UTC date plus one day

The date bucket is only used to discover candidate events. Final writes still require same-order team match, kickoff time window, final status, score fields, and a unique candidate.

## Parser fields

The parser reads:

- `event.id`
- `event.date`
- `event.status.type.name`
- `event.status.type.state`
- `event.status.type.completed`
- `event.competitions[0].competitors[].homeAway`
- `competitor.team.displayName`
- `competitor.team.shortDisplayName`
- `competitor.team.abbreviation`
- `competitor.score`

Final status is true only when ESPN says `completed=true` or the status type is explicitly final/post/full-time.

## Sync commands

Dry-run:

```bash
PYTHONPATH=. python -m api.external_result_sync --dry-run --source espn --date 2026-06-14
```

Even when the CLI date is `2026-06-14`, ESPN lookup can include `20260613` when a local candidate kicks off at `2026-06-14T01:00:00Z`.

Confirm remains explicit:

```bash
PYTHONPATH=. python -m api.external_result_sync --confirm APPLY_EXTERNAL_RESULTS --source espn --date 2026-06-14
```

Do not run confirm unless dry-run shows exactly one safe update candidate.

## Write gate

All conditions must pass:

- local match status is `closed` or `scheduled`
- local `result_home/result_away` are both null
- kickoff is at least 120 minutes old
- 500 current-window source does not contain the match
- ESPN status is final
- ESPN score fields are non-empty
- team names match in the same order
- kickoff time delta is within 120 minutes
- candidate is unique

The first version does not write `ht_home` or `ht_away`.

## official_result_fallback URL safety

Verified CSV fallback now rejects:

- non-HTTP/HTTPS URLs
- `<PASTE...`
- `PLACEHOLDER`
- `TODO`
- `这里换成`
- `example.com`

This prevents placeholder source URLs from being confirmed.

## Safety

- Do not manually update scores.
- Do not write scheduled or in-progress ESPN scores.
- Do not lower external result sync gates.
- Keep `BETTING_ENABLED=false`.
- Do not change P1/P3 weights.
