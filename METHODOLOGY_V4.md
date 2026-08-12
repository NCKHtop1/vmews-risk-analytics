# VMEWS Research Methodology v4

## Purpose

VMEWS is a point-in-time early-warning research system for Vietnamese listed equities. It is designed for **risk-review triage**, not target prices, buy/sell recommendations or guaranteed crash prediction.

The workflow is:

**Market-wide T-day scan → RED/YELLOW shortlist → single-name evidence → calibrated model validation → human risk review.**

## Canonical alert policy

The machine-readable policy is `data/alert-policy.json` (`VMEWS-ALERT-POLICY-4.0.0`). All front-end risk-index bands and market-wide thresholds must read from this policy.

- WATCH: risk index >= 50.
- YELLOW: risk index >= 65 plus weak trend and at least two independent stress signals.
- RED: risk index >= 78 plus weak trend and at least three independent stress signals.
- Market-wide alert eligibility also requires current completed EOD data, sufficient history and minimum average turnover of VND 500 million/day.

A risk index is **not a probability**.

## Market-wide data discipline

The reference universe is the current VCI list of common stocks on HOSE, HNX and UPCoM, cross-matched to the Vietnam TradingView screener for the broad T-day scan. ETFs, covered warrants and derivatives are not treated as common stocks.

The broad scan is EOD/pre-session research. A code push during the Vietnam cash session is not allowed to overwrite the latest completed-EOD snapshot with a partial intraday observation. The scanner therefore retains or restores the previous completed-EOD snapshot during the cash session.

Unavailable benchmark-relative evidence is excluded and the remaining weights are renormalised; it is not imputed as a neutral market return.

## Single-name price resolver

The detail path uses multiple routes:

1. Yahoo Finance history when usable.
2. Vnstock Unified Market equity OHLCV fallback.
3. Pre-built CDN fallback for alert names and HOSE symbols where the primary API route is unavailable.

A valid symbol with insufficient history should still show the available detail/chart, but deep models are not forced to produce output when the history gate cannot support them.

## Point-in-time features

Historical supervised/deep validation uses price-volume information available at each state only. Core features include:

- 20-session realised volatility and historical volatility percentile;
- 60-session drawdown;
- 20-session momentum;
- distance to SMA50 and SMA200;
- RSI14;
- normalised MACD deterioration;
- abnormal volume.

Current news, fundamentals and cross-asset context are an overlay and are not inserted into historical ML validation unless dated vintages are available.

## Event definition and leakage guard

Primary crash event:

- horizon: 20 completed trading sessions;
- event: minimum forward drawdown <= -12% from the state date.

Primary rebound event:

- horizon: 20 completed trading sessions;
- event: maximum forward gain >= +12%.

A historical state can receive a crash/rebound label only when all required forward sessions are already in the historical record. The **current state is never treated as a labelled training example**. The UI reports both the current feature date and the last labelled training state so this can be audited.

## Corporate-action research guard

Raw prices remain visible on the investor chart. For model-return and event-label construction only, a one-day absolute log-return discontinuity above 0.22 is flagged as a possible corporate action and neutralised in the model-price path.

This is a heuristic research guard, not a substitute for an authoritative adjusted-price/corporate-action dataset. Suspects are counted and disclosed.

## Models

The calibrated research engine contains independent components:

- deterministic Structural EWS;
- Random Forest nonlinear benchmark;
- ANFIS-like adaptive neuro-fuzzy rules;
- k-means regime model;
- variational autoencoder reconstruction anomaly;
- LSTM dual crash/rebound sequence classifier.

Random and neural initialisation is seeded from symbol + feature version + policy version, and TensorFlow.js is run on the CPU in the research runtime to improve reproducibility.

## Chronological validation

Random train/test splitting is not used.

Each walk-forward fold is separated into:

1. model-fitting window;
2. purge;
3. probability-calibration window;
4. purge;
5. later out-of-sample test window.

The purge corresponds to approximately 20 trading sessions so that adjacent states cannot share the same forward event horizon across a boundary.

## Probability calibration

Raw model outputs do not share a common statistical meaning: a Random Forest score, a regime event rate and a VAE anomaly score are not automatically comparable probabilities.

Therefore each model is mapped to the observed crash outcome using **chronological isotonic calibration with beta smoothing** on the calibration window. A final current calibrated estimate uses the calibration relationship learned from historical out-of-sample predictions; historical performance metrics remain based on fold-level calibration/test separation.

