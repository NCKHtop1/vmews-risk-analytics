#!/usr/bin/env python3
"""Audit every published HOSE forecast against the executable price grid.

The model is allowed to predict a continuous return internally. Published
central and interval prices, however, must be executable on the exchange grid.
This report also quantifies whether published moves have collapsed to a single
100-VND step across the market. It never alters forecast values.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def finite(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def tick_size(price: float, exchange: str = "HOSE") -> int:
    venue = str(exchange or "HOSE").upper()
    if venue in {"HNX", "UPCOM"}:
        return 100
    if price < 10_000:
        return 10
    if price < 50_000:
        return 50
    return 100


def valid_grid(price: float, exchange: str = "HOSE") -> bool:
    if not math.isfinite(price) or price <= 0:
        return False
    tick = tick_size(price, exchange)
    return abs(price / tick - round(price / tick)) < 1e-8


def band(price: float) -> str:
    if price < 10_000:
        return "LT_10K"
    if price < 50_000:
        return "10K_TO_LT_50K"
    return "GE_50K"


def audit(dashboard: dict[str, Any]) -> dict[str, Any]:
    invalid = []
    rows = []
    band_counts: dict[str, Counter] = defaultdict(Counter)
    fpt = None

    for symbol, snapshot in (dashboard.get("symbols") or {}).items():
        if snapshot.get("exchange") != "HOSE" or snapshot.get("dataFreshness") != "CURRENT":
            continue
        close = finite(snapshot.get("close"))
        if close is None or close <= 0:
            continue
        for horizon in range(1, 6):
            forecast = (snapshot.get("horizons") or {}).get(str(horizon)) or {}
            if forecast.get("priceValidated") is not True or forecast.get("validationStatus") != "PASS":
                continue
            target = finite(forecast.get("expectedPrice"))
            q20 = finite(forecast.get("q20Price"))
            q80 = finite(forecast.get("q80Price"))
            declared_tick = finite(forecast.get("tickSize"))
            if target is None:
                continue
            expected_tick = tick_size(target, "HOSE")
            issues = []
            if not valid_grid(target, "HOSE"):
                issues.append("expectedPrice off exchange grid")
            if q20 is not None and not valid_grid(q20, "HOSE"):
                issues.append("q20Price off exchange grid")
            if q80 is not None and not valid_grid(q80, "HOSE"):
                issues.append("q80Price off exchange grid")
            if declared_tick is not None and int(declared_tick) != expected_tick:
                issues.append(f"declared tick {declared_tick:g} != executable tick {expected_tick}")
            if issues:
                invalid.append({"symbol": symbol, "horizon": horizon, "issues": issues})

            move = target - close
            local_tick = max(tick_size(close, "HOSE"), tick_size(target, "HOSE"))
            move_ticks = abs(move) / local_tick if local_tick else None
            row = {
                "symbol": symbol,
                "horizon": horizon,
                "close": close,
                "target": target,
                "moveVND": move,
                "moveTicks": move_ticks,
                "tickSize": expected_tick,
                "priceBand": band(target),
            }
            rows.append(row)
            band_counts[row["priceBand"]][str(expected_tick)] += 1
            if symbol == "FPT" and horizon == 5:
                fpt = row

    tick_counts = Counter(str(row["tickSize"]) for row in rows)
    one_tick = [row for row in rows if row["moveTicks"] is not None and row["moveTicks"] <= 1.0000001]
    moves = [row["moveTicks"] for row in rows if row["moveTicks"] is not None]
    low_mid = [row for row in rows if row["target"] < 50_000]
    low_mid_100 = [row for row in low_mid if row["tickSize"] == 100]

    warnings = []
    if rows and len(one_tick) / len(rows) > 0.90:
        warnings.append("More than 90% of published validated forecasts move no more than one executable tick.")
    if low_mid and low_mid_100:
        warnings.append("At least one sub-50k HOSE target was assigned a 100-VND tick.")
    if rows and len(tick_counts) == 1 and "100" in tick_counts:
        warnings.append("Every validated forecast uses a 100-VND tick; investigate price-grid collapse.")

    status = "PASS" if not invalid and not low_mid_100 else "FAIL"
    return {
        "version": "VMEWS-PRICE-GRID-AUDIT-26.0",
        "status": status,
        "asOf": dashboard.get("asOf"),
        "validatedForecasts": len(rows),
        "invalidForecasts": len(invalid),
        "tickCounts": dict(sorted(tick_counts.items(), key=lambda item: int(item[0]))),
        "priceBandTickCounts": {key: dict(value) for key, value in sorted(band_counts.items())},
        "oneTickMoveShare": len(one_tick) / len(rows) if rows else None,
        "medianMoveTicks": median(moves) if moves else None,
        "sub50kForecasts": len(low_mid),
        "sub50kUsing100Tick": len(low_mid_100),
        "FPTT5": fpt,
        "warnings": warnings,
        "invalidExamples": invalid[:50],
        "governance": "Continuous model returns are preserved internally; only published price fields are snapped to the exchange-executable grid.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DATA / "forecast-dashboard-v12.json"))
    parser.add_argument("--output", default=str(DATA / "forecast-price-grid-audit-v26.json"))
    args = parser.parse_args()
    dashboard = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = audit(dashboard)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "validatedForecasts", "invalidForecasts", "tickCounts", "oneTickMoveShare", "medianMoveTicks", "FPTT5", "warnings")}, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
