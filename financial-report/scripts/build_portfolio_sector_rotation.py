#!/usr/bin/env python3
"""Build an explainable 5/20-session SECTOR RELATIVE STRENGTH snapshot.

This is NOT JdK RRG. Comparator: median contemporaneous returns across the
same fixed eligible HOSE cohort. Cohort is point-in-time *as of current*
and MUST NOT be used for historical point-in-time backtests or as a VNINDEX proxy.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from statistics import median


def numeric(value):
    try:
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    except (ValueError, TypeError):
        return None


def returns(series, trading_dates, offset, horizon):
    try:
        after = numeric(series.get(trading_dates[offset]))
        before = numeric(series.get(trading_dates[offset + horizon]))
    except (IndexError, TypeError):
        return None
    if not after or not before:
        return None
    r = after / before - 1
    return r if math.isfinite(r) and -1 < r < 30 else None


def rel_pct(period_return, benchmark_return):
    if period_return is None or benchmark_return is None or benchmark_return <= -1:
        return None
    return round(100 * ((1 + period_return) / (1 + benchmark_return) - 1), 3)


def build(market_dir):
    market_dir = Path(market_dir)
    risk = json.loads((market_dir / "risk-monitor.json").read_text(encoding="utf-8"))
    source_day = str(risk.get("sourceDate", ""))
    date.fromisoformat(source_day)
    sectors = risk.get("sectors")
    if not isinstance(sectors, list) or not sectors:
        raise ValueError("Missing sector membership snapshot")

    sector_members = {}
    all_symbols = set()
    for s in sectors:
        members = sorted({str(row.get("symbol") or "").strip().upper() for row in s.get("memberRows", [])
                          if isinstance(row, dict) and str(row.get("symbol") or "").isalnum() and 2 <= len(str(row.get("symbol") or "")) <= 12})
        if members:
            sector_members[str(s["id"])] = (str(s.get("label", s["id"])), members)
            all_symbols.update(members)

    series_by_symbol = {}
    calendar_count = Counter()
    for symbol in sorted(all_symbols):
        f = market_dir / "history" / f"{symbol}.json"
        if not f.is_file():
            continue
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
            bars = blob.get("bars", [])
            if blob.get("interval") != "1D" or not isinstance(bars, list):
                continue
            series = {}
            for row in bars[-90:]:
                d = str(row.get("time", ""))
                if len(d) == 10 and d <= source_day:
                    p = numeric(row.get("close"))
                    if p is not None:
                        series[d] = p
            if source_day not in series:
                continue
            series_by_symbol[symbol] = series
            calendar_count.update(series.keys())
        except (ValueError, TypeError, OSError):
            continue

    # Majority-attended calendar excludes suspended stocks and noisy one-off timestamps.
    threshold = max(2, math.ceil(len(series_by_symbol) * 0.5))
    dates = sorted((d for d, n in calendar_count.items() if n >= threshold and d <= source_day), reverse=True)
    if len(dates) < 26 or dates[0] != source_day:
        raise ValueError("At least 26 aligned trading sessions required")

    offsets = list(range(5, -1, -1))
    eligible = {
        symbol: series for symbol, series in series_by_symbol.items()
        if all(returns(series, dates, offset, n) is not None for offset in offsets for n in (5, 20))
    }
    if len(eligible) < 10:
        raise ValueError("Insufficient common cohort (<10) to calculate sector relative strength")

    benchmark = {}
    for offset in offsets:
        benchmark[offset] = {
            n: median(returns(series, dates, offset, n) for series in eligible.values())
            for n in (5, 20)
        }

    output_sectors = []
    output_stocks = {}
    for sid, (label, members) in sector_members.items():
        active = [s for s in members if s in eligible]
        coverage = len(active) / len(members) if members else 0
        record = {
            "id": sid, "label": label, "members": len(members),
            "used": len(active), "coveragePct": round(coverage * 100, 1),
            "status": "sufficient" if len(active) >= 3 and coverage >= .65 else "thin",
            "rs5": None, "rs20": None, "trail": []
        }
        if len(active) >= 2:
            for offset in offsets:
                r5 = median(returns(eligible[s], dates, offset, 5) for s in active)
                r20 = median(returns(eligible[s], dates, offset, 20) for s in active)
                point = {
                    "date": dates[offset],
                    "rs5": rel_pct(r5, benchmark[offset][5]),
                    "rs20": rel_pct(r20, benchmark[offset][20])
                }
                record["trail"].append(point)
            record["rs5"] = record["trail"][-1]["rs5"]
            record["rs20"] = record["trail"][-1]["rs20"]
        output_sectors.append(record)
        order = sorted(active, key=lambda s: returns(eligible[s], dates, 0, 20), reverse=True)
        for index, symbol in enumerate(order):
            output_stocks[symbol] = {
                "sectorId": sid, "rankWithinSector": index + 1, "sectorCount": len(order),
                "rs5": rel_pct(returns(eligible[symbol], dates, 0, 5), benchmark[0][5]),
                "rs20": rel_pct(returns(eligible[symbol], dates, 0, 20), benchmark[0][20])
            }
    output_sectors.sort(key=lambda x: (x["rs20"] is None, -(x["rs20"] or 0)))
    result = {
        "version": "FINQUERY-SECTOR-RS-1.0",
        "method": "median-sector-return-over-fixed-median-HOSE-cohort",
        "note": "Not JdK RRG; not VNINDEX; not a predictive signal or a historical point-in-time universe.",
        "sourceDate": source_day,
        "sourceTime": risk.get("sourceTime"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "label": "Trung vị nhóm HOSE đủ chuỗi",
            "eligibleSymbols": len(eligible), "rsReference5Pct": round(benchmark[0][5] * 100, 3),
            "rsReference20Pct": round(benchmark[0][20] * 100, 3),
            "fixedCohort": True
        },
        "sectors": output_sectors, "stocks": output_stocks
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    data = build(args.market)
    target = Path(args.output or (Path(args.market) / "sector-rotation.json"))
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"PORTFOLIO SECTOR RS: {len(data['stocks'])} stocks, {len(data['sectors'])} sectors, "
          f"benchmark cohort {data['benchmark']['eligibleSymbols']}, as-of {data['sourceDate']}")


if __name__ == "__main__":
    main()