The UI therefore separates:

- **Historical Risk Percentile / Research Risk Index (0–100):** a relative risk-ranking index;
- **Calibrated 20-session crash estimate (%):** an empirical probability estimate, shown with its historical OOS base rate.

## Rare-event metrics

For crash events, ROC-AUC alone is insufficient. VMEWS reports:

- PR-AUC / average precision;
- ROC-AUC;
- Brier score and Brier skill;
- precision;
- recall / missed-event rate;
- false-positive rate;
- alert rate;
- number of out-of-sample crash events.

PR-AUC is the primary ranking diagnostic for the rare positive event. Brier skill is used to assess probability calibration relative to a constant base-rate forecast.

## Decision threshold governance

Within each fold, an alert probability threshold is selected only from the preceding calibration window. The objective minimises an explicit expected loss where a missed event currently costs twice a false alert. The test fold does not choose its own threshold.

This does not imply that the selected cost ratio is universally optimal; it is a transparent research-policy choice and can be stress-tested.

## Validation-aware ensemble and ablation

Models are not guaranteed equal weight. Historical reliability is measured from PR-AUC skill over the event base rate, Brier skill and ROC-AUC skill. A weak component can receive zero effective weight.

The UI includes a model-ablation table showing each model's OOS PR-AUC, ROC-AUC, Brier skill and incremental PR-AUC relative to the structural benchmark.

Adding a model is justified only if it contributes incremental out-of-sample evidence; model complexity is not treated as evidence by itself.

## News evidence

The research-news pipeline collects a broad candidate set and performs relevance filtering, deduplication and coverage auditing. The statistical NLP baseline is a deterministic hashed unigram/bigram logistic model with financial seed labels and high-confidence distant supervision. Headline evidence is weighted by:

- relevance;
- source quality;
- materiality;
- recency decay.

Headline NLP is a contextual overlay, not the core historically validated crash model.

## Evidence sufficiency

A low risk score does not mean a security is safe. A high score does not mean a crash will occur.

The system separately grades evidence sufficiency using:

- historical session/sample depth;
- number of OOS crash events;
- PR-AUC skill over the event base rate;
- Brier skill;
- market context availability;
- news coverage;
- fundamental context availability.

When evidence is thin or historically weak, the system should explicitly downgrade the use case to screening/human review rather than state a strong conclusion.

## Research limitations

The current implementation has important boundaries:

1. The broad T-day reference universe is a **current listed universe**. It is appropriate for today's monitoring but is not yet a full historical point-in-time constituent database. Claims about long-horizon whole-market validation must account for delisted/transferred/new listings to avoid survivorship bias.
2. The corporate-action guard is heuristic; authoritative adjusted-price data would be preferable.
3. Current fundamentals/news are not historical vintages and therefore do not participate in historical ML validation.
4. Single-name event counts can be small. Probability estimates and model weights are downgraded when the OOS event depth is weak.
5. Browser deep learning is retained for a transparent research demonstration. A production institutional implementation should train/version signed model artefacts offline and perform inference from frozen models.
6. VMEWS is an early-warning decision-support system. It does not replace portfolio limits, suitability review, independent market judgement or investment due diligence.

## Literature informing the design

- Borio, C. & Drehmann, M. (2009), *Assessing the risk of banking crises – revisited*, BIS Quarterly Review.
- Drehmann, M. & Juselius, M. (2013), *Evaluating early warning indicators of banking crises: satisfying policy requirements*, BIS Working Papers No. 421.
- Aldasoro, I., Borio, C. & Drehmann, M. (2018), *Early warning indicators of banking crises: expanding the family*, BIS Quarterly Review.
- Niculescu-Mizil, A. & Caruana, R. (2005), *Predicting Good Probabilities With Supervised Learning*, ICML.
- Davis, J. & Goadrich, M. (2006), *The Relationship Between Precision-Recall and ROC Curves*, ICML.
- Bailey, D.H., Borwein, J., López de Prado, M. & Zhu, Q.J. (2015), *The Probability of Backtest Overfitting*, Journal of Computational Finance / SSRN.

These sources motivate real-time information discipline, interpretable amber/red alert zones, explicit false-alarm/missed-event trade-offs, probability calibration, rare-event evaluation and controls against repeated backtest selection.
