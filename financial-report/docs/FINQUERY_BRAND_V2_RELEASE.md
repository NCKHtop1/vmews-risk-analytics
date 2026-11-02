# FinQuery - Q-Data Design System V2 release

Scope: visual-only brand alignment for the active FinQuery application (November 2, 2026).

## Brand identity
- Navy #0A1B3D, midnight #07152D, electric blue #245BFF, cyan #22C7EB.
- White / light workspace #FFFFFF / #F3F6FA; neutral border #DEE7F3.
- Blue on white contrast exceeds 4.5:1. Do not use cyan as text on white.
- Shared Q-Data SVG: financial-report/frontend/finquery-mark.svg, favicon.svg.

## Updated views
- Main application shell, header, mobile menu, dashboard
- Market, chart shell, scanner controls, financial report and News
- Portfolio tabs/cards, Strategy workspace, Risk Monitor, Macro and ESG, AI drawer
- Forecast VN100: dark navy/blue/cyan shell while preserving positive/negative colors
- FinQuery Login, Admin and Data Hub
- Mobile browser theme color on main and Forecast

## Non-negotiable boundaries
No change to JavaScript business engines, Python backend, API routes, market/forecast data, DOM IDs for existing controls, authentication logic, RBAC, Portfolio calculations, historical backtests, chart time series or up/down/risk semantic colors. Main app CSS and Forecast CSS changes are append-only.

VMEWS risk research homepage (/index.html, /dashboard.html) is a separate product and intentionally not rebranded. Redirect-only pages are unchanged.

## Release checks
- node --test financial-report/tests/brand_system_v2.test.cjs
- node --test financial-report/tests/responsive_system.test.cjs
- node --test financial-report/tests/workspace_tabs.test.cjs
- node --test financial-report/tests/portfolio_ux_handoff.test.cjs
- node scripts/forecast-navigation-test.cjs
- Existing responsive browser tests cover navigation, chart, tables and Portfolio from 320 to 1920px.
- Before claiming live: confirm Vercel Production READY, deployed commit, domain aliases and Q-Data assets in the generated financial-report/index.html. Report limitations when runtime/browser access is unavailable.

## Rollback
Revert only the Design System V2 PR and redeploy. Do not modify databases, market datasets or forecast models to restore the visual theme.
