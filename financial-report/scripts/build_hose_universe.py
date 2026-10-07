#!/usr/bin/env python3
"""Build the tiered HOSE universe used by FinQuery market intelligence.

The financial-report module remains the verified VN100 Core.  The market layer
adds liquid HOSE names that pass objective liquidity/data gates, while every
remaining current HOSE symbol stays in Discovery for EOD technical screening.

This file deliberately does not change the forecast model itself.  Forecasts
are already produced market-wide; this layer controls which symbols are
promoted for live market/scanner use and which remain discovery-only.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from refresh_market import technical_scan_symbol  # noqa:E402

REPO = Path(__file__).resolve().parents[2]
FINANCIAL = REPO / "financial-report"
DEFAULT_OUTPUT = FINANCIAL / "data" / "universe.json"
VN_TZ = timezone(timedelta(hours=7))

MIN_MEDIAN_TURNOVER_20 = float(os.environ.get("FINQUERY_LIQUID_MIN_MEDIAN_VALUE_20", "10000000000"))
MIN_ACTIVE_20 = int(os.environ.get("FINQUERY_LIQUID_MIN_ACTIVE_20", "18"))
MIN_HISTORY = int(os.environ.get("FINQUERY_LIQUID_MIN_HISTORY", "61"))
MAX_LIQUID_EXTRA = int(os.environ.get("FINQUERY_LIQUID_MAX_EXTRA", "120"))
DISCOVERY_MIN_HISTORY = int(os.environ.get("FINQUERY_DISCOVERY_MIN_HISTORY", "35"))
DISCOVERY_MIN_ACTIVE_20 = int(os.environ.get("FINQUERY_DISCOVERY_MIN_ACTIVE_20", "10"))
SEED_BAR_COUNT = int(os.environ.get("FINQUERY_UNIVERSE_SEED_BARS", "180"))


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def normalize_bars(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        day = str(row.get("time") or row.get("date") or "")[:10]
        close = number(row.get("rawClose"))
        if close is None:
            close = number(row.get("close"))
        volume = number(row.get("volume"))
        if len(day) != 10 or close is None or close <= 0 or volume is None or volume < 0:
            continue
        open_ = number(row.get("open")) or close
        high = number(row.get("high")) or max(open_, close)
        low = number(row.get("low")) or min(open_, close)
        merged[day] = {
            "time": day,
            "open": open_,
            "high": max(high, open_, close),
            "low": min(low, open_, close),
            "close": close,
            "volume": volume,
        }
    return [merged[key] for key in sorted(merged)]


def liquidity_metrics(bars: list[dict[str, Any]]) -> dict[str, Any]:
    window = bars[-20:]
    turnovers = [float(row["close"]) * float(row["volume"]) for row in window]
    active = sum(float(row["volume"]) > 0 for row in window)
    median_turnover = statistics.median(turnovers) if turnovers else 0.0
    average_turnover = statistics.fmean(turnovers) if turnovers else 0.0
    return {
        "historyBars": len(bars),
        "activeSessions20": active,
        "observedSessions20": len(window),
        "medianTurnover20": round(median_turnover),
        "averageTurnover20": round(average_turnover),
        "latestDate": bars[-1]["time"] if bars else None,
    }


def build_universe(
    core_companies: list[dict[str, Any]],
    current_hose: set[str],
    histories: dict[str, list[dict[str, Any]]],
    dashboard: dict[str, Any] | None = None,
    live_history_symbols: set[str] | None = None,
) -> dict[str, Any]:
    dashboard = dashboard or {}
    live_history_symbols = (
        None if live_history_symbols is None
        else {str(symbol).upper() for symbol in live_history_symbols if str(symbol).strip()}
    )
    core_by_symbol = {
        str(row.get("symbol") or "").upper(): row
        for row in core_companies
        if str(row.get("symbol") or "").strip()
    }
    core_symbols = set(core_by_symbol)
    charts = dashboard.get("charts") or {}
    snapshots = dashboard.get("symbols") or {}
    # Market freshness is derived from market history, never from the forecast
    # dashboard clock. Forecast data may lag without freezing the market universe.
    market_dates = []
    completed_candidates = []
    local_now = datetime.now(VN_TZ)
    today = local_now.date().isoformat()
    before_eod_lock = local_now.weekday() < 5 and (local_now.hour * 60 + local_now.minute) < (15 * 60 + 20)
    for rows in histories.values():
        normalized = normalize_bars(rows)
        if normalized:
            market_dates.append(normalized[-1]["time"])
            completed_candidates.extend(row["time"] for row in normalized[-3:] if row["time"] < today)
    as_of = max(market_dates) if market_dates else (str(dashboard.get("asOf") or "")[:10] or None)
    if before_eod_lock and as_of == today:
        eod_as_of = max(completed_candidates) if completed_candidates else None
    else:
        eod_as_of = as_of
    symbols = sorted({str(x).upper() for x in current_hose if str(x).strip()} | core_symbols)

    prepared: dict[str, dict[str, Any]] = {}
    candidate_liquid: list[tuple[float, str]] = []

    for symbol in symbols:
        chart_rows = charts.get(symbol) if isinstance(charts, dict) else None
        chart_bars = normalize_bars(chart_rows)
        history_bars = normalize_bars(histories.get(symbol))
        # Always prefer the fresher market history. Forecast charts are only a
        # fallback when they are at least as current, never a freshness clock.
        chart_last = chart_bars[-1]["time"] if chart_bars else ""
        history_last = history_bars[-1]["time"] if history_bars else ""
        if history_last > chart_last or (history_last == chart_last and len(history_bars) >= len(chart_bars)):
            bars = history_bars
        else:
            bars = chart_bars
        metrics = liquidity_metrics(bars)
        fresh = bool(metrics["latestDate"]) and (not as_of or metrics["latestDate"] == as_of)
        data_sufficient = (
            metrics["historyBars"] >= MIN_HISTORY
            and metrics["activeSessions20"] >= MIN_ACTIVE_20
            and metrics["observedSessions20"] >= min(20, MIN_ACTIVE_20)
        )
        market_history_backed = live_history_symbols is None or symbol in live_history_symbols
        liquid_gate = (
            symbol not in core_symbols
            and market_history_backed
            and fresh
            and data_sufficient
            and metrics["medianTurnover20"] >= MIN_MEDIAN_TURNOVER_20
        )
        if liquid_gate:
            candidate_liquid.append((metrics["medianTurnover20"], symbol))
        snapshot = snapshots.get(symbol) if isinstance(snapshots, dict) else {}
        name = (
            (core_by_symbol.get(symbol) or {}).get("name")
            or (snapshot or {}).get("name")
            or (snapshot or {}).get("companyName")
            or symbol
        )
        prepared[symbol] = {
            "symbol": symbol,
            "name": name,
            "exchange": "HOSE",
            "coreMember": symbol in core_symbols,
            "fresh": fresh,
            "dataSufficient": data_sufficient,
            "marketHistoryBacked": market_history_backed,
            **metrics,
            "_bars": bars,
        }

    candidate_liquid.sort(key=lambda item: (-item[0], item[1]))
    liquid_symbols = {symbol for _, symbol in candidate_liquid[:MAX_LIQUID_EXTRA]}

    public_symbols: dict[str, dict[str, Any]] = {}
    discovery_technical: dict[str, dict[str, Any]] = {}
    live_market_symbols: list[str] = []
    scanner_symbols: list[str] = []
    scanner_current_symbols: list[str] = []
    forecast_eligible_symbols: list[str] = []

    for symbol in symbols:
        raw = prepared[symbol]
        bars = raw.pop("_bars")
        if symbol in core_symbols:
            tier = "CORE"
        elif symbol in liquid_symbols:
            tier = "LIQUID"
        else:
            tier = "DISCOVERY"

        scanner_eligible = (
            raw["historyBars"] >= DISCOVERY_MIN_HISTORY
            and raw["activeSessions20"] >= DISCOVERY_MIN_ACTIVE_20
            and bool(raw["latestDate"])
        )
        live_market_eligible = tier in {"CORE", "LIQUID"} and raw["marketHistoryBacked"]
        scanner_fresh = bool(
            scanner_eligible
            and (
                (live_market_eligible and raw["fresh"])
                or (
                    tier == "DISCOVERY"
                    and raw["marketHistoryBacked"]
                    and eod_as_of
                    and raw["latestDate"] == eod_as_of
                )
            )
        )
        forecast_eligible = (
            live_market_eligible
            and raw["fresh"]
            and raw["dataSufficient"]
        )

        row = {
            **raw,
            "tier": tier,
            "liveMarketEligible": live_market_eligible,
            "scannerEligible": scanner_eligible,
            "scannerFresh": scanner_fresh,
            "forecastEligible": forecast_eligible,
            "liquidityGatePassed": symbol in liquid_symbols,
        }

        if tier == "LIQUID" or (tier == "DISCOVERY" and scanner_eligible and not raw["marketHistoryBacked"]):
            row["seedBars"] = bars[-SEED_BAR_COUNT:]

        if tier == "DISCOVERY" and scanner_eligible:
            technical = technical_scan_symbol(symbol, bars)
            if technical:
                discovery_technical[symbol] = {
                    **technical,
                    "tier": "DISCOVERY",
                    "cadence": "EOD",
                    "sourceTime": None,
                    "snapshotFresh": scanner_fresh,
                }

        public_symbols[symbol] = row
        if live_market_eligible:
            live_market_symbols.append(symbol)
        if scanner_eligible:
            scanner_symbols.append(symbol)
        if scanner_fresh:
            scanner_current_symbols.append(symbol)
        if forecast_eligible:
            forecast_eligible_symbols.append(symbol)

    counts = {
        "listedHOSE": len(symbols),
        "core": sum(row["tier"] == "CORE" for row in public_symbols.values()),
        "liquid": sum(row["tier"] == "LIQUID" for row in public_symbols.values()),
        "discovery": sum(row["tier"] == "DISCOVERY" for row in public_symbols.values()),
        "liveMarket": len(live_market_symbols),
        "scannerEligible": len(scanner_symbols),
        "scannerCurrent": len(scanner_current_symbols),
        "forecastEligible": len(forecast_eligible_symbols),
        "discoveryTechnical": len(discovery_technical),
    }
    return {
        "version": "FINQUERY-HOSE-UNIVERSE-1.0",
        "generatedAt": datetime.now(VN_TZ).isoformat(timespec="seconds"),
        "asOf": as_of,
        "eodAsOf": eod_as_of,
        "policy": {
            "core": "Verified VN100 financial-report universe; membership is retained independently of liquidity.",
            "liquid": "Non-core HOSE symbols promoted by objective 20-session turnover, trading activity and history gates.",
            "discovery": "Remaining current HOSE symbols; EOD technical discovery is active only when its published market history matches eodAsOf.",
            "medianTurnover20MinVND": int(MIN_MEDIAN_TURNOVER_20),
            "activeSessions20Min": MIN_ACTIVE_20,
            "historyBarsMin": MIN_HISTORY,
            "liquidExtraCap": MAX_LIQUID_EXTRA,
            "discoveryHistoryBarsMin": DISCOVERY_MIN_HISTORY,
            "discoveryActiveSessions20Min": DISCOVERY_MIN_ACTIVE_20,
            "promotion": "Dynamic from current HOSE membership and published market-history liquidity/data gates; independent of forecast freshness. Forecast/frozen history cannot promote a symbol into the live tier.",
        },
        "counts": counts,
        "liveMarketSymbols": sorted(live_market_symbols),
        "scannerSymbols": sorted(scanner_symbols),
        "scannerCurrentSymbols": sorted(scanner_current_symbols),
        "forecastEligibleSymbols": sorted(forecast_eligible_symbols),
        "discoveryTechnical": discovery_technical,
        "symbols": public_symbols,
    }


def load_inputs() -> tuple[list[dict[str, Any]], set[str], dict[str, list[dict[str, Any]]], dict[str, Any], set[str] | None]:
    core = json.loads((FINANCIAL / "data" / "companies.json").read_text(encoding="utf-8"))
    dashboard_path = REPO / "data" / "forecast-dashboard-v12.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8")) if dashboard_path.exists() else {}
    frozen_path = REPO / "data" / "v12-frozen-source.json.gz"
    with gzip.open(frozen_path, "rt", encoding="utf-8") as stream:
        frozen = json.load(stream)
    current_hose = {str(symbol).upper() for symbol in frozen.get("currentHOSESymbols", [])}
    histories = {
        str(symbol).upper(): rows
        for symbol, rows in (frozen.get("histories") or {}).items()
        if isinstance(rows, list)
    }
    market_dir_raw = os.environ.get("FINQUERY_MARKET_DIR")
    market_dir = Path(market_dir_raw) if market_dir_raw else None
    market_history_symbols: set[str] | None = None
    if market_dir and market_dir.exists():
        market_history_symbols = set()
        read_json = {}
        universe_path = market_dir / "universe.json"
        if universe_path.exists():
            try:
                read_json = json.loads(universe_path.read_text(encoding="utf-8"))
                published_symbols = set((read_json.get("symbols") or {}).keys())
                if published_symbols:
                    current_hose = {str(x).upper() for x in published_symbols}
            except (OSError, ValueError, TypeError):
                pass
        history_dir = market_dir / "history"
        if history_dir.exists():
            for symbol in current_hose:
                file = history_dir / f"{symbol}.json"
                if not file.exists():
                    continue
                try:
                    row = json.loads(file.read_text(encoding="utf-8"))
                    bars = row.get("bars") or []
                    if bars:
                        histories[symbol] = bars
                        market_history_symbols.add(symbol)
                except (OSError, ValueError, TypeError):
                    continue
    return core, current_hose, histories, dashboard, market_history_symbols


def main() -> None:
    core, current_hose, histories, dashboard, market_history_symbols = load_inputs()
    universe = build_universe(
        core, current_hose, histories, dashboard,
        live_history_symbols=market_history_symbols,
    )
    output = Path(os.environ.get("FINQUERY_UNIVERSE_OUTPUT", str(DEFAULT_OUTPUT)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(universe, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "output": str(output),
        "asOf": universe.get("asOf"),
        **universe.get("counts", {}),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
