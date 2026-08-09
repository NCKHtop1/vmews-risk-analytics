# VMEWS — Vietnam Market Early Warning System

A portfolio-grade research-to-production demo for market risk analytics.

**Purpose:** turn the supplied graduation thesis, *“An Exploration of Stock Crashes in Vietnam: Can Early Warning Model Mitigate the Impact?”* (2024), into a clean, deployable website with a live VN-Index monitoring layer, transparent data controls, thesis benchmarks, backtesting summaries, sector analytics, and runnable reference model code.

> **Important:** this project is a portfolio and research demo. It is not investment advice and it is not a bank production risk engine.

---

## 1. What is directly supported by the thesis

The website preserves these thesis statements and reported results:

- Research period: **2007–2023**.
- Research universe: **251 HOSE stocks**, **745,452 observations**, across ten sectors.
- Data source stated in thesis: **TradingView closing prices**.
- Crash framework: **COUNT / CRASH**, where a weekly specific return is a crash when it falls below **mean − 3.09 standard deviations**.
- Predictive framework: **ANFIS** with a **Variational Autoencoder (VAE)** / deep-learning anomaly layer.
- Classifier benchmark reported in the thesis:
  - ANFIS AUC **0.970**
  - Logistic Regression AUC **0.883**
  - Multilayer Perceptron AUC **0.922**
  - Simple Logistic AUC **0.880**
- Ensemble ANFIS fit metrics reported in the thesis: R² **0.9891**, MSE **11.1202**, RMSE **3.3347**, mean error **0.2305**, error standard deviation **0.5954**.
- Stress-test results reported in the thesis:
  - 20 days: accuracy **0.95**, precision **0.96**, recall **0.94**, F1 **0.95**
  - 61 days: **0.92 / 0.93 / 0.90 / 0.91**
  - 122 days: **0.88 / 0.89 / 0.85 / 0.87**
  - 245 days: **0.83 / 0.84 / 0.80 / 0.82**
- Backtest metrics with hypothetical starting capital of VND 500 million:
  - 2008–2010 T+3 MACD: cumulative return **31.76%**, win rate **56.98%**, max drawdown **19.80%**, annualised return **10.50%**.
  - 2016–2019 T+2 EMA: **92.57%**, **77.15%**, **14.50%**, **22.14%**.
  - 2020–2023 T+2.5 Stochastic: **41.83%**, **60.27%**, **21.40%**, **13.70%**.
- Live-test narrative in the thesis covers **01 Jan–19 Apr 2024**, including a reported buy signal on **03 Jan 2024 at VN-Index 1,144** and sell signal on **01 Apr 2024 at 1,287**.

### Source inconsistency preserved, not hidden

The thesis table reports **31.76% cumulative return** for the 2008–2010 strategy. A later narrative paragraph says VND **500 million became 833.63 million**. Those numbers are not arithmetically equivalent. This project uses the table as the main benchmark and explicitly records the narrative value rather than silently changing either source statement.

---

## 2. What cannot be reproduced exactly from the PDF alone

The supplied PDF does **not** include:

- the original 745,452-row raw dataset as a downloadable file;
- the complete MATLAB project;
- the original trained ANFIS weights;
- the full learned fuzzy rule base;
- every final membership-function count and optimized parameter;
- the trained VAE/LSTM weight files;
- a production data-feed credential.

Therefore, it would be misleading to display a new live number and call it the exact original 2024 ANFIS/VAE prediction.

The project solves this correctly by separating:

1. **Thesis benchmark layer** — immutable values copied from the paper.
2. **Reference model layer** — runnable ANFIS + VAE code matching the described method class.
3. **Live operational proxy** — a transparent risk score based on current market data, clearly labelled as a proxy.

---

## 3. Live dashboard logic

The website calls `/api/market`, a Vercel serverless function that requests the public Yahoo Finance chart feed for `^VNINDEX.VN`.

The UI calculates:

- daily log return;
- 20-day annualised volatility;
- 60-day drawdown;
- 20-day price momentum;
- latest-return anomaly z-score;
- a transparent **0–100 live proxy risk score**:

```
Risk Score =
  35% × volatility pressure
+ 25% × drawdown pressure
+ 20% × negative momentum pressure
+ 20% × return anomaly pressure
```

This score is an engineered live monitoring layer. It is **not** labelled as the thesis ANFIS probability.

Risk state:

- `0–34` → LOW
- `35–64` → WATCH
- `65–100` → HIGH

### Fallback design

