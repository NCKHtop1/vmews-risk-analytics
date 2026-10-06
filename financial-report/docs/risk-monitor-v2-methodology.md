# FinQuery Market Risk V2 — Methodology and Validation

## Purpose

FinQuery Risk V2 is a market-state monitor for the live HOSE Core + Liquid universe. It is not a calibrated probability that the market will fall. Current stress and evidence of continuation over the next three sessions are validated separately.

## Research basis

- Holló, Kremer & Lo Duca — CISS: systemic stress aggregation should account for cross-segment co-movement rather than only standalone component levels.
- Office of Financial Research — Financial Stress Index: stress measures should be interpreted relative to historical distributions and remain decomposable into drivers.
- Amihud (2002) and Chordia, Roll & Subrahmanyam (2000): liquidity stress is related to price impact and market-wide commonality, not simply high trading volume.
- Andersen & Bollerslev: intraday volatility and activity have strong time-of-day seasonality, so partial-session observations should not be compared naively with full-day observations.
- Ang & Chen; Longin & Solnik: dependence can strengthen in downside/extreme market states.
- Kritzman et al.: concentration of variance in common factors is useful as a fragility/systemic-risk concept.
- Cleveland & McGill; Stephen Few: dashboard encodings should favor common-scale position/length, stable layouts, compact information hierarchy and details on demand.
- Vietnam high-frequency evidence (VNINDEX 2022–2025): intraday volatility/price discovery is time-dependent and constrained by liquidity, supporting session-aware normalization.

## Architecture

Five components retain a stable 30/20/20/20/10 interpretation:

1. **Market breadth (30%)** — decline share, severe maturity-adjusted losses, median maturity-adjusted return.
2. **Abnormal volatility (20%)** — maturity-adjusted intraday range, ATR/price regime, share of unusually wide ranges.
3. **Liquidity & selling pressure (20%)** — downside activity pace, broad high-volume selling, return-per-relative-volume price-impact proxy, negative CMF breadth.
4. **Cross-sector co-movement / fragility (20%)** — downside sector synchronization plus rolling historical downside sector correlation.
5. **Concentration under weak breadth (10%)** — turnover concentration is multiplied by breadth weakness and active-trading coverage; concentration cannot create market stress on its own.

## Intraday normalization

The repository does not yet contain a sufficiently long historical intraday bar archive to fit an empirical HOSE time-of-day curve without look-ahead or fabricated assumptions. V2 therefore uses a conservative fallback:

- return and range scale by square-root active trading time;
- volume uses a parameter-free symmetric U-shaped activity clock `(2/pi) * asin(sqrt(progress))` with a small opening floor;
- the lunch break contributes no active trading time;
- EOD observations remain unchanged.

Once a long enough append-only intraday archive exists, the fallback should be replaced by empirically fitted per-time-bucket profiles and revalidated out of sample.

## Historical calibration

- Up to 900 daily sessions are reconstructed from the market history branch.
- Current calibration uses the most recent 504 usable sessions.
- Every component is mapped to its empirical historical percentile.
- The weighted composite is mapped again to its own historical distribution.
- Therefore the displayed 0–100 score is a relative historical stress position, not a crash probability.

Risk bands:

- `<70`: Bình thường
- `70–84.9`: Cần theo dõi
- `85–94.9`: Cao
- `>=95`: Rất cao

## Walk-forward validation

Each OOS day is scored using prior history only. The test currently contains hundreds of walk-forward observations and evaluates score thresholds 70, 85 and 95.

Two questions are kept separate:

### State validation

A high score must identify materially worse contemporaneous market states. Gate 85 requires enough OOS observations/signals, a sensible signal rate, and a meaningfully worse median same-day market return than the unconditional sample.

### Continuation validation

Forward three-session evidence is optional and cannot redefine the state score. Continuation is only marked validated if adverse-tail precision lift, Youden separation and the forward-return distribution all improve versus the unconditional background. If this test fails, the UI must not claim that the market is likely to keep falling.

## Alert policy

- Normal high-risk alerts require confirmation in two consecutive snapshots.
- Extreme observations may alert immediately.
- Active alerts use a lower exit threshold than entry to avoid repeated on/off flicker.
- Sector state alerts and evidence of three-session continuation remain separate.

## UI policy

- No descriptive subtitle paragraphs under the Risk page header.
- Coverage and source time are compact header metadata.
- One contribution panel replaces duplicate component-card presentations.
- The heatmap keeps a fixed sector order so spatial memory is preserved across refreshes.
- Current-vs-prior-update and current-vs-previous-close comparisons are separate.
- Methodology details live behind the `(i)` help or drill-down, not in persistent header copy.

## Release gate

Risk V2 must not be published unless all of the following pass on the exact PR head:

- focused model tests;
- full FinQuery validation;
- publisher concurrency/governance checks;
- walk-forward state validation on real `financial-market-data` history;
- same-session calibration freshness;
- live coverage and source-time alignment;
- Pages build/deploy/verify;
- production browser smoke after deployment.

Production remains on the previous method until every gate is green.