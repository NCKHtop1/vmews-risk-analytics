import argparse
import json
import math
import pathlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from vn_exchange_calendar import PRICE_READY_AFTER, is_trading_day, latest_completed_session

ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "data" / "forecast-dashboard-v12.json"
OUT = ROOT / "data" / "forecast-session-v21.json"
VN_TZ = timezone(timedelta(hours=7))
VERSION = "VMEWS-FORECAST-SESSION-21.3"
MIN_COVERAGE = 0.90
MIN_CURRENT_COVERAGE = 0.90
MIN_CUTOFF_FRESH_COVERAGE = 0.90


def num(value, default=None):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def norm_symbol(value):
    symbol = str(value or "").upper().split(":")[-1]
    return re.sub(r"[^A-Z0-9]", "", symbol)


def norm_exchange(value):
    exchange = str(value or "").upper().strip()
    return {"HSX": "HOSE", "HOCHIMINH": "HOSE"}.get(exchange, exchange)


def quote_time(value):
    timestamp = num(value)
    if timestamp is None:
        return None
    if timestamp > 1e12:
        timestamp /= 1000.0
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(VN_TZ)
    except Exception:
        return None


def session_name(now):
    if not is_trading_day(now.date(), require_certified=True):
        return "MARKET_CLOSED"
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60:
        return "PRE_OPEN"
    if minutes < 12 * 60 + 45:
        return "AM"
    ready_minutes = PRICE_READY_AFTER.hour * 60 + PRICE_READY_AFTER.minute
    if minutes < ready_minutes:
        return "PM"
    return "POST_CLOSE"


def cutoff_floor(now):
    session = session_name(now)
    if session in {"PRE_OPEN", "MARKET_CLOSED"}:
        return now
    hour, minute = (11, 15) if session == "AM" else (14, 30)
    floor = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if floor > now:
        return now - timedelta(minutes=20)
    return floor


def fetch_quotes():
    from tradingview_screener import stocks

    fields = [
        "name", "exchange", "close", "change", "volume",
        "relative_volume_10d_calc", "sector", "update_mode", "update_time",
    ]
    _, frame = stocks("vietnam").select(*fields).limit(3000).get_scanner_data()
    if frame is None or len(frame) < 500:
        raise RuntimeError(f"TradingView Vietnam screener returned only {0 if frame is None else len(frame)} rows")
    return frame


def preferred_core_horizon(dashboard):
    promotion = dashboard.get("promotion") or {}
    promoted = {int(value) for value in promotion.get("directPriceHorizons") or []}
    preferred = int(promotion.get("preferredRankingHorizon") or 5)
    if preferred in promoted or not promoted:
        return preferred
    for horizon in (3, 4, 5, 2, 1):
        if horizon in promoted:
            return horizon
    raise RuntimeError("No validated ranking horizon is available")


def eligible_core_symbols(dashboard, horizon=None):
    horizon = int(horizon or preferred_core_horizon(dashboard))
    eligible = {}
    for symbol, snapshot in (dashboard.get("symbols") or {}).items():
        forecast = (snapshot.get("horizons") or {}).get(str(horizon)) or {}
        close = num(snapshot.get("close"))
        target = num(forecast.get("expectedPrice"))
        if (
            snapshot.get("exchange") == "HOSE"
            and snapshot.get("dataFreshness") == "CURRENT"
            and forecast.get("priceValidated") is True
            and forecast.get("validationStatus") == "PASS"
            and close and target
        ):
            eligible[symbol] = snapshot
    if len(eligible) < 100:
        raise RuntimeError(f"Validated HOSE core universe unexpectedly small ({len(eligible)})")
    return eligible


def quality_score(snapshot, horizon, remaining_upside, interval_width):
    probability = num(horizon.get("probUp")) if horizon.get("directionValidated") is True else None
    if probability is None:
        probability_component = 0.45
    else:
        probability_component = max(0.0, min(1.0, (probability - 0.44) / 0.18))
    interval_component = max(0.0, min(1.0, remaining_upside / max(interval_width, 0.012)))
    risk = str(snapshot.get("riskStatus") or "UNKNOWN")
    risk_component = 1.0 if risk == "GREEN" else 0.55 if risk in {"WATCH", "YELLOW"} else 0.15
    return 0.42 * probability_component + 0.38 * interval_component + 0.20 * risk_component


