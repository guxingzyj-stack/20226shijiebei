# P3 Data Source Plan

P3-A only prepares infrastructure. Do not run uncontrolled external scraping from production services.

## FBref

- Manual trigger only.
- Request interval must be at least 3.1 seconds.
- Cache raw HTML or CSV before parsing.
- Do not fetch FBref during API startup or scheduler startup.
- Respect robots.txt and source terms.

## Transfermarkt

- Manual trigger only.
- Request interval must be at least 2 seconds.
- Prefer manual CSV or a licensed API alternative.
- Do not bypass captcha, login walls, or rate limits.
- Do not fetch Transfermarkt during API startup or scheduler startup.

## P3-B Scope

Real data ingestion belongs to P3-B after source approval, cache design, and rate limiting are reviewed.
