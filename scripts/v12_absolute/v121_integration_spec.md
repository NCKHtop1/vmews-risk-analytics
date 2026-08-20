# V12.1 Absolute Challenger Integration

## Goal

Reduce near-zero point forecasts without artificial amplification.

## Final return equation

```
final_return = magnitude_scale * (
    market_weight * market_return
  + sector_weight * sector_return
  + alpha_weight * v12_alpha
)
```

## Constraints

- market weight: 20%-50%
- sector weight: 10%-40%
- alpha weight: 20%-60%
- magnitude scale: 0.5-1.5

## Selection rules

Weights are selected only from pre-blind windows.

Forbidden:
- using sealed labels for weight tuning
- maximizing forecast amplitude
- forcing positive/negative direction

## Promotion gate

V12.1 replaces V12 only if:

1. OOS MAE improves
2. Calibration remains valid
3. Rank IC does not materially deteriorate
4. Improvement survives regime split
5. Blind holdout passes

## Expected behavior

The model should not produce:

```
65.55 -> 65.53 -> 65.56 -> 65.54
```

only because of shrinkage.

It should produce movement when supported by:

- market regime
- sector state
- stock alpha
- confidence

but remain conservative when evidence is weak.