def build_payload(dashboard, frame, now=None):
    now = now or datetime.now(VN_TZ)
    session = session_name(now)
    fresh_floor = cutoff_floor(now)
    ranking_horizon = preferred_core_horizon(dashboard)
    core = eligible_core_symbols(dashboard, ranking_horizon)
    expected_core_date = latest_completed_session(now).isoformat()
    expected_quote_date = (
        expected_core_date
        if session in {"PRE_OPEN", "POST_CLOSE", "MARKET_CLOSED"}
        else now.date().isoformat()
    )
    core_as_of = str(dashboard.get("asOf") or "")[:10]
    forecast_aligned = core_as_of == expected_core_date
    matched = {}
    duplicates = 0
    for _, row in frame.iterrows():
        symbol = norm_symbol(row.get("name")) or norm_symbol(row.get("ticker"))
        if symbol not in core or norm_exchange(row.get("exchange")) != "HOSE":
            continue
        if symbol in matched:
            duplicates += 1
            continue
        matched[symbol] = row

    current_quotes = 0
    cutoff_fresh_quotes = 0
    dated = []
    update_modes = []
    quote_ages = []
    symbols = []
    advancing = falling = flat = 0
    changes = []
    for symbol, snapshot in core.items():
        row = matched.get(symbol)
        if row is None:
            continue
        live_close = num(row.get("close"))
        if live_close is None or live_close <= 0:
            continue
        updated_at = quote_time(row.get("update_time"))
        quote_date = updated_at.date().isoformat() if updated_at else None
        if quote_date:
            dated.append(quote_date)
        is_current = quote_date == expected_quote_date
        fresh_for_cutoff = is_current if session in {"PRE_OPEN", "POST_CLOSE", "MARKET_CLOSED"} else bool(updated_at and fresh_floor <= updated_at <= now + timedelta(minutes=5))
        current_quotes += int(is_current)
        cutoff_fresh_quotes += int(fresh_for_cutoff)
        update_mode = str(row.get("update_mode") or "UNKNOWN")
        update_modes.append(update_mode)
        quote_age = max(0.0, (now - updated_at).total_seconds() / 60.0) if updated_at else None
        if quote_age is not None:
            quote_ages.append(quote_age)
        change_pct = (num(row.get("change"), 0.0) or 0.0) / 100.0
        if change_pct > 0.00005:
            advancing += 1
        elif change_pct < -0.00005:
            falling += 1
        else:
            flat += 1
        changes.append(change_pct)

        horizon = (snapshot.get("horizons") or {}).get(str(ranking_horizon)) or {}
        core_close = num(snapshot.get("close"))
        target = num(horizon.get("expectedPrice"))
        q20 = num(horizon.get("q20Price"))
        q80 = num(horizon.get("q80Price"))
        interval_width = ((q80 - q20) / core_close) if q20 is not None and q80 is not None and core_close else 0.0
        core_upside = target / core_close - 1.0
        remaining_upside = target / live_close - 1.0
        quality = quality_score(snapshot, horizon, max(remaining_upside, 0.0), max(interval_width, 0.0)) if forecast_aligned else None
        conviction = remaining_upside * (0.68 + 0.32 * quality) if quality is not None else None
        symbols.append({
            "symbol": symbol,
            "liveClose": live_close,
            "change": change_pct,
            "volume": num(row.get("volume"), 0.0),
            "relativeVolume10d": num(row.get("relative_volume_10d_calc")),
            "sector": str(row.get("sector") or snapshot.get("sector") or ""),
            "updateAt": updated_at.isoformat() if updated_at else None,
            "quoteCurrent": is_current,
            "freshForCutoff": fresh_for_cutoff,
            "updateMode": update_mode,
            "quoteAgeMinutes": round(quote_age, 2) if quote_age is not None else None,
            "coreClose": core_close,
            "rankingHorizon": ranking_horizon if forecast_aligned else None,
            "coreTarget": target,
            "coreUpside": core_upside,
            "remainingUpside": remaining_upside,
            "coreTargetT5": target,
            "coreUpsideT5": core_upside,
            "remainingUpsideT5": remaining_upside,
            "directionValidated": horizon.get("directionValidated") is True,
            "probUp": num(horizon.get("probUp")),
            "riskStatus": snapshot.get("riskStatus") or "UNKNOWN",
            "quality": round(quality, 5) if quality is not None else None,
            "conviction": round(conviction, 8) if conviction is not None else None,
        })

    eligible_count = len(core)
    quoted_count = len(symbols)
    coverage = quoted_count / eligible_count if eligible_count else 0.0
    current_coverage = current_quotes / eligible_count if eligible_count else 0.0
    cutoff_fresh_coverage = cutoff_fresh_quotes / eligible_count if eligible_count else 0.0
    dominant_quote_date = Counter(dated).most_common(1)[0][0] if dated else None
    mode_counts = dict(Counter(update_modes))
    dominant_mode = Counter(update_modes).most_common(1)[0][0] if update_modes else None
    status = "PASS" if (
        coverage >= MIN_COVERAGE
        and current_coverage >= MIN_CURRENT_COVERAGE
        and cutoff_fresh_coverage >= MIN_CUTOFF_FRESH_COVERAGE
    ) else "DEGRADED"

    positive = [row for row in symbols if forecast_aligned and row["coreTargetT5"] > row["liveClose"]]
    positive.sort(key=lambda row: (row["conviction"], row["remainingUpsideT5"], row["quality"]), reverse=True)
    defensive = not positive
    leaders = [] if not forecast_aligned else positive[:10] if positive else sorted(
        symbols,
        key=lambda row: (row["remainingUpsideT5"], row["quality"]),
        reverse=True,
    )[:10]

    ordered_changes = sorted(changes)
    median_change = ordered_changes[len(ordered_changes) // 2] if ordered_changes else None
    return {
        "version": VERSION,
        "status": status,
        "generatedAt": now.isoformat(),
        "session": session,
        "cutoffAt": now.isoformat(),
        "coreAsOf": dashboard.get("asOf"),
        "coreForecastUnchanged": True,
        "rankingHorizon": ranking_horizon,
        "mode": "FORECAST_ALIGNED" if forecast_aligned else "PRICE_ONLY_STALE_CORE",
        "scope": (
            f"Validated HOSE quotes re-rank remaining distance to the sealed T+{ranking_horizon} target without rewriting it."
            if forecast_aligned
            else "Validated HOSE quotes remain publishable for price display, while ranking and forecast decisions abstain until the completed-EOD core catches up."
        ),
        "forecastAlignment": {
            "status": "PASS" if forecast_aligned else "STALE_CORE",
            "rankingEligible": forecast_aligned,
            "actualCoreAsOf": core_as_of,
            "expectedCoreAsOf": expected_core_date,
        },
        "coverage": {
            "coreEligible": eligible_count,
            "quoted": quoted_count,
            "currentQuoteDate": current_quotes,
            "coverageRatio": round(coverage, 6),
            "currentCoverageRatio": round(current_coverage, 6),
            "cutoffFresh": cutoff_fresh_quotes,
            "cutoffFreshCoverageRatio": round(cutoff_fresh_coverage, 6),
            "freshnessFloor": fresh_floor.isoformat(),
            "expectedQuoteDate": expected_quote_date,
            "dominantQuoteDate": dominant_quote_date,
            "dominantUpdateMode": dominant_mode,
            "updateModeCounts": mode_counts,
            "medianQuoteAgeMinutes": round(sorted(quote_ages)[len(quote_ages)//2], 2) if quote_ages else None,
            "maxQuoteAgeMinutes": round(max(quote_ages), 2) if quote_ages else None,
            "duplicatesIgnored": duplicates,
        },
        "market": {
            "advancing": advancing,
            "falling": falling,
            "flat": flat,
            "medianChange": median_change,
            "positiveCoreTargetFromLive": len(positive),
            "defensive": defensive,
        },
        "leaders": leaders,
        "symbols": symbols,
        "governance": [
            "The session layer never treats an incomplete session as a completed EOD model row.",
            "Core T+1 to T+5 targets remain the independently validated sealed forecast until the completed-EOD pipeline publishes a new snapshot.",
            "Quote freshness is bound to the certified latest completed or active exchange session, never to a potentially stale core date.",
            "After the 15:05 EOD readiness cutoff, a same-session final quote remains current even when an illiquid symbol's last trade occurred before 14:30.",
            "When the core date lags, verified prices remain visible but forecast ranking and decision labels abstain until the completed-EOD pipeline catches up.",
            "A session snapshot is publishable only when universe coverage, expected-session coverage and cutoff freshness all pass strict gates; otherwise the prior last-known-good file is retained.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    payload = build_payload(dashboard, fetch_quotes())
    if payload["status"] != "PASS":
        raise RuntimeError(f"Session snapshot rejected by coverage gate: {payload['coverage']}")
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "status": payload["status"], "session": payload["session"], "coreAsOf": payload["coreAsOf"],
        "coverage": payload["coverage"], "leaders": [row["symbol"] for row in payload["leaders"]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
