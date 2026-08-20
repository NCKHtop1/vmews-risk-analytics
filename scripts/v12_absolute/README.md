# V12.1 Absolute Forecast Layer Challenger

Purpose: improve absolute T+1..T+5 price forecasts without replacing the existing V12 alpha engine.

Design:

1. Market absolute return layer
2. Sector absolute return layer
3. Existing V12 cross-sectional alpha residual
4. Conditional magnitude calibration
5. Challenger gate against V12 baseline

The production V12 model remains unchanged. Promotion requires blind OOS improvement.

Target failure mode addressed:
- Avoid forecasts collapsing to near-zero movement for all symbols.
- Avoid artificial large forecasts by multiplying returns.
- Add economically grounded market and sector components.
