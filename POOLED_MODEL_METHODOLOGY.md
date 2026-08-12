# VMEWS Pooled HOSE Crash-Risk Model — Methodology

## Objective

The pooled layer estimates whether a liquid HOSE security is entering a state associated with a **20-trading-session forward maximum drawdown of at least 12%**. It is an early-warning research classifier, not a price-target or buy/sell model.

The pooled layer is deliberately separate from the deterministic T-Day structural screen. The structural screen answers *how materially the current state is deteriorating*; the pooled model asks whether similar cross-sectional states across the HOSE panel have historically been associated with the defined 20-session drawdown event.

## Why pooled cross-sectional training

Single-security models can have very few independent crash episodes, making probability calibration unstable. The pooled panel lets a market-specific model learn from many securities and many stress episodes while retaining point-in-time features for each date.

This design is motivated by evidence that machine-learning gains in equity data can come from nonlinear interactions among momentum, liquidity and volatility signals, while over-flexible models remain vulnerable to overfitting. Gu, Kelly and Xiu (2020, *Review of Financial Studies*, DOI 10.1093/rfs/hhaa009) also report that shallow methods can outperform deeper architectures in low signal-to-noise asset-pricing settings. International evidence in *Alpha Go Everywhere* (2025, *Review of Asset Pricing Studies*, DOI 10.1093/rapstu/raaf005) supports market-specific training rather than assuming that a model trained in another market transfers cleanly.

## Panel construction

- Reference universe: current HOSE common-stock reference from VCI through vnstock.
- Price history: Yahoo Finance primary; existing Vnstock/CDN fallback where Yahoo history is unavailable.
- Completed EOD only. A current-day partial bar is excluded before the Vietnam cash session is safely complete.
- Minimum liquidity: median 20-session turnover of VND 500 million.
- Historical sampling: one point-in-time state every 5 trading sessions.
- Label horizon: 20 trading sessions.
- Positive event: forward maximum drawdown <= -12%.
- One-day absolute log-return discontinuities above 22% are flagged and neutralized only inside the research/model return path to reduce obvious corporate-action contamination. Raw chart prices remain unaltered.

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

The candidate set is intentionally small and fixed before the sealed test to reduce specification mining:

1. L2-regularized logistic regression with class weighting.
2. Shallow histogram gradient boosting with fixed depth, leaf-size, L2 regularization and deterministic random seed.

The purpose is not to maximize the number of algorithms. The selected champion must demonstrate incremental out-of-sample value over the structural baseline. A more complicated model is not preferred merely because it is more complicated.

## Chronological validation

The panel is ordered by date. No random train/test split is used.

- Development stage: expanding chronological folds.
- Between fit, calibration and test windows: a purge equivalent to at least 20 trading sessions.
- Candidate selection: development folds only.
- Final promotion test: last 15% of sampled panel dates is sealed and is not used for candidate selection.
- Probability calibration: regularized Platt calibration on a chronological window that is separate from classifier fitting.
- A binary decision threshold is selected on calibration data using a missed-event cost of 2 and false-alert cost of 1, but this threshold is assessed separately from the quality of the underlying probability/ranking model.

This separation follows scikit-learn's distinction between the statistical problem of estimating scores/probabilities and the decision problem of converting those scores to actions or class labels. Probability calibration is also fit on data separate from classifier fitting.

## Rare-event evaluation

The primary ranking metric is **PR-AUC**, because the crash class is imbalanced. Saito and Rehmsmeier (2015, PLOS ONE, DOI 10.1371/journal.pone.0118432) show why precision-recall evaluation is more informative than ROC alone for imbalanced classification.

The sealed report also includes:

- event base rate
- ROC-AUC
- Brier score and Brier skill versus a base-rate probability forecast
- precision and recall at the pre-specified operating threshold
- false-positive rate and alert rate
- missed-event rate
- precision enrichment versus the base rate
- crash-episode recall, where overlapping positive states are collapsed into event episodes
- date-block bootstrap confidence interval for PR-AUC
- direct comparison with the deterministic structural baseline on the same sealed test

