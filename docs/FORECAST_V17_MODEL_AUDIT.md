# VMEWS V17.2: decision-time evidence and publication audit

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

## Matured event-reaction prior

V17.2 adds five event-reaction features derived from historical abnormal returns
at T+1, T+3 and T+5. For an event observed at decision date `D`, an older
event outcome may enter its prior only when the older event's `matureDate` is no
later than `D`. Current, same-day, future and not-yet-matured returns are never
available to the feature builder.

The prior is estimated hierarchically by event type and sentiment. A broad
market prior is shrunk toward zero, then an issuer prior is shrunk toward that
market estimate. This lets repeated earnings, ownership, regulatory, financing
and community-claim patterns inform the forecast without treating one headline
as a deterministic price move. The published audit records 37,392 matured
horizon outcomes, zero same-or-future outcomes used, and no current sector
membership lookup.

Historical community timestamps are often available only at source-default
hours. V17.2 therefore does not claim reliable historical pre-open classification
for every item. New ingestion must preserve the exact observed timestamp so a
future release can separately validate pre-open, intraday and after-close shock
features.

## SoluTION.AI security and deployment

The public GitHub CDN serves static HTML and JavaScript; it cannot keep a shared
provider credential secret. Direct Gemini mode therefore asks the user for a
Google AI Studio key and stores it only in the current tab's `sessionStorage`.
It is sent to Google's API in the request header, never written to GitHub,
`localStorage`, the prompt or a URL. Disconnecting or closing the tab removes it.

Direct mode can use Google Search and URL Context, ranks integrated and open
sources by trust, freshness and question relevance, keeps a bounded conversation
history, and automatically tries another available Gemini Flash model after a
provider failure. If Gemini remains unavailable, stock questions continue from
the audited VMEWS snapshot and the interface states the limitation.

`api/solution-ai.js` remains an optional secure Gemini adapter. A deployed trusted
backend must provide `GEMINI_API_KEY` as a server-side environment secret and
may set `GEMINI_MODEL` and `SOLUTION_AI_ALLOWED_ORIGINS`. The CDN dashboard
accepts only the trusted HTTPS backend URL, never an API key. Requests include
the currently selected issuer, validated forecasts, factor attribution, dated
flow, fund holdings, financial indicators, recent verified articles and
published validation status.

The adapter rate-limits clients, rejects oversized requests, restricts CORS,
sets `no-store`, avoids provider-secret exposure, and instructs Gemini not to
invent prices, fund trades, financial figures or unvalidated probabilities.
