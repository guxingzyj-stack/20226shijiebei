# P1-C Probe Temporary Zeabur Service

This temporary service runs only the 10-second 500.com historical page probe for P1-C. It is not a production worker and must not be left running.

## Zeabur Service Settings

```text
service_name: wc-p1c-probe-temp
repo: https://github.com/guxingzyj-stack/20226shijiebei.git
branch: main
root directory: /ops/p1c_probe_service
provider: Docker / Dockerfile
dockerfile: Dockerfile
```

Use only the isolated probe service directory:

```text
/ops/p1c_probe_service
```

Do not use the repository root `/`. The repository root must not contain a `Dockerfile`, because Zeabur may otherwise auto-detect formal monorepo services such as `wc-p2-api` as the temporary probe container.

Do not deploy this as `static`. If Zeabur still shows `static`, the service is not using `/ops/p1c_probe_service` as its root directory.

The older explicit `Dockerfile.p1c-probe` is retained only as a reference. The recommended Zeabur setup is the isolated directory `/ops/p1c_probe_service` with its local `Dockerfile`.

Do not use the probe Dockerfile for the formal API, Web, model-worker, or crawler services. Those services keep their existing service-specific build settings and must not be redeployed for this probe.

## Default Command

The isolated Dockerfile default command is:

```bash
python p1c_probe_standalone.py --start-date 2022-11-20 --end-date 2022-12-18 --timeout-seconds 10
```

The output should start with:

```text
P1-C 500.com Historical Probe Report
```

## What To Copy Back

Copy the report fields only. Do not copy large raw HTML.

```text
Candidate URLs:
- url
- status_code
- decoded_as
- contains_worldcup_keywords
- contains_odds_like_fields
- contains_score_like_fields
- likely_usable
- notes

Summary:
- candidates_tested
- usable_candidates
- best_candidate_url
- recommended_next_step
- result
```

## Safety Boundaries

- Do not restart `wc-p0-odds-crawler`.
- Do not modify `crawler/`.
- Do not touch `wc-p2-api`, `wc-p2-web`, or `wc-p1-model-worker`.
- Do not put a `Dockerfile` back in the repository root for this probe.
- Do not run migrations.
- Do not set `BETTING_ENABLED=true`.
- Do not scrape 64 matches.
- Do not generate a formal historical odds CSV.
- Stop or delete `wc-p1c-probe-temp` after the probe finishes and logs are saved.
