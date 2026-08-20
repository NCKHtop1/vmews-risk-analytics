# V12.1 Absolute Challenger Experiment Protocol

## Objective
Improve absolute T+1..T+5 price forecast without sacrificing V12 ranking quality.

## Comparison

Baseline:
- V12 production

Challenger:
- V12 alpha residual
- market absolute layer
- sector absolute layer
- conditional magnitude calibration

## Required metrics

- MAE
- RMSE
- Rank IC
- Calibration
- Forecast dispersion ratio
- Regime stability

## Hard rules

1. No sealed label usage for selection.
2. No manual forecast multiplier.
3. Larger price movement is not considered improvement by itself.
4. Challenger merges only if blind OOS wins.