If the upstream market feed fails:

- the serverless request returns an error;
- the browser loads `data/fallback-market.json`;
- the dashboard changes the badge from **LIVE** to **FALLBACK**;
- the latest fallback date is shown visibly.

The fallback file is intentionally small. It exists to keep the demo usable, not to pretend that a stale dataset is live.

---

## 4. Data controls

Before live analytics are calculated, browser code applies basic controls:

- required date;
- valid positive close price;
- invalid/null rows removed;
- duplicate dates de-duplicated;
- ascending date sort;
- source mode shown to user;
- last market session shown as data freshness.

For a production/bank implementation, add:

- licensed official market feed;
- source-to-target reconciliation;
- business-date/calendar validation;
- feed completeness controls;
- corporate action methodology where relevant;
- run ID and input snapshot ID;
- immutable model version;
- alert audit trail;
- independent model validation;
- access control and approval workflow.

---

## 5. Reference model code

`model/` contains runnable research code:

- `data_pipeline.py` — downloads daily VN-Index data and engineers transparent features.
- `crash_label.py` — implements the thesis equations for volume-weighted sector price, log return, expanded market-model residuals, specific weekly return, and 3.09-sigma crash flagging.
- `anfis_hybrid.py` — compact first-order Sugeno ANFIS with Gaussian memberships and alternating least-squares / gradient updates.
- `vae.py` — compact VAE anomaly model using reconstruction error + KL divergence.
- `train_demo.py` — chronological 80/10/10 reference experiment.

The code comments deliberately state where the implementation is a reference approximation because the original trained objects are unavailable.

### Run model experiment

```bash
cd VMEWS_Portfolio
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd model
python train_demo.py
```

Output is saved to `data/demo-model-output.json`.

---

## 6. Run the website locally

For the static UI only:

```bash
cd VMEWS_Portfolio
python -m http.server 8080
```

Open `http://localhost:8080`.

Because Python's static server cannot execute the `/api/market` serverless function, local static mode will use the fallback market snapshot.

For the complete live API experience, use Vercel CLI:

```bash
npm i -g vercel
cd VMEWS_Portfolio
vercel dev
```

---

## 7. Deploy to Vercel

No frontend build step is required.

```bash
cd VMEWS_Portfolio
vercel
```

For production:

```bash
vercel --prod
```

Vercel will serve `index.html` and execute `api/market.js` as a serverless endpoint.

---

## 8. Website sections

- **Overview** — portfolio positioning and current market snapshot.
- **Live Monitor** — VN-Index chart, risk score, volatility, anomaly and recent observations.
- **Model Lab** — ANFIS + VAE architecture, exact thesis benchmark values and reproducibility disclosure.
- **Backtest & Stress Test** — regime backtests and forecast-horizon stress metrics.
- **Sector Risk** — thesis descriptive statistics across ten sectors.
- **Data & Methodology** — crash rule, research split, live data lineage, controls and governance.

---

## 9. Suggested CV wording

**Vietnam Market Early Warning System — Market Risk Analytics Portfolio**

- Converted an academic ANFIS + VAE stock-crash early-warning framework into a deployable risk analytics web application for the Vietnamese equity market.
- Built a serverless market-data pipeline, data-quality controls, feature engineering, risk monitoring dashboard and transparent fallback logic.
- Reproduced the thesis CRASH/COUNT methodology and implemented reference ANFIS hybrid learning and VAE anomaly detection in Python.
- Presented model benchmarking, backtesting, stress testing, sector analytics and model-governance disclosures in a recruiter-friendly live dashboard.

**Tech:** Python, Pandas, PyTorch, Scikit-learn, JavaScript, Chart.js, Serverless API, Vercel, Time Series, Model Risk, Market Risk Analytics.

---

## 10. Recommended interview explanation

> “I did not present the original thesis result as a newly retrained live model because the PDF does not contain the original raw data or trained weights. I separated the project into three layers: thesis benchmarks, a reproducible ANFIS/VAE reference implementation, and a transparent live monitoring score. This keeps the demo technically useful while preserving model governance and avoiding unsupported claims.”

That explanation is stronger than claiming an unverifiable 97% live model accuracy.

---

## 11. External data references used by the live/fallback layer

- Yahoo Finance symbol: `^VNINDEX.VN` — best-effort public live adapter.
- Investing.com VN Index historical page — used only to cross-check the small embedded fallback snapshot.
- For a production implementation, use a licensed or official Vietnam market-data provider instead of a free public endpoint.

