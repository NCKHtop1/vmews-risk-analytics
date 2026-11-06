# FINQUERY RELIABILITY REVIEW — 2026-11-06

## Incident evidence and status
At 09:56 ICT 06-Nov-2026, the user saw FPT 52,900 VND, -1.86%, market timestamp 14:45 05-Nov-2026. The canonical financial-market-data branch contained the same last-source timestamp while quotes.json had status=ok. prices-status.json showed 111/111 last-session prices, historical FPT daily candles were populated through 05-Nov, 5m data existed through 05-Nov, and news refreshed on 06-Nov. This proves stale pricing delivery, **not** absence of FPT history or a proven chart-engine failure. Vercel production logs/deploy details were not accessible (403), so no claim of a repaired live site is justified.

## Key design gaps
1. \`guard_public_quotes.py\` originally compared source vs GitHub Pages lag only. If both remain equally outdated, lag==0 can pass. Absolute certified-session freshness and collector heartbeat must be evaluated first.
2. \`live_session_publisher.sh\` only commits the price batch after derived Technical, Strategy, Risk and calibration work/validation succeed. A downstream failure may block valid source price publication.
3. Green GitHub workflow and \`status=ok\` snapshots do not prove the active market session is available to the user.
4. Chart candlestick errors and mobile UI visibility require authenticated real-browser QA. The screenshot does not establish whether the chart canvas below the viewport is blank.
5. Forecast/backtest quality must remain separately fail-closed; never promote withheld models or unverified news-impact alerts to active.

## P0 safety repair in this PR
- \`quote_freshness_policy.py\` evaluates the source's own local exchange session, absolute age, publisher heartbeat and per-symbol 90% freshness against the existing certified 2026 VN trading calendar. It differentiates preopen, live morning, lunch, active afternoon, postclose, weekend and holidays. Unknown calendar years fail closed.
- \`guard_public_quotes.py\` runs it before public-mirror comparison; exit 24 explicitly means valid-but-stale SOURCE, not a Pages-only lag. Existing 95% valid record and access-control probes remain unchanged.
- Independent price-availability workflow runs both old and new tests, dispatches the price workflow only when no queued/running publisher is found, and keeps the incident FAILED until a later verification succeeds.
- No quote values, market-data writers, derivatives, risk model, UI, RBAC, confidential keys or live forecasts are modified in this PR.

## Cross-functional rollout backlog (separate reviewed PRs)

| ID | Priority | Owner | Scope | Exit evidence |
|---|---|---|---|---|
| FQ-P0-01 | P0 | Data + SRE | Verify source API vs raw \`financial-market-data\`, 06-Nov quote absence, collector logs and 429/403/invalid response | Exact failed step, run ID, upstream response summary, source timestamp, owner and rollback |
| FQ-P0-02 | P0 | System + Quant | Decouple raw quote/history publisher from Strategy/Risk/calibration publication without mixing revisions | Independent atomic raw quote commit, immutable input SHA for derived bundle, fail-safe stale labelling, zero synthetic values |
| FQ-P0-03 | P0 | SRE | Cross-check raw source/Pages/authenticated Vercel; heartbeat, running/queued jobs, bounded retry, incident deduplication | Source stale >20m critical, guard FAIL, one recovery dispatch maximum, later truly fresh snapshot before incident closes |
| FQ-P0-04 | P0 | Frontend + QA | Make current/prior-session status unambiguous, maintain historical charts, disable live signals when stale | Android Chrome + iOS Safari + desktop screenshots and console/network logs |
| FQ-P1-05 | P1 | Quant | Audit scanners, Strategy, VN100 Forecast, Risk, Portfolio; immutable as-of and point-in-time source alignment | OOS/withheld gates unchanged, verified data lineage, none of stale Discovery alerts promoted |
| FQ-P1-06 | P1 | Data | Audit financial statements, VN100 universe, 1m/5m/1d OHLC, adjustment, corporate actions, macro and ESG | Real-source reconciliations, 111-symbol coverage where entitled, documented missing data |
| FQ-P1-07 | P1 | News/Quant | Event time, deduplication, issuer/sector exposure, out-of-sample impact validation | Shadow-only unless signed empirical tests pass; kill switch LOCKED_OFF otherwise |
| FQ-P1-08 | P1 | Security | Verify protected Vercel/Neon routes and auth without exposing tokens, data or internal telemetry | Anonymous 401 + actual authenticated read, RBAC negative tests, redacted traces |
| FQ-P1-09 | P1 | Release/SRE | Verify Pages/Vercel SHA, staged production, observability and rollback | Exact deployed SHA, smoke PASS, next genuine source refresh, revert plan |

## Release gates
- Verify Vercel project/team/domain and production commit; do not assume \`READY\` means live data current.
- CI: legacy + new source freshness unit tests, complete repository integration tests, chart/market browser tests, mobile 320/390/768/1280, auth/RBAC tests, nonregression checks in Financials/Forecast/Portfolio/News/Risk.
- Data: source session aligns with certified day; during active window source age <=20 minutes, checkedAt <=15 minutes and >=90% fresh non-retained member quotes. Existing >=95% valid-quote record guard and <=25min raw-to-Pages delivery lag remain.
- Real live smoke: current-session FPT and at least three other securities, daily and intraday history, four modules, one actual refresh cycle, no browser errors.
- Require review approval by Senior Data, Senior Quant, Senior System/SRE, Senior Frontend and Security. No force push of market branch.
- Promote a verified, staged production build only after gates. Observe next live session; if errors recur, revert code to last verified SHA and keep last-known-good data explicitly labelled as stale. Do not fabricate recovery.

## Current decision
**P0 safety repair implemented in review branch, not production.** External test/CI status, live market recovery and Vercel runtime access must be verified. Entire-system hardening remains an open, separately tracked work program.
