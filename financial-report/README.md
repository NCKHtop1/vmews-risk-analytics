# FinQuery — VN100 financial reports

Open `index.html` through an HTML-capable CDN or static server. The self-contained build includes a VN100 catalog and fallback snapshots for VIC, MBB, FPT and VCB. It always tries the live `financial-report-data` branch first, independently of catalog loading. The footer shows the age of the selected company's data; an offline snapshot is labelled “Bản đã lưu”. No API key goes to the browser. jsDelivr serves source files but does not host this HTML application.

Users choose a VN100 company, **year or quarter**, individual non-consecutive periods, and reports. “Mới nhất” selects the latest period actually returned by the source for all selected reports. Missing periods remain disabled, including future unpublished quarters. There is no hard-coded final year. Fiscal reporting-period labels follow the provider. Membership comes from the public `Listing(source='VCI').symbols_by_group('VN100')` call, validated as exactly 100 unique symbols; a failed membership refresh retains the last valid list.

Downloads are real `.xlsx` files with detailed indicators as rows and selected periods as columns. Numeric cells remain numeric; missing values stay blank and zero stays zero. Formatting is plain, panes freeze at B5, long labels wrap, and there are no comments or metadata sheets. The BCTC and Chi_so sheets group the selected reports.

## Data and continuous updates

The connector uses public **vnstock 4.0.8** Finance methods, VCI statements and KBS ratios/fallback statements. It respects rate limits and data entitlements. The current unauthenticated edition returns four recent periods per report; older periods already collected are retained in the archive. The UI exposes actual company/report coverage, not an assumed range. MBB also retains the independently reviewed 2020–2025 annual dataset.

GitHub Actions starts a refresh every four hours. One paced worker rotates across VN100 in order of oldest attempt, with a 100-minute budget and published checkpoints every five companies. Failed companies go to the back of the queue and do not block other members. Quarterly reports are checked each sweep; annual reports are checked at least daily. `checkedAt` is distinct from `updatedAt`: a failed fetch keeps the last successful timestamp and figures. This is scheduled collection of provider publications, not a promise of real-time issuer filing availability. GitHub scheduling and provider publication can lag.

The data branch contains `manifest.json` with separate annual and quarterly coverage, `universe.json`, per-company datasets, and refresh status. Only that branch is written by the publisher. It does not change unrelated forecasts or the main branch. A valid cached report is retained if a provider is unavailable. The next sweep rechecks retained reports and adds new periods automatically.

## Periods and ratios

Canonical quarter keys are `YYYY-Q1` to `YYYY-Q4`, distinct from annual keys. VCI quarterly cash-flow values represent individual quarters. KBS fallback cash flow is labelled year-to-date; datasets with differing bases are not merged. Report dates with duplicate provider suffixes are excluded instead of choosing an arbitrary value. VCI ratios currently expose stale 2018 periods and repeated year labels, so they are not used as current ratios.

All usable KBS ratio rows are retained under **Chỉ số từ nguồn** with their original units, including valuation, profitability, growth, liquidity, debt and cash-flow measures. Banks have sector-specific indicators such as NIM, CIR and LDR. These source ratios can differ from calculations on the VCI consolidated statements; their exact inputs and calculation dates are not independently certified.

**Chỉ số tính từ BCTC** adds up to 14 transparent measures computed from the actual displayed statements. Definitions live in `config/derived_metrics.json`; Python and browser calculations share those definitions. They cover margins, liabilities/assets, equity/assets, period ROA/ROE, operating cash-flow coverage, current/cash ratios, same-period growth, and operating cash after fixed-asset purchases. ROA/ROE use average opening/closing balances and are explicitly not annualized. Missing opening balances, missing comparison periods and non-positive denominators produce blanks. Quarterly flow ratios are not calculated by dividing cumulative cash flow by single-quarter income. Source ratios are preserved separately and are never silently overwritten by a different formula.

There is no unrestricted AI search/OCR service behind the static CDN. Provider fallback is automatic; arbitrary issuer PDF extraction requires a separately verified mapping. Premium-only supplementary notes are not claimed as part of the community package.

## Verification

`tests/test_reports.py` covers reviewed MBB annual figures, units, cash flow, missing periods and numeric Excel exports. `tests/test_quarters.py` covers VIC Q2/2026 against the reviewed consolidated H1 filing, distinct year/quarter axes, source-date ambiguities, VN100 membership, fair refresh ordering, formula boundaries and every exported value in browser/Python quarterly workbooks.

VIC controls were checked against the **reviewed** filing approved 29 August 2026, not the earlier unreviewed filing: [issuer report page](https://vingroup.net/quan-he-co-dong/bao-cao-tai-chinh/2026). PDF printed pages 6–13 show total assets of 1,309,346,482 million VND and ending cash of 76,396,702 million VND at 30 June 2026. The sum of the two source quarters reconciles to the reviewed H1 revenue, profit and cash-flow totals. This is a targeted independent check, not an audit of every cell for every issuer.

```sh
pip install -r financial-report/requirements.txt
python -m unittest discover -s financial-report/tests -v
python financial-report/scripts/build_cdn.py
python -m http.server 8080
```

`api/generate_report.py` is a callable Python module returning XLSX bytes, not a deployed HTTP service. Examples: `generate_report('VIC', years=[2023, 2025])` or `generate_report('VIC', period_type='quarter', periods=['2026-Q1','2026-Q2'])`. The live website creates downloads in the browser and needs no download server.
