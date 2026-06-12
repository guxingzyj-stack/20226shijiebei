# P4 Recap Acceptance Report

Status: API complete and frontend product layer complete, production web deployment pending.

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
- model performance page `/recaps/model`
- EV signal performance page `/recaps/ev`
- daily shareable recap report page `/recaps/daily`
- match detail entry to post-match recap when a finished result is available

## 2. Endpoints

```text
GET /api/recaps/matches/{match_id}
GET /api/recaps/recent?limit=20
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
GET /recaps/model
GET /recaps/ev
GET /recaps/daily
```

Expected:

```text
/recaps lists recent finished match recaps from the recap API
/recaps/{match_id} shows result, market, model, EV, settlement, data quality, and summary sections
/recaps/model shows model hit rate, market agreement, and recent match performance
/recaps/ev shows EV totals, research/suggestion flags, and hit/miss review
/recaps/daily groups recaps by date and generates copyable daily report text
unavailable recaps show a friendly empty state
match detail only links to recap when status is finished/completed and scores are present
research_only EV is labelled as research signal, not betting advice
no user_id, bet_id, or internal id is rendered
```

## 7.1 P4-UI-OPT Readability

EV display rules:

```text
/recaps/ev defaults to Top 20 EV rows
/recaps/{match_id} EV detail defaults to Top 20 EV rows
EV rows are sorted by EV descending
duplicate display rows are aggregated by match + play_type + selection + odds
aggregated duplicates show occurrence_count
users can expand all rows and collapse back to Top 20
missed EV review text uses "复盘未命中"
research_only EV remains labelled as "研究信号"
```

Layout tuning:

```text
/recaps/model uses tighter local spacing and card padding
/recaps/daily uses tighter local spacing and a capped daily preview area
global layout and other pages are unchanged
```

## 7.2 Metric Help Layer

Added a beginner-friendly metric explanation layer:

```text
/help explains model, odds, EV, settlement, system health, and safety terms
recap pages show compact help tips beside model hit rate, EV, implied probability, and settlement status
match schedule and match detail pages explain model prediction, odds, and EV signals
leaderboard explains ROI as virtual-fund performance only
EV text continues to state research signal, not betting advice
```

## 7.3 EV Value Explanation

EV copy was simplified for regular users:

```text
/help includes "EV 值怎么看？" with EV > 0 / = 0 / < 0 examples
/recaps/ev shows an EV band guide above the signal list
/recaps/{match_id} EV sections explain that EV is not win probability and not betting advice
scoreline EV is labelled as high-volatility review-only signal
```

## 7.4 Match List And Detail Analytics

Added schedule and match detail readability improvements:

```text
/api/matches supports status=all/upcoming/finished
web schedule defaults to all matches and adds 全部 / 未开赛 / 已完赛 filters
today's matches are sorted first, then by kickoff time
finished match cards show centered score, model pre-match direction, and hit/miss status
finished cards link to /recaps/{match_id} when a complete result exists
finished-like matches without result show 赛果回填中 and link to match detail
match detail right rail now includes odds trend, model vs market comparison, score-matrix metrics, team form, prediction drift, EV explanation, and betting gate status
team form and prediction history endpoints are read-only and return insufficient_data when local data is unavailable
ScoreMatrix highlights final score cells and labels result backfill / out-of-range states
```

## 8. Product Boundary

P4 is complete enough for production display, but it remains a read-only review
layer. It does not depend on P3 completion and it does not authorize opening
betting.

```text
no prediction writes
no score writes
no bet/user/balance writes
no P1/P3 weight changes
BETTING_ENABLED remains false
```
