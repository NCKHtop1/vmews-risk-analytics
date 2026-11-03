# FinQuery — News-to-Sector/Stock Impact Research

**Status: RESEARCH ONLY — NO LIVE NOTIFICATIONS.** Do not change Price, Forecast, Strategy, or Risk logic. This is an offline Quant / DA / Systems evaluation with a release gate.

## Research objective

A headline mentioning FPT is NOT evidence of a price impact on FPT. A market response after a story is also NOT proof that a notification after receiving that story would have profitable or reliable predictive value. Separate three questions:

1. SEMANTIC EXPOSURE: What financial channel is affected (cost of capital, FX revenues, input costs, capacity, regulatory decisions)?
2. OBSERVED RESPONSE: Does the affected sector/ticker historically show abnormal return or abnormal volume after comparable events?
3. ACTIONABLE PREDICTION: With independently verified information time, does a stable out-of-sample response remain available AFTER the alert, fees and slippage?

## Proposed labels

- Relevance: DIRECT_ISSUER / INDIRECT_EXPOSURE / SECTOR / MACRO / UNRELATED / AMBIGUOUS.
- Event family: MONETARY_POLICY, FX, OIL, METALS, TARIFF_TRADE, REGULATORY, EARNINGS, CORPORATE_ACTION, CREDIT_DEFAULT, M_AND_A, PROJECT_CONTRACT, OTHER.
- Mechanism: REVENUE / INPUT_COST / FUNDING_COST / DEBT_FX / MARGIN / INVENTORY / VALUATION / DEMAND / SUPPLY / REGULATION; allow opposing mechanisms.
- Hypothesis sign: POS / NEG / MIXED / UNKNOWN. Never force UNKNOWN into a directional claim.
- Evidence tier: E0_UNTESTED; E1_RETROSPECTIVE_ASSOCIATION; E2_CHRONOLOGICAL_HOLDOUT; E3_FORWARD_PIT_VALIDATED.
- Notification policy: only E3 is a candidate for a small in-app notification. E0–E2 remain searchable research, without push.

Examples requiring exposure verification rather than naive sentiment: stronger USD/VND can favor net exporters and harm USD debtors; higher oil prices may benefit upstream energy service providers but increase airline fuel costs; lower policy rates can change bank funding and lending yields in opposing ways. Do not assign a universal positive/negative sign to an entire sector.

## Point-in-time data contract

Store immutable story_id, event_cluster_id, original URL, publisher, publishedAt, FIRST_SEEN_AT (actual FinQuery collector receipt), decisionAt, corrections, true issuer_id, entity role (parent/subsidiary/counterparty), ticker mapping effective date, sector mapping effective date, model version, factor exposure, data_asof, adjusted corporate actions, and live price snapshot lineage.

Historical RSS backfill provides a publication time but not necessarily the moment FinQuery could have known the story. The current publishedAt-based event studies therefore **cannot certify an executable trading signal**. Capture forward ingestion firstSeenAt for every story going forward; do not fill it retrospectively from publication time.

## Quant methodology

1. One canonical event per distinct story, source and impacted mechanism; collapse syndicated headlines and cool down overlapping ticker-events.
2. Event t0 is the first **tradable** time after verified decisionAt. With daily bars, use next-session opening price for intraday/afterhours articles; use verified intraday bars only when exact timestamp and feed latency allow intraday tests.
3. Measure reaction and potential predictability separately: T+1, T+3, T+5 abnormal returns against market and sector benchmarks; test pre-event drift, volume surprise, volatility, and false positive effects of news following prices.
4. Adjust for corporate actions, suspended/illiquid stocks, news publication gaps, varying sectors through time and overlapping market-wide macro shocks.
5. Split chronologically with embargo between training, validation and untouched holdout. Then forward shadow validation with genuine collector firstSeenAt. Never tune on the final holdout.
6. Cluster-bootstrap by unique event and event date, correct multiple hypotheses across industries/stocks/horizons (FDR), placebo on comparable no-news days, and stress by regime.
7. Economic criteria: effect direction, median and quantile abnormal return, hit-rate vs base rate, cost-adjusted impact, universe coverage, calibration, alert precision and false notification burden.

**Proposed initial sample gate — NOT a claim of success:** at least 40 independent training events and 20 holdout events per narrow cohort; >=15 independent holdout event days and >=4 distinct holdout months, FDR q<=0.10, stable effect with >60% holdout direction agreement and sufficient post-cost economic magnitude. These are hypotheses to be calibrated by Quant, not final certified parameters.

**E3 is additionally gated** on two consecutive valid forward, PIT shadow windows with adequate independent event counts, typically no less than 8–12 weeks; if sample size is insufficient, continue shadow rather than lower standards.

## UX rules to minimize noise

- Silent default: E0, E1, E2, ambiguous issuer, secondary source, rumor, corrected or stale stories => no push.
- Event-level grouping, not one notification per article; watchlist/portfolio personalization.
- A small inline indicator can say “historical sector response observed” only after validated evidence is shown, and must be distinct from “live response already occurred.”
- An E3 event can only suggest a **historically supported hypothesis**, never state that price WILL rise/fall or that a current impact is already proven.
- Require current quote freshness, provenance and possibly live relative volume/abnormal return confirmation before an in-session reaction notice.
- Default noise budget: <=3 meaningful in-app notifications per user/day, one per event-sector/ticker per six hours. User controls are configurable.
- Each alert carries mechanism, affected universe, source, firstSeenAt, evidence sample sizes, OOS windows, horizon, uncertainty and contradictory impacts. Disable automatically on feed failure / model drift.

## Pilot implementation and explicit limitations

