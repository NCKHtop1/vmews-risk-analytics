# VMEWS Pooled HOSE Crash-Risk Model — Methodology

## Objective

The pooled layer asks whether a liquid HOSE security is entering a state historically associated with a **20-trading-session forward maximum drawdown of at least 12%**. It is an early-warning research classifier, not a price-target or buy/sell model.

The pooled layer is deliberately separate from the deterministic T-Day structural screen. The structural screen answers *how materially the current state is deteriorating*; the pooled model asks whether similar cross-sectional states across the HOSE panel have historically ranked toward the defined 20-session drawdown event.

## Why pooled cross-sectional training

Single-security models can have very few independent crash episodes, making validation and probability calibration unstable. The pooled panel lets a market-specific model learn from many securities and many stress episodes while retaining point-in-time features for each date.

The candidate set is intentionally conservative. Gu, Kelly and Xiu (2020, *Review of Financial Studies*, DOI 10.1093/rfs/hhaa009) show that machine-learning gains in equity data can arise from nonlinear interactions among characteristics, while deeper or more flexible methods are not automatically superior in low signal-to-noise finance. International evidence in *Alpha Go Everywhere* (2025, *Review of Asset Pricing Studies*, DOI 10.1093/rapstu/raaf005) also motivates market-specific training rather than assuming clean transfer from another market.

## Panel construction

- Reference universe: current HOSE common-stock reference from VCI through vnstock.
- Price history: Yahoo Finance primary; existing Vnstock/CDN fallback where Yahoo history is unavailable.
- Completed EOD only. A current-day partial bar is excluded before the Vietnam cash session is safely complete.
- Minimum liquidity: median 20-session turnover of VND 500 million.
- Historical sampling: one point-in-time state every 5 trading sessions.
- Label horizon: 20 trading sessions.
- Positive event: forward maximum drawdown <= -12%.
- One-day absolute log-return discontinuities above 22% are flagged and neutralized only inside the research/model return path. Raw chart prices remain unaltered.

### Per-security features

- 1-day return
- 5-day return
- 20-day momentum
- 60-day drawdown
- distance from SMA50
- distance from SMA200
- RSI14
- log median turnover
- deterministic structural technical score

### Cross-sectional features at each date

- percentile/risk ranks of momentum, drawdown, SMA50 distance, SMA200 distance and RSI
- liquidity rank
- structural technical-risk rank

### Market-breadth features at each date

- fraction of securities with negative 20-day momentum
- fraction below SMA50
- median 20-day momentum
- median 60-day drawdown
- cross-sectional momentum dispersion
- mean structural technical risk

No future label or future market state enters the feature vector.

## Candidate models

The candidate set was fixed before opening the final sealed block:

1. L2-regularized logistic regression with class weighting.
2. Shallow histogram gradient boosting with fixed depth, leaf size, L2 regularization and deterministic random seed.

The purpose is not to maximize the number of algorithms. The champion must demonstrate incremental out-of-sample value over the deterministic structural baseline. The selected champion is **L2 logistic regression**; the more complex candidate was not preferred merely for being nonlinear.

## Chronological validation

The panel is ordered by date. No random train/test split is used.

- Development stage: expanding chronological folds.
- Between fit, calibration and test windows: purge equivalent to at least 20 trading sessions.
- Candidate selection: development folds only.
- Final promotion test: last 15% of sampled panel dates is sealed and is not used for candidate selection.
- Probability calibration: regularized Platt calibration on a chronological window separate from classifier fitting.
- A binary decision threshold is selected on calibration data using a missed-event cost of 2 and false-alert cost of 1, but threshold/action quality is assessed separately from continuous ranking quality.

This follows the distinction in scikit-learn's model-evaluation guidance between estimating scores/probabilities and choosing a decision threshold for an action.

## Rare-event evaluation

The primary ranking metric is **PR-AUC** because the crash class is imbalanced. Saito and Rehmsmeier (2015, PLOS ONE, DOI 10.1371/journal.pone.0118432) show why precision-recall evaluation is more informative than ROC alone for imbalanced classification.

The sealed report also includes:

- event base rate
- ROC-AUC
- Brier score and Brier skill versus a base-rate probability forecast
- precision and recall at the pre-specified operating threshold
- false-positive rate and alert rate
- missed-event rate
- precision enrichment versus base rate
- crash-episode recall, collapsing overlapping positive states into event episodes
- direct comparison with the deterministic structural baseline on the same sealed test

## Sealed result for VMEWS-POOLED-HOSE-1.2.0

The post-freeze reconstruction contains approximately **64 thousand labelled point-in-time states across 311 HOSE securities**. The final sealed block contains **7,427 states, 242 securities and about 295 distinct crash episodes**.

The frozen champion achieves approximately:

- PR-AUC: **0.184** versus sealed event base rate **0.103**
- ROC-AUC: **0.631**
- full-sealed Brier skill: **+0.007**
- PR-AUC improvement over the structural baseline: approximately **+0.089**
- precision at the original cost-based threshold: approximately **27%**, or roughly **2.6x** the sealed event base rate
- crash-episode recall at that threshold: approximately **8.5%**

The low binary-threshold recall is kept visible; it is not hidden by the stronger continuous ranking metrics.

## Post-freeze robustness audit

After model architecture, features and the sealed split were frozen, an independent audit was added **without retuning the model**. Post-freeze diagnostics are allowed to downgrade evidence only.

The audit uses:

