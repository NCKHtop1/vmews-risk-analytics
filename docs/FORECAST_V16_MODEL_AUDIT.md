# VMEWS Forecast V16 — model audit

## Publication state

- Forecast as-of: 2026-08-21
- Universe: 403/403 model-ready HOSE symbols; 0 stale EOD symbols
- Target: direct log return for T+1 through T+5
- Price output: valid HOSE tick grid and multi-session price limits
- Direction probability: published only for T+1 through T+4; T+5 is withheld by the Brier gate

## What changed in V16

The point forecast remains a conditional median. A separate absolute-move model now estimates the likely magnitude and produces calibrated bear/bull scenarios. This prevents a visually large but statistically unsupported point target from replacing an honest near-neutral median.

T+2 and T+4 retain 25% of the market-wide intercept, while T+3 removes it. These fixed horizon rules were frozen from pre-publication walk-forward experiments. T+1 and T+5 retain the raw market component. The T+2 shrinkage specifically protects the executable quote from recent market-regime drift without discarding the more stable cross-sectional ranking signal.

Weak T+1 signals are allowed to remain neutral instead of being forced one tick away from the reference close. The bear/bull scenarios remain non-flat.

## Final out-of-sample evidence

| Horizon | Executable MAE skill | Rank IC | Absolute-move skill | Q20–Q80 coverage | Walk-forward executable skill | Positive WF folds |
|---|---:|---:|---:|---:|---:|---:|
| T+1 | 0.47% | 18.08% | 4.86% | 61.5% | 1.17% | 3/3 |
| T+2 | 1.36% | 16.06% | 3.67% | 61.3% | 0.81% | 3/3 |
| T+3 | 0.87% | 14.80% | 2.74% | 60.9% | 0.04% | 2/3 |
| T+4 | 0.54% | 13.16% | 0.93% | 60.8% | 0.20% | 2/3 |
| T+5 | 1.43% | 13.24% | 2.08% | 60.9% | 0.33% | 2/3 |

Every walk-forward fold retrains from scratch with a maturity-purged training set and a pre-test calibration window. No future row or future label is used in training or calibration.

## Fund holdings

The Fmarket adapter collected 369 disclosed holdings from 42 funds, mapped to 57 HOSE symbols. `netAssetPercent` is converted from percentage points to a fraction of NAV; a regression test covers values below 1%, which otherwise risk a 100× unit error.

Only one valid point-in-time snapshot exists. Fund holdings therefore appear as current context but do not affect V16 forecasts. The model gate requires at least four independently collected snapshots. The 2026-08-23 snapshot is later than the 2026-08-21 forecast origin, so post-origin fund feature usage is zero.

## Limitations

- A PASS means improvement over the defined out-of-sample baselines, not a guaranteed future close.
- Central forecasts can be neutral when direction is weak. Use the absolute-move and Q20–Q80 ranges to understand plausible movement.
- News, flow and holdings remain subject to publisher coverage and timestamp quality.
