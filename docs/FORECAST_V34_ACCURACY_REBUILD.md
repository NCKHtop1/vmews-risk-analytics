# Forecast V34 accuracy rebuild

## Decision

The scalar T+1…T+5 price must not be presented as the primary forecast.  The
current conditional-median model is slightly better than a no-change quote on
long sealed samples, but its economic amplitude and recent stability are too
weak to support that interpretation.  V34 therefore presents the calibrated
Q20–Q80 distribution and down/base/up scenarios first, keeps the conditional
centre visible, and labels that centre `LOW_CONFIDENCE` unless it passes a new
point-specific gate.

This is not a cosmetic widening of FPT or any other symbol.  No holdout outcome
is used to move a live quote.

## Reproduced failure

The checked-in sealed audit shows the following point-forecast behaviour:

| Horizon | MAE skill vs no change | Direction | Point / realised median move |
| --- | ---: | ---: | ---: |
| T+1 | 1.01% | 50.3% | 30.2% |
| T+2 | 1.22% | 53.8% | 35.2% |
| T+3 | 0.65% | 53.9% | 28.9% |
| T+4 | 1.44% | 56.9% | 35.3% |
| T+5 | 0.84% | 57.0% | 32.9% |

The old promotion rule accepted improvements as small as 0.3–0.5% and mixed
interval/ranking quality with point accuracy.  A conditional median trained
with absolute error is rewarded for shrinking noisy returns toward zero, so a
small price move can pass even when it captures only about one third of the
typical realised move.

## Challengers tested

`scripts/forecast_v34_challenger_audit.py` rebuilds the panel from 394,568
point-in-time rows covering 403 HOSE symbols.  Selection is calibration-only;
the final 120 sessions remain sealed.  All online overlays require label
maturity to be strictly earlier than the next forecast origin.

The following candidates were rejected rather than promoted:

- squared-error point regression: slightly larger amplitude but weaker recent
  walk-forward results and no correction of FPT's sign;
- causal market/issuer residual correction: no horizon met the stability rule;
- fixed and dynamically estimated momentum overlays: calibration regimes did
  not persist into the sealed holdout;
- recent-window/time-decayed boosting: T+5 sealed skill fell below the current
  model and FPT's latest evaluated sign remained wrong;
- market-plus-issuer hierarchical ridge: lower T+5 MAE skill, direction and
  rank quality than the current pooled model.

Promoting any of these would manufacture larger-looking targets while reducing
out-of-sample accuracy.

## New point gate

`economic_point_gate` is separate from interval and ranking validation.  A
point must now satisfy all of the following:

- at least 52% overall and large-move direction accuracy;
- at least 25% point-to-realised median amplitude;
- paired MAE improvement larger than a standard error clustered by origin
  session and positive in at least three of four chronological blocks;
- positive executable skill and direction in the newest sealed block;
- positive results in at least two retrained walk-forward folds and at least
  0.5% mean executable skill.

Failing this gate does not erase the numerical distribution.  It prevents the
conditional centre from being described as a dependable target or trading
signal.

## Next numerical promotion path

A future scalar replacement should be promoted only after conditional
quantile models, tail-weighted direction models and point-in-time archives for
fundamental/news/flow features beat this V34 baseline across purged rolling
regimes.  The V34 challenger audit is the reproducible harness for that work.
