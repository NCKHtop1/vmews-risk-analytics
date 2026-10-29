# FinQuery | UX/UI Responsive QA & Release Plan

Updated: 2026-10-29. Scope: authenticated FinQuery main dashboard, secure login and admin.

## 1. Critical user journeys

| Workspace | Mobile first task | Desktop first task | Hard acceptance |
| --- | --- | --- | --- |
| Navigation / login | Open one compact menu, choose section, sign in | Direct section links | No clipped nav, menu closes by Escape/outside click |
| Market + Candlesticks | Find ticker, read latest quote, change candle period | Analyze full chart | Readable chart, non-overlapping filters, advanced controls on demand |
| Scanner + Futures + Ownership | Filter signals, inspect contracts/holders | Compare detailed rows | Tables scroll only inside table container |
| Strategy Builder | Choose conditions, run/inspect output | Assemble multi-condition strategies | Single-column mobile, controls remain tappable |
| Risk Monitor | Check score, alerts, breadth, sectors | Drill into sector/issuer | Charts and heatmaps fit without document overflow |
| Macro + ESG | Check latest point, compare history, download | Use multiple charts | Provenance stored internally, compact dates and one download per valid curve |
| Financial Reports | Select company and periods, export and read BS/IS/CF/ratios | Compare broad period tables | Report table scroll is local; sticky first column retained |
| Dolphin AI | Open/close assistant without hiding content | Use full side dialog | No distracting glow, keyboard-aware mobile height |
| Admin / secure login | Authenticate, review roles, approve | Batch review and history | Narrow sign-in width, manageable horizontal user table |

## 2. Interaction / layout rules

1. **320, 360, 390, 430, 768, 1024, 1440, 1920 px** are regression widths.
2. No horizontal document overflow. Only table and deliberate chart scroll areas may overflow internally.
3. Interactive controls in primary mobile workflows target a minimum ~40-44 px; icon-only context-help buttons remain small with separate affordances.
4. One active mobile navigation menu, single accessible trigger with correct `aria-expanded`, Escape and outside-click dismissal. Reuse existing routes.
5. Keep the four core chart controls on the surface; advanced zoom, fit, marker and fullscreen behind `Công cụ khác`. Never remove chart logic or IDs.
6. Explicitly display stale/empty data without inventing financial metrics. Do not surface verbose provenance-debug sentences in cards.
7. Calm visual hierarchy: white cards, restrained borders, readable contrast, charts first; no decorative glows occluding data.
8. Source / permission enforcement, quotes, history, forecasts and risk calculations must remain untouched by UI-only changes.

## 3. Implementation and release stages

- **P0: Layout foundation** — shared `responsive-system.css` applied AFTER legacy CSS, responsive header navigation, mobile market tabs, compact chart controls, strategy/risk/report layout; secure auth and admin touch corrections.
- **P1: Integration** — wire stylesheet and navigation into BOTH `frontend/index.html` and `scripts/build_cdn.py` (the production one-file bundle); prevent production from silently serving old CSS.
- **P2: Regression** — `responsive_system.test.cjs`, headless Chrome `site_responsive_browser.py`, the existing Macro & ESG and Quant gates. No authentication or backend mocking on production; local deterministic fixture tests only.
- **P3: Release** — merge only when QA passes; GitHub Pages must finish Build/Deploy/Verify; create Vercel Production with exact main SHA; validate `finquery.info.vn` alias points to the new READY deployment.
- **P4: Field QA** — validate authenticated real-device touch interactions with owner and normal account, iOS Safari and Android Chrome, and monitor actual user feedback. This manual stage is not proven by synthetic browser tests.

## 4. Acceptance and non-goals

**Automated exit criteria:** all listed viewport sizes pass, document width fits; header/menu and tabs fit; chart advanced controls open; finance/risk tables scroll locally; no duplicated controls/IDs; one-file release contains the new CSS and JS once; existing market/macro/strategy/risk unit tests pass.

**Out of scope:** changing financial-source integrity rules, scraping endpoints, database records, privilege checks, theme redesign, speculative UX enhancements that add visual clutter. Tests do not claim to authenticate a user or cover every possible device font-scaling setting.

## 5. Ongoing prevention

The `.github/workflows/finquery-responsive-site-qa.yml` check runs on every relevant pull request / main push and may be manually dispatched. Extend fixture coverage whenever a new page or interactive section is added.
