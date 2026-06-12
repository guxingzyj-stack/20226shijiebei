# P4 Recap Acceptance Report

Status: API complete and frontend MVP complete, production web deployment pending.

## 1. MVP Features

Implemented:

- single match recap API
- recent recaps API
- aggregate recap summary API
- market HAD open/close odds review
- normalized market implied probabilities
- pre-kickoff model prediction review
- model hit/miss classification
- EV signal hit/miss review
- settlement aggregate counts without internal ids
- CLI runner
- recap home page `/recaps`
- single-match recap page `/recaps/:matchId`
- match detail entry to post-match recap when a finished result is available

## 2. Endpoints

```text
GET /api/recaps/matches/{match_id}
GET /api/recaps/recent?limit=10
GET /api/recaps/summary
```

## 3. CLI

```bash
PYTHONPATH=. python -m api.recap_runner --match-id 500-1359172
PYTHONPATH=. python -m api.recap_runner --summary
```

## 4. Data Policy

P4 reads existing data and computes reports at request time. No migration and no
cache table are used in this MVP.

## 5. Safety

```text
BETTING_ENABLED remains false
no score writes
no bet/user/balance writes
no P1/P3 weight changes
no migration
no internal id exposure in settlement summaries
research_only EV is labelled as research_signal
```

## 6. Production Verification After Deploy

Run:

```bash
curl -sS https://fifa2026.zeabur.app/api/recaps/matches/500-1359172
curl -sS https://fifa2026.zeabur.app/api/recaps/recent
curl -sS https://fifa2026.zeabur.app/api/recaps/summary
```

Optional container CLI:

```bash
PYTHONPATH=. python -m api.recap_runner --match-id 500-1359172
PYTHONPATH=. python -m api.recap_runner --summary
```

Expected:

```text
available=true for finished matches with results
market/model/ev/settlement/summary sections present
no user_id or bet_id in settlement output
```

## 7. Frontend Verification

Routes:

```text
GET /recaps
GET /recaps/{match_id}
```

Expected:

```text
/recaps lists recent finished match recaps from the recap API
/recaps/{match_id} shows result, market, model, EV, settlement, data quality, and summary sections
unavailable recaps show a friendly empty state
match detail only links to recap when status is finished/completed and scores are present
research_only EV is labelled as research signal, not betting advice
no user_id, bet_id, or internal id is rendered
```
