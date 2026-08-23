# VMEWS V17: decision-time evidence and publication audit

## Forecast chronology

The last market close and the forecast decision timestamp are distinct. A fund
portfolio published after Friday's close but collected before the next Monday
session can inform Sunday's published forecast. It cannot be inserted into a
Friday training row or into any historical holdout observation.

V17 enforces both clocks:

- Historical model inputs include fund columns only after the existing history
  gate passes. Before that gate passes, every historical fund feature is hard
  masked to zero.
- A disclosure can enter the current decision prior only when its observed
  collection timestamp and reporting date are no later than the forecast
  decision timestamp.
- Legacy snapshots without an explicit `FRACTION_OF_NAV` unit declaration are
  rejected. This prevents the known 100-times portfolio-weight error from
  silently entering the model.
- No current disclosure or accounting observation is backfilled into historical
  feature, calibration, holdout or walk-forward rows.

## Independent validation versus live evidence

The T+1 through T+5 core forecasts retain sealed maturity-purged holdouts, four
chronological subperiods, and three independently retrained walk-forward folds.
Exchange-executable quote, absolute-move and calibrated interval gates remain
mandatory for publication.

Fund portfolio composition, archived foreign/proprietary transactions,
observed quarterly financial information, and verified news published after the
latest exchange close form a separate, explicit decision
prior. Its issuer-level adjustment is capped at the smaller of 1.2% or 22% of
the issuer's estimated horizon volatility. Components are exposed individually
as `FUND`, `FLOW`, `FUNDAMENTAL` and `EVENT`; published attribution still sums exactly
to the tradable HOSE quote.

Because the valid fund archive currently has only one usable dated observation,
this prior does not claim its own independently validated historical skill.
Artifacts identify this limitation with
`livePriorIndependentlyBacktested: false`. As valid snapshots accumulate, the
existing historical gate can enable point-in-time fund features without
fabricating older holdings.

Fund weights refer to allocations within each fund's portfolio. They are not
issuer ownership percentages and do not establish current fund purchases or
sales. Proprietary transaction values are converted from billions of VND to
VND before presentation. Stale observations retain their real date and amount,
while their forecast influence decays by observed age.

After-close and weekend headlines are accepted only when their exact publication
timestamp precedes the decision and their effective trading date is the next
session. They are displayed as newly published evidence and contribute to the
existing event factor without changing historical training or validation rows.

## SoluTION.AI security and deployment

The public GitHub CDN serves static HTML and JavaScript; it cannot execute a
serverless function or safely hold a provider credential. The dashboard
therefore offers a grounded, deterministic stock-analysis fallback without
claiming that Gemini is connected.

`api/solution-ai.js` adds an optional secure Gemini adapter. A deployed trusted
backend must provide `GEMINI_API_KEY` as a server-side environment secret and
may set `GEMINI_MODEL` and `SOLUTION_AI_ALLOWED_ORIGINS`. The CDN dashboard
accepts only the trusted HTTPS backend URL, never an API key. Requests include
the currently selected issuer, validated forecasts, factor attribution, dated
flow, fund holdings, financial indicators, recent verified articles and
published validation status.

The adapter rate-limits clients, rejects oversized requests, restricts CORS,
sets `no-store`, avoids provider-secret exposure, and instructs Gemini not to
invent prices, fund trades, financial figures or unvalidated probabilities.
