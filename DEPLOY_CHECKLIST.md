# Production-style Deploy Checklist

## Before deploy
- [x] Frontend contains no credentials.
- [x] Live market calls are proxied through `/api/market`.
- [x] API has cache headers.
- [x] Invalid/null/non-positive market rows are filtered.
- [x] Duplicate market dates are de-duplicated.
- [x] Fallback mode is visible.
- [x] Last market session is shown as freshness.
- [x] Thesis benchmarks are separated from live proxy values.
- [x] Source inconsistencies are documented.
- [x] JavaScript and Python syntax checks passed.
- [x] Serverless API passed a mocked response test.

## After deploy
- [ ] Confirm `/api/market?range=5y` returns HTTP 200.
- [ ] Confirm dashboard badge is `LIVE`.
- [ ] Confirm latest market date equals latest available trading session.
- [ ] Test 1Y / 5Y / MAX buttons.
- [ ] Test mobile layout.
- [ ] Open production URL in an incognito browser.
- [ ] Add production URL to CV/LinkedIn.

## Optional upgrades
- [ ] Replace free feed with licensed/official market data.
- [ ] Persist daily snapshots in a database.
- [ ] Add scheduled model retraining and model registry.
- [ ] Add live sector feeds and sector-level EWM scores.
- [ ] Add downloadable CSV / audit report.