## Dual promotion governance

VMEWS deliberately uses **two different gates** because predictive quality and an action threshold are different questions.

### Gate A — pooled predictive evidence / calibrated probability

The pooled challenger may be deployed as a separate predictive-evidence layer only if the sealed test satisfies all of the following:

- at least 100 distinct crash episodes in the sealed evaluation
- PR-AUC exceeds the sealed event base rate by more than 0.02
- PR-AUC exceeds the structural baseline on the same sealed block by at least 0.005
- Brier skill is positive
- ROC-AUC is at least 0.58
- the lower bound of a 95% date-block-bootstrap confidence interval for PR-AUC remains above the sealed event base rate

Passing Gate A permits VMEWS to show the pooled calibrated probability and risk percentile as **predictive research evidence**. It does not authorize a RED/YELLOW alert by itself.

### Gate B — standalone binary alert policy

The pooled model may become an independent alert generator only if Gate A passes **and** crash-episode recall at the pre-specified binary operating threshold is at least 35% on the sealed test.

If Gate B fails:

- the pooled probability/rank may still be displayed if Gate A passed;
- the failure and low binary-threshold recall remain visible in the model audit;
- pooled output cannot create RED/YELLOW;
- pooled output cannot create a buy/sell or autonomous risk action;
- the canonical T-Day structural policy remains the alert source.

This prevents the project from hiding a weak operating threshold behind otherwise useful probability/ranking performance.

## Production learning loop

VMEWS does **not** automatically retrain after every daily observation.

- Daily: refresh completed-EOD features and run inference with the frozen champion.
- After labels mature: observations become eligible for the next research dataset.
- Monthly: retrain challenger candidates.
- Promotion: only after the complete sealed predictive-evidence gate passes. An independent alert policy requires its own Gate B approval.

This champion/challenger design prevents a model from changing behavior every day simply because a few new observations arrived.

## Known limitations

1. The historical pooled panel currently uses today's HOSE reference universe. Historical delisted constituents are not yet reconstructed, so survivorship bias is an explicit limitation. Classic survivorship research shows that conditioning on survivors can create or exaggerate apparent predictability; VMEWS therefore does not claim a survivorship-free historical panel at this stage.
2. Corporate-action treatment is still a research heuristic rather than an authoritative adjusted-price/corporate-action master.
3. The model predicts the defined drawdown event only. It does not predict target prices or investment returns.
4. Positive Brier skill may still be economically small. A statistically acceptable probability layer is not the same as a highly accurate forecast.
5. A sealed historical pass does not guarantee future accuracy. Live calibration and drift must be monitored.
6. Model development is deliberately constrained after sealed-test observation. Repeatedly tuning features, architectures or thresholds against the same holdout would convert it into a development set and create backtest-overfitting risk (Bailey et al., *The Probability of Backtest Overfitting*).

## Research references

- Gu, S., Kelly, B., & Xiu, D. (2020). *Empirical Asset Pricing via Machine Learning*. Review of Financial Studies, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009.
- *Alpha Go Everywhere: Machine Learning and International Stock Returns* (2025). Review of Asset Pricing Studies, 15(3-4), 288–331. DOI: 10.1093/rapstu/raaf005.
- Saito, T., & Rehmsmeier, M. (2015). *The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets*. PLOS ONE, 10(3), e0118432. DOI: 10.1371/journal.pone.0118432.
- Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2015). *The Probability of Backtest Overfitting*. Journal of Computational Finance / SSRN 2326253.
- Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992). *Survivorship Bias in Performance Studies*. Review of Financial Studies, 5(4), 553–580. DOI: 10.1093/rfs/5.4.553.
- scikit-learn 1.9 documentation, *Probability calibration* and *Tuning the decision threshold for class prediction*.
