# Source Traceability — Supplied Thesis

This note maps the website content to the supplied thesis so a reviewer can distinguish source material from new engineering work.

## Direct thesis content used in the website

| Website item | Thesis content used |
|---|---|
| Research scope | VNIndex + sectoral Vietnamese stock market, 2007–2023 |
| Research dataset | 251 HOSE stocks, 745,452 observations, ten sectors; TradingView closing prices |
| Sector construction | Volume-weighted average closing price |
| Crash rule | COUNT / CRASH; specific weekly return below mean − 3.09 standard deviations |
| ANFIS | First-order Sugeno structure, membership functions, five-layer architecture, hybrid learning discussion |
| VAE | Encoder/decoder, latent Gaussian distribution, reconstruction error, KL divergence |
| Model benchmark | ANFIS AUC 0.970; LR 0.883; MLP 0.922; Simple Logistic 0.880 |
| Ensemble ANFIS metrics | R² 0.9891; MSE 11.1202; RMSE 3.3347; mean error 0.2305; error std. 0.5954 |
| Backtest table | 2008–2010 MACD; 2016–2019 EMA; 2020–2023 Stochastic performance metrics |
| Stress test | 20/61/122/245-day accuracy, precision, recall and F1 values |
| 2024 live test | Buy 03 Jan at 1,144; sell 01 Apr at 1,287; end of stated live-test period 19 Apr |
| Sector descriptive stats | Mean / stdev / skewness / kurtosis for ten sectors |
| Sector observation | Minerals often first to react to bad market information |

## New engineering work in this portfolio

The following items are **not claims from the thesis**:

- Vercel serverless market-data adapter.
- Browser-side data validation and fallback handling.
- The 0–100 live proxy risk score and its 35/25/20/20 weights.
- JavaScript dashboard implementation.
- Python reference ANFIS and VAE implementations.
- API caching and source/freshness badges.
- Portfolio CV wording and model-governance disclosure.

## Known source limitations

1. The raw 745,452-row thesis dataset is not embedded in the supplied PDF.
2. Original ANFIS/VAE/LSTM trained weight files are not embedded.
3. Complete tuned fuzzy rule parameters are not embedded.
4. The thesis contains an internal numerical inconsistency between the 2008–2010 cumulative-return table (31.76%) and narrative final capital (VND 833.63m from VND 500m).
5. The thesis train/validation/test date sentence is ambiguous for the validation/test starting date. The website does not invent a correction.
