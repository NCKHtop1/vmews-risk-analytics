# VMEWS Pooled v5.2 — Final Research Release

Final commit: `faa92ca450fb982940ab5f6e733a23ada4267e29`

Final CDN:
`https://cdn.githubraw.com/NCKHtop1/vmews-risk-analytics/faa92ca450fb982940ab5f6e733a23ada4267e29/research-final.html`

## Pooled HOSE evidence

- Model: `VMEWS-POOLED-HOSE-1.2.0`
- Champion: L2 logistic regression selected against a shallow histogram gradient-boosting challenger on development folds.
- 64,145 labelled point-in-time panel states.
- 311 panel securities.
- Sealed period: 2025-04-23 through 2026-07-08.
- Sealed states: 7,427.
- Sealed positive states: 769.
- Distinct sealed crash episodes: 295.
- Sealed event base rate: 10.35%.
- PR-AUC: 0.1834.
- ROC-AUC: 0.6302.
- Full-sealed Brier skill: +0.0073.
- Structural-only PR-AUC on the same sealed block: 0.0949.
- Incremental pooled PR-AUC: +0.0886.
- Precision at the original pre-specified binary threshold: 27.0%, about 2.61x the sealed base rate.
- Crash-episode recall at that binary threshold: 8.47%; therefore standalone pooled alert policy is NOT approved.

## Post-freeze robustness

The model specification was not retuned for this audit.

- Moving 20-session-equivalent date-block PR-AUC 95% CI: approximately 0.149–0.248.
- Security-cluster PR-AUC 95% CI: approximately 0.137–0.238.
- Both lower bounds remain above the full sealed base rate.
- Sealed first half: PR-AUC approximately 0.138 vs base approximately 0.067; ROC-AUC approximately 0.675.
- Sealed second half: PR-AUC approximately 0.259 vs base approximately 0.142; ROC-AUC approximately 0.618.
- Top sealed risk decile empirical event rate: approximately 22.8%, about 2.2x the full sealed base rate.
- Ranking robustness: PASS, evidence grade MODERATE.

## Probability and alert governance

- Absolute pooled point probability: WITHHELD.
- Reason: calibration is not stable through the sealed sub-periods; the first half has negative Brier skill even though the full sealed Brier skill is slightly positive.
- Web displays pooled risk percentile and same-risk-decile historical event frequency/lift instead of presenting an unstable point probability.
- Standalone pooled alert: NOT APPROVED because the pre-specified binary operating threshold has insufficient crash-episode recall.
- Pooled output cannot create RED/YELLOW or autonomous risk actions.
- T-Day RED/YELLOW remains controlled by the canonical structural policy.

## Daily learning loop

- Daily workflow performs frozen-model inference only.
- Champion retraining/promotion is manual, not automatic.
- New observations must mature their 20-session labels before they can enter a future research dataset.

## Final smoke

GitHub Actions run `31567895483` completed successfully on the final commit.

Passed:
- static robust-pooled evidence/governance checks;
- FPT browser end-to-end;
- PNJ browser end-to-end;
- HPG browser end-to-end;
- VCB browser end-to-end;
- BNA outside-domain/no-imputation test.

Each HOSE browser smoke verifies detail, investor chart, local RF/VAE/LSTM stack, pooled robust section, WITHHELD absolute probability, empirical risk-decile evidence, standalone-alert rejection, robustness intervals, sealed sub-period audit, canonical watchlist and completed-EOD alignment. BNA verifies that an HNX/UPCoM security does not receive an imputed HOSE pooled score while its existing T-Day RED/local research remains available.

## Explicit limitations

- Historical pooled panel uses the current HOSE reference universe; delisted historical constituents have not yet been reconstructed, so survivorship bias remains an explicit limitation.
- Corporate actions still use a research discontinuity guard rather than an authoritative adjusted-price/corporate-action master.
- Ranking evidence is useful but MODERATE, not a guaranteed forecast.
- Absolute pooled point probability is currently withheld.
- The standalone pooled alert policy is currently not approved.
- Live forward performance must continue to be monitored for drift.
