#!/usr/bin/env python3
"""Publish a compact, complete VN100 product snapshot without changing backtest truth.

The full immutable backtest remains in finquery-vn100-forecast.json; the UI
only needs the latest observed per-symbol cases and chart history.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def make_product(source: dict, *, max_cases: int = 6) -> dict:
    if source.get("status") != "PASS":
        raise ValueError("Forecast source is not publishable")
    dashboard = source.get("dashboard") or {}
    symbols = dashboard.get("symbols") or {}
    charts = dashboard.get("charts") or {}
    if len(symbols) != 100 or set(symbols) != set(charts):
        raise ValueError("VN100 universe must contain 100 tickers and charts")
    cleaned = {}
    for symbol, row in symbols.items():
        horizons = row.get("horizons") or {}
        if set(horizons) != {"1", "2", "3", "4", "5"}:
            raise ValueError("Incomplete T+1 to T+5 for " + symbol)
        for h, prediction in horizons.items():
            if not prediction.get("priceValidated") or any(
                not math.isfinite(float(prediction.get(field) or 0)) or float(prediction.get(field) or 0) <= 0
                for field in ("expectedPrice", "q20Price", "q80Price")
            ):
                raise ValueError("Invalid forecast for " + symbol + " T+" + h)
        slim = {key: value for key, value in row.items() if key != "evidence"}
        # Events/news are refreshed independently; old dated evidence is not
        # carried into the new model snapshot and misrepresented as fresh.
        slim["evidence"] = {"recent": [], "decisionRecent": []}
        cleaned[symbol] = slim
        if len(charts[symbol]) < 8:
            raise ValueError("Insufficient chart points for " + symbol)
    audit = source.get("backtest") or {}
    recent_cases = {}
    for h in ("1", "2", "3", "4", "5"):
        rows = (audit.get("cases") or {}).get(h) or []
        by_symbol = {}
        for case in rows:
            sym = case.get("symbol")
            if sym in symbols:
                by_symbol.setdefault(sym, []).append(case)
        if set(by_symbol) != set(symbols):
            raise ValueError("Missing backtest cases for T+" + h)
        recent_cases[h] = [
            case for symbol in sorted(by_symbol)
            for case in by_symbol[symbol][-max_cases:]
        ]
    product = {
        "version": source.get("version"),
        "status": source.get("status"),
        "generatedAt": source.get("generatedAt"),
        "asOf": source.get("asOf"),
        "universe": source.get("universe"),
        "dashboard": {
            "asOf": dashboard.get("asOf"),
            "generatedAt": dashboard.get("generatedAt"),
            "forecastUpdatedAt": dashboard.get("forecastUpdatedAt") or source.get("generatedAt"),
            "forecastSessionDate": dashboard.get("forecastSessionDate"),
            "symbols": cleaned,
            "charts": {symbol: rows[-125:] for symbol, rows in charts.items()},
            "promotion": dashboard.get("promotion"),
        },
        "model": source.get("model"),
        "backtest": {"horizons": audit.get("horizons") or {}, "cases": recent_cases},
        "gates": source.get("gates"),
    }
    return product


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--status", required=True, type=Path)
    args = parser.parse_args()
    full_bytes = args.input.read_bytes()
    source = json.loads(full_bytes)
    product = make_product(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    data = json.dumps(product, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    temp.write_text(data, encoding="utf-8")
    temp.replace(args.output)
    status = {
        "status": "PASS",
        "generatedAt": product["generatedAt"],
        "asOf": product["asOf"],
        "sourceSha256": hashlib.sha256(full_bytes).hexdigest(),
        "productBytes": len(data.encode("utf-8")),
        "symbols": len(product["dashboard"]["symbols"]),
        "horizons": sum(len(s["horizons"]) for s in product["dashboard"]["symbols"].values()),
        "backtestCases": {h: len(rows) for h, rows in product["backtest"]["cases"].items()},
        "freshHistory": (product["universe"] or {}).get("freshHistory"),
        "activeQuotes": (product["universe"] or {}).get("activeQuotes"),
        "fallbackQuotes": (product["universe"] or {}).get("fallbackQuotes"),
        "quoteStatus": (product["universe"] or {}).get("quoteStatus"),
        "inputMode": (product["universe"] or {}).get("inputMode"),
        "latestVerifiedQuoteAt": (product["universe"] or {}).get("latestVerifiedQuoteAt"),
        "forecastSessionDate": (product["dashboard"] or {}).get("forecastSessionDate"),
        "forecastRunEveryMinutes": 30,
        "marketQuoteDisplayEveryMinutes": 5,
    }
    args.status.write_text(json.dumps(status, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
