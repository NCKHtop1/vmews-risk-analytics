# Archived forecast model boundary (30 October 2026)

FinQuery production forecasts use only the separately published, validated `finquery-vn100-data/data/finquery-vn100-{product,forecast,status}.json` package and independently timestamped `financial-market-data/market/quotes.json`.

The retired V12/V13/V20 core and V21 session overlay are preserved on GitHub branch `archive/forecast-core-frozen-20261020`, pinned to commit `e84dcdea3637772cee2d6d875666a247ea3000a5`. This snapshot is a research/evidence archive, not a live forecast source. It must not be republished into `main/data`, bundled on the FinQuery site, or used to enrich VN100 with stale news, flow, research, or corporate context.

The standalone SoluTION.AI product has a separate `solution-ai-core-data` data branch. Its research pipeline may restore the pinned seed into an ephemeral worker. Any independent core publication must still pass the unchanged sealed walk-forward gates; archived forecasts cannot silently be promoted.

Preventive gates:
- The `finquery-retired-forecast-quarantine.yml` workflow checks that main contains no retired forecast artifacts or writer workflows and that the archive ref is unchanged.
- `system_contract_audit.py` enforces this isolation on each operations audit.
- The VN100 builder takes issuer names only from `financial-report/data/companies.json` and prices from current verified market and certified last-good VN100 histories.
- The FinQuery frontend refuses direct legacy core asset loads. An old standalone V21 overlay is only available on the isolated standalone core branch.

If historical backtests are required, read the pinned archive branch by explicit reference. Never restore old assets into a deployed production tree.
