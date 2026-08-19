"""Label-free structural sanity gate for fresh V12 current forecasts.

This gate never reads realized future labels and does not require forecasts to be large.
It catches implementation failures: NaN/Inf, broken log-return-to-price mapping, invalid
quantile order, missing horizons/validation, and obvious cross-sectional constant-value
collapse. Small but genuinely varying calibrated forecasts are allowed.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CURRENT = DATA / "forecast-current-v12.json"
MODEL = DATA / "forecast-model-v12.json"
OUT = DATA / "forecast-sanity-v12.json"
HORIZONS = ["1", "2", "3", "4", "5"]
REPRESENTATIVES = ["FPT", "VCB", "HPG"]


def finite_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def rel_close(a, b, *, rtol=2e-10, atol=1e-8):
    return abs(float(a) - float(b)) <= max(atol, rtol * max(1.0, abs(float(a)), abs(float(b))))


def quantile(values, q):
    xs = sorted(float(x) for x in values)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def main():
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    symbols = current.get("symbols") or {}
    promotion = model.get("promotion") or {}
    model_horizons = model.get("horizons") or {}
    failures = []
    per_h = {h: [] for h in HORIZONS}
    representative = {}

    if current.get("version") != "VMEWS-CURRENT-12.0.0":
        failures.append(f"unexpected_current_version:{current.get('version')}")
    if promotion.get("status") != "PASS":
        failures.append(f"model_promotion:{promotion.get('status')}")
    if [int(x) for x in promotion.get("directPriceHorizons") or []] != [1, 2, 3, 4, 5]:
        failures.append(f"direct_price_horizons:{promotion.get('directPriceHorizons')}")
    if len(symbols) < 300:
        failures.append(f"current_symbol_count:{len(symbols)}<300")

    for h in HORIZONS:
        mh = model_horizons.get(h) or {}
        if mh.get("priceStatus") != "PASS":
            failures.append(f"model_horizon_{h}_price_status:{mh.get('priceStatus')}")

    for symbol, item in sorted(symbols.items()):
        close = item.get("close")
        if not finite_number(close) or float(close) <= 0:
            failures.append(f"{symbol}:invalid_close")
            continue
        horizons = item.get("horizons") or {}
        if sorted(horizons.keys(), key=str) != HORIZONS:
            failures.append(f"{symbol}:horizons:{sorted(horizons.keys())}")
            continue
        for h in HORIZONS:
            z = horizons.get(h) or {}
            fields = ["expectedReturn", "expectedPrice", "q20", "q80", "q20Price", "q80Price", "alpha"]
            bad = [f for f in fields if not finite_number(z.get(f))]
            if bad:
                failures.append(f"{symbol}:T+{h}:nonfinite:{','.join(bad)}")
                continue
            r = float(z["expectedReturn"]); lo = float(z["q20"]); hi = float(z["q80"])
            ep = float(z["expectedPrice"]); lp = float(z["q20Price"]); hp = float(z["q80Price"])
            if not (lo <= r <= hi):
                failures.append(f"{symbol}:T+{h}:return_quantile_order")
            expected_ep = float(close) * math.exp(r)
            expected_lp = float(close) * math.exp(lo)
            expected_hp = float(close) * math.exp(hi)
            if not rel_close(ep, expected_ep):
                failures.append(f"{symbol}:T+{h}:expected_price_formula")
            if not rel_close(lp, expected_lp):
                failures.append(f"{symbol}:T+{h}:q20_price_formula")
            if not rel_close(hp, expected_hp):
                failures.append(f"{symbol}:T+{h}:q80_price_formula")
            if not (lp <= ep <= hp and lp > 0 and hp > 0):
                failures.append(f"{symbol}:T+{h}:price_quantile_order")
            if z.get("priceValidated") is not True or z.get("validationStatus") != "PASS":
                failures.append(f"{symbol}:T+{h}:price_not_validated")
            per_h[h].append(r)

    distribution = {}
    for h, vals in per_h.items():
        rounded = [round(x, 8) for x in vals]
        counts = Counter(rounded)
        mode_value, mode_count = counts.most_common(1)[0] if counts else (None, 0)
        stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        q10 = quantile(vals, .10); q50 = quantile(vals, .50); q90 = quantile(vals, .90)
        unique = len(counts)
        mode_share = mode_count / max(1, len(vals))
        # Only reject an obvious implementation collapse. This is deliberately scale-free:
        # legitimate 0.1% or 1% forecasts pass if they vary across the cross-section.
        collapse = (
            len(vals) < 300
            or unique < 3
            or stdev <= 1e-8
            or mode_share >= 0.95
        )
        if collapse:
            failures.append(
                f"T+{h}:technical_cross_section_collapse:n={len(vals)},unique={unique},std={stdev:.12g},modeShare={mode_share:.6f}"
            )
        distribution[h] = {
            "n": len(vals),
            "uniqueRounded1e8": unique,
            "modeRounded1e8": mode_value,
            "modeShare": mode_share,
            "std": stdev,
            "q10": q10,
            "median": q50,
            "q90": q90,
            "p90Abs": quantile([abs(x) for x in vals], .90),
            "technicalCollapse": collapse,
        }

    for symbol in REPRESENTATIVES:
        item = symbols.get(symbol)
        if not item:
            failures.append(f"representative_missing:{symbol}")
            continue
        representative[symbol] = {
            "date": item.get("date"),
            "close": item.get("close"),
            "horizons": {
                h: {
                    k: (item.get("horizons") or {}).get(h, {}).get(k)
                    for k in ["expectedReturn", "expectedPrice", "q20", "q80", "q20Price", "q80Price", "priceValidated", "directionValidated"]
                }
                for h in HORIZONS
            },
        }

    # Detect the old pathological shape where one calibrated constant is repeated across
    # nearly every stock AND every horizon, without imposing any minimum forecast magnitude.
    all_rounded = [round(v, 8) for vals in per_h.values() for v in vals]
    all_counts = Counter(all_rounded)
    global_mode, global_count = all_counts.most_common(1)[0] if all_counts else (None, 0)
    global_mode_share = global_count / max(1, len(all_rounded))
    if global_mode_share >= 0.90:
        failures.append(f"global_technical_collapse:mode={global_mode},share={global_mode_share:.6f}")

    out = {
        "version": "VMEWS-V12-FORECAST-SANITY-1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "labelFree": True,
        "sealedLabelsRead": 0,
        "futureOutcomesRead": 0,
        "minimumMagnitudeGate": False,
        "contract": "expectedPrice = current raw close * exp(calibrated conditional-median log return)",
        "symbolCount": len(symbols),
        "promotion": promotion,
        "distribution": distribution,
        "globalModeRounded1e8": global_mode,
        "globalModeShare": global_mode_share,
        "representatives": representative,
        "failures": failures[:500],
        "failureCount": len(failures),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(0 if out["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
