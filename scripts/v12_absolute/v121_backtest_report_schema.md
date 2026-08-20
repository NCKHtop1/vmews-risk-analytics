# V12.1 Challenger Report Schema

The challenger must be evaluated against V12 baseline on identical splits.

Required fields:

- horizon
- origin_date
- baseline_mae
- challenger_mae
- mae_delta
- baseline_rank_ic
- challenger_rank_ic
- dispersion_ratio
- calibration_error
- regime
- promotion_status

Promotion requires:

1. Blind OOS MAE improvement.
2. No degradation in rank IC.
3. Stable improvement across regimes.
4. No sealed label usage during model selection.
