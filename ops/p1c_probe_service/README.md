# P1-C Probe Temporary Service

This isolated directory is the only root directory that should be used for the Zeabur temporary probe service.

## Zeabur Settings

```text
service_name: wc-p1c-probe-temp
root directory: /ops/p1c_probe_service
provider: Docker
dockerfile: Dockerfile
```

Do not use the repository root `/` for this temporary service. The repository root intentionally has no `Dockerfile`, so formal monorepo services such as `wc-p2-api`, `wc-p2-web`, and `wc-p1-model-worker` are not accidentally detected as the probe container.

## Command

The Dockerfile runs:

```bash
python p1c_probe_standalone.py --start-date 2022-11-20 --end-date 2022-12-18 --timeout-seconds 10
```

The script is self-contained and only requires `requests` plus the Python standard library.

## Safety

- Do not restart `wc-p0-odds-crawler`.
- Do not modify `crawler/`.
- Do not deploy this onto `wc-p2-api`, `wc-p2-web`, or `wc-p1-model-worker`.
- Do not run migrations.
- Do not enable betting.
- Do not scrape 64 matches.
- Do not generate a formal CSV.
