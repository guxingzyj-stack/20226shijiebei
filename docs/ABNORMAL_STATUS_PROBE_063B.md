# 063-B Abnormal Status Probe

`abnormal_status_probe` is a non-production safety probe for postponed,
abandoned, cancelled, rescheduled, and interrupted match states.

## Safety

- Does not run confirm against production by default.
- Does not write real `500-` matches.
- Does not write real scores.
- Does not change betting state.
- Does not modify predictions, odds, P1, or P3.
- Uses only `test-` match ids.

## Commands

Dry-run:

```bash
PYTHONPATH=. python -m api.abnormal_status_probe --dry-run
```

Confirm in non-production or with explicit test override:

```bash
PYTHONPATH=. python -m api.abnormal_status_probe --confirm RUN_ABNORMAL_STATUS_PROBE
```

Production confirm is refused unless:

```text
ALLOW_TEST_PROBES=true
```

## Test Matches

The probe uses only:

```text
test-postponed-001
test-abandoned-001
test-cancelled-001
test-rescheduled-001
test-interrupted-001
```

They must never be marked as `finished` by the probe, and their
`result_home/result_away` values must remain `NULL`.

## Assertions

The probe checks:

- abnormal rows are not marked finished
- result fields remain null
- settlement runner skips the probe bet in dry-run mode
- result consistency does not report non-finished-with-result pollution
- betting gate is not improved by abnormal states
- cleanup removes only probe-created rows

## Cleanup Scope

Cleanup is scoped to the fixed probe match ids and the probe user:

```text
__abnormal_status_probe__
```

It must not delete arbitrary non-test users or real `500-` matches.

## Operations Rule

Exceptional matches must not auto-settle. Without a clear full-time score,
`result_home/result_away` must remain empty. Postponed, abandoned, cancelled,
rescheduled, or interrupted matches must not be treated as `finished`.
