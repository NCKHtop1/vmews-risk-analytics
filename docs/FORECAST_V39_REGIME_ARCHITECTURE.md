# Forecast V39: T+3–T+5 regime architecture

## Why V39 exists

The previous long-horizon learner estimated total issuer return in one model
and then adjusted its market intercept after prediction. That design retained
cross-sectional ranking skill but reacted too slowly when the whole HOSE regime
changed. It also used the pre-holdout estimator for live inference, so the
published model did not learn from the newest labels after the sealed test.

V39 fixes both problems without weakening the out-of-sample tests.

## Architecture

For T+3, T+4 and T+5, the return target is decomposed into two independently
trained components:

1. **Market regime** — the date-level median forward return, estimated with a
   standardized Ridge model from market return, volatility, breadth and weekday
   features.
2. **Issuer-relative return** — the issuer forward return minus that date-level
   market target, estimated by the regularized histogram gradient-boosting
   model and centered cross-sectionally at each known origin.

Ridge alpha, regime half-life, component weights, scale, conviction floor,
direction/magnitude blend and interval residuals are selected only on the
purged calibration period. The sealed holdout is never used for selection.

T+1 and T+2 keep the validated short-horizon architecture. T+2 retains its
pre-publication intercept shrinkage; T+3–T+5 no longer use that legacy path.

Implementation references:

- [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
- [scikit-learn HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
- [scikit-learn time-series split and gap semantics](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

## Evaluation and production separation

- The evaluation estimator is frozen after train/calibration and produces the
  sealed holdout plus three independently retrained walk-forward folds.
- A separate production estimator is then refit on every label matured by the
  latest completed exchange session.
- Architecture and calibration choices remain frozen during the production
  refit; sealed metrics are never recomputed with the refit estimator.
- Live news, holdings, flow and accounting context cannot alter the central
  forecast until separately promoted by an out-of-sample test.

## Long-horizon release rule

A T+3–T+5 central price is publishable only when all existing price, magnitude,
rank and interval checks pass, and all of the following are true:

- sealed architecture and every walk-forward fold use `MARKET_RELATIVE`;
- all three walk-forward folds have positive MAE and executable-MAE skill;
- mean executable walk-forward skill is at least 0.5%;
- the latest fold remains positive;
- sealed directional accuracy is at least 53%;
- the session-clustered paired improvement exceeds its daily standard error
  and is positive in at least three of four chronological blocks.

Failure abstains only that horizon; it cannot freeze current prices or erase
other independently validated horizons.

## V39 sealed results

| Horizon | Sealed MAE skill | Executable MAE skill | Direction accuracy | Rank IC | Positive executable WF folds | Mean executable WF skill |
|---|---:|---:|---:|---:|---:|---:|
| T+3 | 2.49% | 2.27% | 56.00% | 0.185 | 3/3 | 1.68% |
| T+4 | 1.94% | 1.59% | 56.43% | 0.168 | 3/3 | 1.29% |
| T+5 | 2.15% | 1.85% | 56.93% | 0.157 | 3/3 | 1.26% |

The dashboard exposes one exchange-valid central price for each horizon. Q20–Q80
is supporting uncertainty context, not a replacement forecast and not a promise
that the future close will equal the central price.
