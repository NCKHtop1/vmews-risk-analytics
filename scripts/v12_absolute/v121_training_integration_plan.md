# V12.1 Training Integration Plan

## Objective

Connect the Absolute Challenger layers into the H1-H5 evaluation flow without
modifying V12 production.

## Flow

1. Generate existing V12 alpha residual.
2. Generate market absolute return component.
3. Generate sector absolute return component.
4. Optimize blend weights only on pre-blind data.
5. Apply conditional magnitude calibration.
6. Produce challenger point forecast and uncertainty.
7. Compare against frozen V12 baseline.

## Required gates

- Lower OOS MAE than V12 baseline.
- No degradation in rank IC.
- Calibration remains valid.
- Stability across market regimes.
- No sealed holdout usage for selection.

## Output

v12_absolute_challenger_report.json

The challenger is promoted only after independent evidence of improvement.
