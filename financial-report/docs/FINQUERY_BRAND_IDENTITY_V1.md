# FinQuery · Brand Identity (2026-11-01)

Visual-only refresh. Keep existing authentication, portfolio calculations, market risk status colors, forecast, market data, API, routes, module layout and all component IDs unchanged.

Palette: Navy `#0A1B3D` · Electric Blue `#245BFF` · Cyan `#22C7EB` · Gray `#F3F6FA` · White `#FFFFFF`.

Assets: `frontend/finquery-mark.svg` standalone mark; `finquery-logo-light.svg` and `finquery-logo-dark.svg` horizontal lockups; `favicon.svg` app icon. Header SVG is inline for compatibility with the existing standalone HTML builder. All legacy HTML outside the original logo span is unchanged; existing CSS rules remain intact with a brand override appended to `responsive-system.css`.

Run `node --test financial-report/tests/brand_identity.test.cjs` and the existing FinQuery workflow checks. Do not update API/forecast/quant scripts as part of this release.
