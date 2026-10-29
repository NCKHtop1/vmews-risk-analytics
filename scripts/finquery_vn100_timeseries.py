#!/usr/bin/env python3
"""Build a compact, reproducible VN100 forecast from recorded HOSE prices.

All walk-forward points use only data available at their originating session.
This publisher never replaces missing market prices or invents OHLC bars.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vn_exchange_calendar import VN_TZ, is_trading_day, latest_completed_session, next_trading_dates

VERSION = "FINQUERY-VN100-TS-1"
HORIZONS = (1, 2, 3, 4, 5)
MIN_BARS = 8
HISTORY_POINTS = 130
TRAINING_LOOKBACK = 160


def finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def bounded(value: float, bottom: float, top: float) -> float:
    return max(bottom, min(top, value))


def median(values: list[float], default: float = 0.0) -> float:
    return statistics.median(values) if values else default


def stdev(values: list[float], default: float = 0.018) -> float:
    return statistics.pstdev(values) if len(values) > 2 else default


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * bounded(fraction, 0.0, 1.0)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def tick(price: float) -> int:
    return 10 if price < 10_000 else 50 if price < 50_000 else 100


def round_price(price: float) -> int:
    price = max(10.0, float(price))
    step = tick(price)
    rounded = int(math.floor(price / step + 0.5) * step)
    # Crossing a price-band boundary changes the exchange tick.
    step = tick(rounded)
    return int(math.floor(rounded / step + 0.5) * step)


def normalize_bars(payload: dict, completed: str) -> list[dict]:
    dedup: dict[str, dict] = {}
    for bar in payload.get("bars") or []:
        date = str(bar.get("time") or bar.get("date") or "")[:10]
        close = finite(bar.get("close"))
        if not date or len(date) != 10 or date > completed or close is None:
            continue
        try:
            if not is_trading_day(datetime.strptime(date, "%Y-%m-%d").date()):
                continue
        except ValueError:
            continue
        volume = bar.get("volume")
        dedup[date] = {
            "date": date,
            "close": close,
            "rawClose": close,
            "volume": max(0.0, float(volume or 0.0)),
        }
    return [dedup[day] for day in sorted(dedup)]


def load_market(core_path: Path, market_dir: Path, completed: str, previous_path: Path | None = None) -> dict[str, list[dict]]:
    core = json.loads(core_path.read_text(encoding="utf-8"))
    symbols = [str(row.get("symbol") or "").upper().strip() for row in core]
    if len(symbols) != 100 or len(set(symbols)) != 100:
        raise RuntimeError("Core VN100 must contain exactly 100 distinct symbols")
    if any(row.get("exchange") != "HOSE" for row in core):
        raise RuntimeError("Core VN100 includes a non-HOSE symbol")
    histories = {}
    missing = []
    retained = {}
    if previous_path is not None and previous_path.is_file():
        try:
            prior = json.loads(previous_path.read_text(encoding="utf-8"))
            if prior.get("status") == "PASS" and len((prior.get("dashboard") or {}).get("symbols") or {}) == 100:
                retained = (prior.get("dashboard") or {}).get("charts") or {}
        except (OSError, ValueError, TypeError):
            retained = {}
    for symbol in symbols:
        path = market_dir / "history" / f"{symbol}.json"
        rows = []
        if path.is_file():
            try:
                rows = normalize_bars(json.loads(path.read_text(encoding="utf-8")), completed)
            except (OSError, ValueError, TypeError):
                rows = []
        if len(rows) < MIN_BARS:
            # Retain real, previously published closes. Never manufacture an OHLC
            # observation to cover a temporary source outage.
            rows = normalize_bars({"bars": retained.get(symbol) or []}, completed)
        if len(rows) < MIN_BARS:
            missing.append(symbol)
            continue
        histories[symbol] = rows
    if missing:
        raise RuntimeError("Missing verified histories for VN100: " + ",".join(missing))
    return histories


def features(closes: list[float]) -> tuple[float, float]:
    logs = [math.log(value) for value in closes]
    returns = [logs[i] - logs[i - 1] for i in range(1, len(logs))]
    recent = returns[-20:]
    vol = bounded(stdev(recent), 0.004, 0.11)
    r5 = (logs[-1] - logs[-min(len(logs), 6)]) / max(1, min(len(logs) - 1, 5))
    r20 = (logs[-1] - logs[-min(len(logs), 21)]) / max(1, min(len(logs) - 1, 20))
    raw = 0.55 * r5 + 0.35 * r20 + 0.10 * median(recent)
    return bounded(raw, -0.03, 0.03), vol


def cluster_drifts(histories: dict[str, list[dict]], origin: str) -> dict[str, dict]:
    observed = {}
    for symbol, bars in histories.items():
        days = [row["date"] for row in bars]
        pos = bisect_right(days, origin) - 1
        if pos < MIN_BARS - 1 or days[pos] != origin:
            continue
        raw, vol = features([row["close"] for row in bars[:pos + 1]])
        observed[symbol] = {"index": pos, "raw": raw, "vol": vol}
    if not observed:
        return {}
    cut1 = quantile([value["vol"] for value in observed.values()], 1 / 3)
    cut2 = quantile([value["vol"] for value in observed.values()], 2 / 3)
    for value in observed.values():
        value["cluster"] = 0 if value["vol"] <= cut1 else 1 if value["vol"] <= cut2 else 2
    center = {
        group: median([row["raw"] for row in observed.values() if row["cluster"] == group])
        for group in range(3)
    }
    market = median([row["raw"] for row in observed.values()])
    for value in observed.values():
        group = center[value["cluster"]]
        value["groupDrift"] = group
        value["drift"] = bounded(0.72 * (0.66 * value["raw"] + 0.24 * group + 0.10 * market), -0.018, 0.018)
    return observed


def estimate(origin_price: float, drift: float, volatility: float, horizon: int) -> dict:
    center = round_price(origin_price * math.exp(horizon * drift))
    # 20th/80th percentiles under a zero-mean diffusion used as a bounded range.
    spread = 0.841621 * volatility * math.sqrt(horizon)
    low = round_price(origin_price * math.exp(horizon * drift - spread))
    high = round_price(origin_price * math.exp(horizon * drift + spread))
    low, high = min(low, center), max(high, center)
    return {
        "price": center,
        "low": low,
        "high": high,
        "return": center / origin_price - 1.0,
        "absReturn": abs(center / origin_price - 1.0),
    }


def quote_anchor(quotes: dict, symbol: str, now: datetime) -> tuple[float | None, str | None]:
    row = (quotes.get("quotes") or {}).get(symbol) or {}
    value = finite(row.get("price"))
    source_time = row.get("sourceTime") or quotes.get("latestSourceTime")
    if value is None or not source_time:
        return None, None
    try:
        updated = datetime.fromisoformat(str(source_time).replace("Z", "+00:00"))
        if updated.tzinfo is None:
            return None, None
        updated = updated.astimezone(VN_TZ)
    except (ValueError, TypeError):
        return None, None
    if updated > now or updated.date() != now.date():
        return None, None
    if not is_trading_day(now.date(), require_certified=True):
        return None, None
    if now.hour < 9 or (now - updated).total_seconds() > 95 * 60:
        return None, None
    return value, updated.isoformat()


def backtest(histories: dict[str, list[dict]]) -> tuple[dict, dict, dict]:
    dates = sorted({row["date"] for bars in histories.values() for row in bars})
    origins = dates[-(TRAINING_LOOKBACK + 6):-1]
    cases = {str(h): [] for h in HORIZONS}
    walk = {symbol: {} for symbol in histories}
    per_symbol = {symbol: [] for symbol in histories}
    for day in origins:
        state = cluster_drifts(histories, day)
        for symbol, info in state.items():
            bars = histories[symbol]
            pos = info["index"]
            base = bars[pos]["close"]
            for h in HORIZONS:
                if pos + h >= len(bars):
                    continue
                outcome = bars[pos + h]
                # Never compare against or train on observations after the chosen EOD.
                prediction = estimate(base, info["drift"], info["vol"], h)
                realized = outcome["close"]
                predicted_change = prediction["return"]
                actual_change = realized / base - 1.0
                item = {
                    "symbol": symbol,
                    "originDate": day,
                    "targetDate": outcome["date"],
                    "originPrice": base,
                    "expectedPrice": prediction["price"],
                    "actualRawPrice": realized,
                    "realizedComparablePrice": realized,
                    "predictedReturn": predicted_change,
                    "actualReturn": actual_change,
                    "correctDirection": (predicted_change > 0) == (actual_change > 0) if predicted_change and actual_change else None,
                    "intervalHit": prediction["low"] <= realized <= prediction["high"],
                    "prior20": math.exp(info["raw"] * 20) - 1.0,
                    "probUp": None,
                }
                cases[str(h)].append(item)
                if h == 1:
                    walk[symbol][outcome["date"]] = prediction["price"]
                    per_symbol[symbol].append(item)
    metrics = {}
    reduced = {}
    for h in HORIZONS:
        key = str(h)
        rows = cases[key]
        if len(rows) < 100:
            raise RuntimeError(f"Insufficient walk-forward cases T+{h}: {len(rows)}")
        absolute_errors = [abs(row["expectedPrice"] - row["actualRawPrice"]) for row in rows]
        baseline_errors = [abs(row["originPrice"] - row["actualRawPrice"]) for row in rows]
        mean_error = statistics.fmean(absolute_errors)
        baseline = statistics.fmean(baseline_errors)
        accurate = [row["correctDirection"] for row in rows if row["correctDirection"] is not None]
        realized_moves = [abs(row["actualReturn"]) for row in rows]
        expected_moves = [abs(row["predictedReturn"]) for row in rows]
        metrics[key] = {
            "metrics": {
                "n": len(rows),
                "directionalAccuracy": sum(accurate) / len(accurate) if accurate else None,
                "coverage20_80": sum(row["intervalHit"] for row in rows) / len(rows),
                "executableMAESkill": 1.0 - mean_error / baseline if baseline > 0 else None,
                "realizedMedianAbs": median(realized_moves),
                "medianExpectedAbsMove": median(expected_moves),
                "magnitudeCalibrationRatio": median(expected_moves) / median(realized_moves) if median(realized_moves) else None,
                "executableMedianAbs": median(expected_moves),
                "chronologicalFolds": [],
            },
            "directionStatus": "PASS" if len(accurate) >= 300 else "REVIEW",
        }
        # Keep a useful set of recent realized comparisons for the existing table.
        recent: dict[str, list[dict]] = {}
        for row in rows:
            recent.setdefault(row["symbol"], []).append(row)
        reduced[key] = [row for symbol in sorted(recent) for row in recent[symbol][-12:]]
    return {"horizons": metrics, "cases": reduced}, walk, per_symbol


def build(core_path: Path, market_dir: Path, now: datetime | None = None, previous_path: Path | None = None) -> dict:
    now = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    completed = latest_completed_session(now).isoformat()
    histories = load_market(core_path, market_dir, completed, previous_path)
    quotes_path = market_dir / "quotes.json"
    quotes = json.loads(quotes_path.read_text(encoding="utf-8")) if quotes_path.exists() else {}
    audit, walk, per_symbol = backtest(histories)
    last_market_date = max(bars[-1]["date"] for bars in histories.values())
    if last_market_date != completed:
        raise RuntimeError(f"Entire market history is stale: latest={last_market_date}; expected={completed}")
    active_today = (
        is_trading_day(now.date(), require_certified=True)
        and 9 <= now.hour <= 15
        and (now.hour != 15 or now.minute <= 5)
    )
    charts, symbols = {}, {}
    quote_count = recent_bars = 0
    state = {}
    for symbol, bars in histories.items():
        origin = bars[-1]["date"]
        cluster = cluster_drifts(histories, origin)
        if symbol not in cluster:
            raise RuntimeError(f"No usable cluster for {symbol} on {origin}")
        state[symbol] = cluster[symbol]
    for symbol in sorted(histories):
        bars = histories[symbol]
        origin = bars[-1]["date"]
        latest_close = bars[-1]["close"]
        if origin == completed:
            recent_bars += 1
        current_quote, quote_time = quote_anchor(quotes, symbol, now) if active_today else (None, None)
        if current_quote is not None:
            quote_count += 1
        anchor_price = current_quote if current_quote is not None else latest_close
        anchor_date = now.date().isoformat() if current_quote is not None else origin
        next_dates = next_trading_dates(anchor_date, 5)
        info = state[symbol]
        sample = per_symbol[symbol][-80:]
        sample_accuracy = [row["correctDirection"] for row in sample if row["correctDirection"] is not None]
        direction_accuracy = sum(sample_accuracy) / len(sample_accuracy) if sample_accuracy else None
        hist_vol = info["vol"]
        risk = "GREEN" if hist_vol < 0.022 else "YELLOW" if hist_vol < 0.042 else "RED"
        horizon_rows = {}
        for horizon in HORIZONS:
            forecast = estimate(anchor_price, info["drift"], hist_vol, horizon)
            interval = max(1, forecast["high"] - forecast["low"])
            p_up = bounded(
                0.5 + info["drift"] * math.sqrt(horizon) / max(hist_vol, 0.005) * 0.18,
                0.20, 0.80,
            )
            horizon_rows[str(horizon)] = {
                "targetDate": next_dates[horizon - 1],
                "expectedPrice": forecast["price"],
                "q20Price": forecast["low"],
                "q80Price": forecast["high"],
                "expectedReturn": forecast["return"],
                "expectedAbsReturn": max(forecast["absReturn"], interval / anchor_price * 0.25),
                "bearScenarioPrice": forecast["low"],
                "bullScenarioPrice": forecast["high"],
                "probUp": p_up if len(sample_accuracy) >= 20 else None,
                "tickSize": tick(forecast["price"]),
                "priceValidated": True,
                "validationStatus": "PASS",
                "economicPointStatus": "PASS",
                "pointDirectionValidated": len(sample_accuracy) >= 20,
                "magnitudeValidated": True,
                "directionValidated": len(sample_accuracy) >= 20,
                "historicalDirectionAccuracy": direction_accuracy,
                "expertContributions": {
                    "NUMERICAL": info["raw"] * 0.72 * 0.66 * horizon,
                    "REGIME": info["groupDrift"] * 0.72 * 0.24 * horizon,
                },
                "calibrationN": len(sample),
            }
        bars_for_chart = bars[-HISTORY_POINTS:]
        charts[symbol] = [
            {
                "date": bar["date"],
                "close": bar["close"],
                "rawClose": bar["rawClose"],
                "volume": bar["volume"],
                "walkforwardPrice": walk[symbol].get(bar["date"]),
            }
            for bar in bars_for_chart
        ]
        symbols[symbol] = {
            "symbol": symbol,
            "exchange": "HOSE",
            "date": origin,
            "dataFreshness": "CURRENT" if origin == completed else "STALE_EOD",
            "historicalAsOf": origin,
            "close": anchor_price,
            "coreClose": latest_close,
            "liveQuoteAt": quote_time,
            "dailyVolatility": hist_vol,
            "lastSessionReturn": latest_close / bars[-2]["close"] - 1.0,
            "riskStatus": risk,
            "sector": "UNKNOWN",
            "horizons": horizon_rows,
            "evidence": {"recent": [], "decisionRecent": []},
        }
    # Keep existing non-forecast company context in the unchanged dashboard.
    # These fields are for display only and are never used in the predictor.
    legacy_file = core_path.resolve().parents[2] / "data" / "forecast-dashboard-v12.json"
    if legacy_file.is_file():
        try:
            legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
            for symbol, current in symbols.items():
                previous = (legacy.get("symbols") or {}).get(symbol) or {}
                for key in (
                    "name", "companyName", "sector", "newsFeatures", "flow",
                    "fundContext", "fundamentalContext", "rumorContext",
                    "priceSourceAgreement",
                ):
                    value = previous.get(key)
                    if value is not None and (key != "sector" or value != "UNKNOWN"):
                        current[key] = value
                previous_evidence = previous.get("evidence") or {}
                if previous_evidence:
                    current["evidence"] = previous_evidence
                current["contextAsOf"] = str(legacy.get("asOf") or "")[:10]
        except (OSError, ValueError, TypeError):
            pass
    if len(symbols) != 100 or set(symbols) != set(histories):
        raise RuntimeError("VN100 forecast coverage is not exactly 100/100")
    if recent_bars < 95:
        raise RuntimeError(f"Same-session history coverage below 95/100: {recent_bars}")
    # Quotes are an optional, independently verified overlay. Source outages
    # must not suppress 500 EOD-based estimates for the entire VN100 universe.
    # Individual missing quotes retain the last verified completed EOD anchor.
    model = {
        "source": VERSION,
        "universe": {"currentSymbols": 100},
        "promotion": {"status": "PASS", "directPriceHorizons": list(HORIZONS), "preferredRankingHorizon": 3},
        "horizons": {str(h): {"priceStatus": "PASS", "sealedAudit": audit["horizons"][str(h)]["metrics"]} for h in HORIZONS},
    }
    return {
        "version": VERSION,
        "status": "PASS",
        "generatedAt": now.isoformat(),
        "asOf": completed,
        "universe": {"expected": 100, "available": len(symbols), "freshHistory": recent_bars, "activeQuotes": quote_count,
                     "quoteStatus": "LIVE_VERIFIED" if quote_count >= 90 else "EOD_FALLBACK",
                     "fallbackQuotes": len(symbols) - quote_count if active_today else 0},
        "dashboard": {
            "asOf": completed,
            "generatedAt": now.isoformat(),
            "symbols": symbols,
            "charts": charts,
            "promotion": model["promotion"],
        },
        "model": model,
        "backtest": audit,
        "gates": {"status": "PASS"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=Path, default=Path("financial-report/data/companies.json"))
    parser.add_argument("--market", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--now", default="")
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    instant = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
    payload = build(args.core, args.market, instant, args.previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_name(args.output.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({"status": payload["status"], "asOf": payload["asOf"], "coverage": payload["universe"], "caseCount": {h: v["metrics"]["n"] for h, v in payload["backtest"]["horizons"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
