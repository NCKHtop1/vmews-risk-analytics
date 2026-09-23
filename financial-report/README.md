# FinQuery — Financial reports on GitHub/CDN

Open `index.html` (self-contained CDN build) or `frontend/index.html` through an HTML-capable CDN or any static server. jsDelivr delivers source files, not an HTML application host. No API key is sent to the browser.

The page lets users search the listed-company catalog, select individual years (including non-consecutive years), choose reports and download an actual `.xlsx`. Financial statements, financial ratios and available supplementary reports retain all returned line items. Years are columns. The workbook uses numeric cells, plain formatting, freeze panes, and has no comments or metadata sheet.

## Data

`backend/vnstock_connector.py` calls the public vnstock 4.0.4 finance methods. It respects the installed data entitlement (the community edition currently returns four periods). VCI annual statements and KBS ratios are normalized independently. Repeated/ambiguous year columns are rejected. Zero is distinct from missing; unavailable years are never synthesized. Each report's available years determine what can be selected.

The bundled release includes MBB, FPT, VCB, HPG, VNM, ACB, TCB, SSI and BVH datasets. `data/companies.json` is the broader listing catalog, not a claim that every company already has a report. The live `financial-report-data` branch expands coverage and retains valid snapshots when a provider is unavailable. The scheduled refresh runs every four hours, with a 45-minute budget (six minutes on code pushes); the next run continues uncollected companies. A company without a published dataset is shown as unavailable, never given invented date limits.

`verified/MBB.json` preserves the six-year dataset reconciled to MBB's audited consolidated reports. The reviewed figures have priority over inconsistent provider values. Provider trailing EPS in the ratios sheet is a different measure from the reported annual EPS in the income statement.

Automatic unrestricted web search/AI/OCR is not provided by a static CDN. The release does not claim to autonomously verify arbitrary PDF reports. Additional independently checked annual reports can be added to `verified/` using the same schema. vnstock-data premium notes require a separately licensed connector and are not part of the community package used here.

## Run and verify

```sh
python -m venv .venv
.venv/bin/pip install -r financial-report/requirements.txt
.venv/bin/python financial-report/tests/test_reports.py
python financial-report/scripts/build_cdn.py
python -m http.server 8080
# Open /financial-report/frontend/index.html
```

The Python engine also exports real XLSX bytes through `api/generate_report.py`. It is a callable Python module, not a claim of a deployed HTTP API. The production CDN app exports in the browser with no backend needed for downloads.

GitHub Actions: `financial-report-test.yml` validates every numeric cell in representative Excel exports. `financial-report-refresh.yml` publishes to the dedicated data branch; it never writes to unrelated forecast data or to main.