The isolated offline program financial-report/scripts/research_news_impact.py reads retrospective research-news-v10, market history and today's sector snapshot. It validates timestamps, quarantines ticker/issuer ambiguity, excludes incomplete current-day bars, uses conservative next-session-open assumptions, removes duplicate/overlapping events, computes cross-sectional market-median-adjusted returns, and performs an embargoed chronological exploratory holdout with multiple-testing correction.

Its exported report ALWAYS sets liveSectorAlerts=false and liveTickerAlerts=false; it never writes market snapshots or UI notifications. The exploratory test does not yet have point-in-time sector membership, independent firstSeenAt or event-day clustered bootstrap. Those are blockers to E3 and must not be hidden by attractive pilot results.

## Measured research results, 03 Nov 2026 (NO production approval)

Independent CI, GitHub Actions run 41601370425:

- Recent retrospective archive: 13,870 articles across 404 symbols; 113 symbol histories available in the market branch for the pilot; 1,671 deduplicated representative stock-events with outcome windows. Historical collector firstSeenAt fields: **zero**.
- Older event intelligence V12: 12,785 individual records spanning 2018-08-20 to 2026-08-18, 366 symbols and 98.5% benchmark coverage for T+5. Historical sector status remains ABSTAIN.
- V12 directional/issuer-eligible records: 2,042; after 7-calendar-day overlapping-event cooldown: 1,712. Held-out tests for EVENT/TICKER × event category × sentiment × (1/3/5 sessions): 339 total; only 3 met pre-specified minimum independent-day/month/source counts; **zero** met exploratory evidence gates and **zero** can issue live notifications.
- Positive EARNINGS examples: T+1 train implied UP, but validation directional effect -18.7 bps and holdout -12.5 bps, hit rate 44%. T+5 train implied DOWN but OOS hit rate 57.3%, week-bootstrap 95% interval [-10.9, 128.3] bps and FDR-adjusted exploratory q=0.594. Neither is actionable directional evidence.

The outcome does not prove absence of news impact. It proves this archive, issuer/entity coverage and labeling scheme do not presently support low-noise, dependable alerts. More exhaustive news labels, news-to-factor exposure and timestamped forward ingestion are required before restarting a live-alert approval review.

## Required independent review

- Senior Data Analyst: entity QA (including parent vs subsidiary), source and firstSeenAt audit, sector mapping through time, labelled precision/recall sample.
- Senior Quant: pre-registered hypotheses, abnormal returns vs benchmark, OOS/fold stability, event-day bootstrap, FDR, matched placebo, execution-aware net returns.
- Senior Systems: idempotent ingestion, deduplication, immutable source lineage, recovery, provenance dashboard, shadow staging, alert budget, canary, kill switch.
- Release owner: alert launch only after PIT forward validation report and user-level false alert audit. No existing business logic changes.

Method references: MacKinlay (1997) Event Studies in Economics and Finance; Heston and Sinha (2016) News versus Sentiment (Federal Reserve); Brière et al. (2023) Stock Market Reaction to News; Vietnam sectoral EVFTA event-study (2024). They support research methods, not a FinQuery alpha claim.


## Follow-up audit: separate frozen V12 T+2, 03 Nov 2026

This is a **different, narrower experiment** from the earlier 339-hypothesis
T+1/T+3/T+5 pilot above. Do NOT combine p-values, event counts or threshold
pass rates across the two research protocols.

- Source: `data/event-intelligence-v12.json`, 12,785 retrospective records.
- Clean issuer/date/event/sentiment duplicates and overlap purge through each
  prior ticker episode's T+5 maturity: 1,625 independent episodes. Strict
  60%/20%/20% date boundaries and actual maturity embargo leave 601 training,
  306 validation and 709 holdout episodes (the remaining observations are
  intentionally purged at fold boundaries).
- Only **two pooled** event/sentiment hypotheses have sufficient train,
  validation and holdout samples. **Zero issuer-specific ticker hypotheses**
  have enough independent evidence for a defensible price-direction alert.
- REGULATORY + NEG: the holdout has 54 episodes over 48 event days, signed
  VNINDEX-relative T+2 day-cluster mean +197 bps *in the negative direction*,
  74.1% hit rate, day-bootstrap 95% interval [+104,+306] bps and exploratory
  BH q=0.001 within this *small validation-selected family*. **BUT** the
  validation fold already had a prior two-day same-direction excess move of
  +245 bps BEFORE the news. That pretrend is material confounding; classify
  as `OOS_ASSOCIATION_WITH_PRETREND`, **not an approved causal or actionable
  signal**.
- EARNINGS + POS is also directionally unstable/weak: the training direction
  is counterintuitively negative, holdout 265 episodes / 108 days with 52.1%
  hit rate and q=0.065, **below** the predeclared 55% hit floor.
- A BH q-value is not a cure for retrospective search-selection, first-seen
  uncertainty, multiple prior study iterations or news-following-price
  confounding. The frozen 2018–2026 data were already examined in prior
  experiments, so the newest “holdout” should be treated as a **reused
  retrospective evaluation**, not a genuinely untouched future test.

**Release decision: RESEARCH_ONLY.** `notificationsEnabled=false`,
`tickerAlerts=false`, `sectorAlerts=false`. The potential novelty lies in
the quality of the independent timestamped forward evidence, first-order
business exposures and actual post-news market reaction, NOT a high-volume
sentiment ticker banner. No code from this study changes existing FinQuery
price, news, Strategy, Portfolio, Forecast or Risk business logic.

Independent read-only research runner:
`scripts/news_impact_shadow_research.py` plus
`.github/workflows/news-impact-shadow-research.yml`; its artifact contains
full methodological thresholds, failure counts and each evaluated cohort.