1. **Moving sampled-date block bootstrap** with four sampled panel dates per block, approximately one 20-session label horizon. Each sampled date keeps the full cross-section together.
2. **Security-cluster bootstrap**, resampling securities while preserving each sampled security's entire time history.
3. **Sealed sub-period stability**, splitting the sealed period into two chronological halves.
4. **Calibration diagnostics**, including equal-count-bin expected calibration error and Brier skill by sealed sub-period.
5. **Ten sealed risk buckets**, reporting empirical event frequency and lift by pooled risk rank.

The frozen ranking remains robust:

- moving 20-session-equivalent block PR-AUC 95% CI: approximately **0.149–0.248**
- security-cluster PR-AUC 95% CI: approximately **0.137–0.238**
- both lower bounds remain above the full sealed base rate
- sealed first half: PR-AUC about **0.138** versus base **0.067**, ROC-AUC about **0.675**
- sealed second half: PR-AUC about **0.259** versus base **0.142**, ROC-AUC about **0.619**
- top sealed pooled-risk decile: empirical event rate about **22.8%**, approximately **2.2x** the full sealed base rate

Therefore the pooled **risk ranking** passes the robustness gate at a **MODERATE** evidence grade.

## Why absolute probability is withheld

The same robustness audit finds that probability calibration is not stable enough across time:

- full sealed Brier skill is slightly positive;
- first sealed half Brier skill is negative;
- second sealed half Brier skill is positive;
- equal-count-bin calibration error is around 4.3%.

Because a trustworthy point probability should remain reasonably calibrated across sub-periods, VMEWS now **withholds the pooled absolute 20-session crash probability**. The web displays instead:

- pooled risk percentile;
- sealed empirical event frequency for the corresponding risk decile;
- empirical lift versus sealed base rate;
- robust PR-AUC intervals and sub-period evidence.

The bucket event rate is explicitly an **empirical historical frequency for a risk bucket, not a point forecast for the current security**.

No calibrator or model was retuned after observing this failure. A future probability version requires a new independent validation exercise.

## Three separate governance gates

### Gate A — predictive ranking promotion

The pooled challenger may be deployed as a predictive-ranking layer only if:

- at least 100 distinct crash episodes exist in the sealed evaluation;
- PR-AUC exceeds sealed base rate by more than 0.02;
- PR-AUC exceeds the structural baseline by at least 0.005;
- full sealed Brier skill is positive;
- ROC-AUC is at least 0.58;
- a dependence-aware PR-AUC lower confidence bound remains above base rate.

The current frozen model passes this ranking/predictive-evidence gate.

### Gate B — absolute probability stability

Absolute probability is displayed only if ranking robustness passes **and**:

- full sealed Brier skill is positive;
- each sealed chronological half has positive Brier skill;
- calibration ECE is at most 5%.

The current frozen model **fails Gate B because the first sealed half has negative Brier skill**. Absolute point probability is therefore WITHHELD.

### Gate C — standalone binary alert policy

The pooled model may become an independent alert generator only if the predictive evidence is approved and crash-episode recall at the pre-specified binary operating threshold is at least 35% on the sealed test.

The current frozen model **does not pass this gate**. Pooled output cannot create RED/YELLOW, cannot generate a buy/sell recommendation and cannot create an autonomous risk action. Canonical T-Day RED/YELLOW remains structural-policy driven.

## Production learning loop

VMEWS does **not** automatically retrain after every daily observation.

- Daily: refresh completed-EOD features and run inference with the frozen champion.
- Daily pooled output: risk percentile / risk bucket only unless the absolute-probability stability gate is approved.
- After labels mature: observations become eligible for a future research dataset.
- Champion retraining/promotion: **manual workflow only**, after explicit review and a new sealed validation exercise.

This prevents silent production-model changes and prevents a few new observations from changing behavior every day.

## Known limitations

1. The historical pooled panel currently uses today's HOSE reference universe. Historical delisted constituents are not reconstructed, so survivorship bias is an explicit limitation. VMEWS does not claim a survivorship-free historical panel.
2. Corporate-action treatment is a research heuristic rather than an authoritative adjusted-price/corporate-action master.
3. The model predicts the defined drawdown event only. It does not predict target prices or investment returns.
4. The ranking evidence is meaningful but not near-perfect; the system labels it MODERATE rather than STRONG.
5. Absolute pooled probability is intentionally withheld because sub-period calibration is unstable.
6. The current standalone binary threshold has low crash-episode recall and is not deployed as an alert generator.
7. A sealed historical pass does not guarantee future performance. Live drift and calibration must be monitored.
8. Model development is deliberately constrained after sealed-test observation. Repeated tuning against the same holdout would convert it into a development set and create backtest-overfitting risk.

## Research references

- Gu, S., Kelly, B., & Xiu, D. (2020). *Empirical Asset Pricing via Machine Learning*. Review of Financial Studies, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009.
- *Alpha Go Everywhere: Machine Learning and International Stock Returns* (2025). Review of Asset Pricing Studies, 15(3-4), 288–331. DOI: 10.1093/rapstu/raaf005.
- Saito, T., & Rehmsmeier, M. (2015). *The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets*. PLOS ONE, 10(3), e0118432. DOI: 10.1371/journal.pone.0118432.
- Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2015). *The Probability of Backtest Overfitting*. Journal of Computational Finance / SSRN 2326253.
- Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). *Survivorship Bias in Performance Studies*. Review of Financial Studies, 5(4), 553–580. DOI: 10.1093/rfs/5.4.553.
- scikit-learn documentation, *Probability calibration* and *Tuning the decision threshold for class prediction*.
