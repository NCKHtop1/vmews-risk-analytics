# V12.1 Absolute Challenger Validation

## Objective
Reduce over-shrink of absolute price forecasts while preserving V12 alpha quality.

## Fixed comparison

Baseline:
- V12 production model

Challenger:
- Market absolute layer
- Sector absolute layer
- V12 alpha residual
- Conditional magnitude calibration

## Required gates

1. Same chronological origins.
2. Same blind holdout.
3. No sealed labels for model selection.
4. MAE must improve.
5. Calibration must pass.
6. Rank IC must not materially deteriorate.
7. Improvement must survive regime slices.

## Diagnostics

Track:
- forecast dispersion ratio
- realized dispersion ratio
- MAE
- RMSE
- rank IC
- directional accuracy
- bull/sideway/bear stability
