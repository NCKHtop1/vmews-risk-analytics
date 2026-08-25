import argparse
import json
import math
import pathlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "data" / "forecast-dashboard-v12.json"
OUT = ROOT / "data" / "forecast-session-v21.json"
VN_TZ = timezone(timedelta(hours=7))
VERSION = "VMEWS-FORECAST-SESSION-21.0"
MIN_COVERAGE = 0.70
MIN_CURRENT_COVERAGE = 0.65


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
    minutes = now.hour * 60 + now.minute
    if minutes < 12 * 60 + 45:
        return "AM"
    if minutes < 17 * 60 + 30:
        return "PM"
    return "POST_CLOSE"


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


def eligible_core_symbols(dashboard):
    eligible = {}
    for symbol, snapshot in (dashboard.get("symbols") or {}).items():
        horizon = (snapshot.get("horizons") or {}).get("5") or {}
        close = num(snapshot.get("close"))
        target = num(horizon.get("expectedPrice"))
        if (
            snapshot.get("exchange") == "HOSE"
            and snapshot.get("dataFreshness") == "CURRENT"
            and horizon.get("priceValidated") is True
            and horizon.get("validationStatus") == "PASS"
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
    core = eligible_core_symbols(dashboard)
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
    dated = []
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
        is_current = quote_date == now.date().isoformat()
        current_quotes += int(is_current)
        change_pct = (num(row.get("change"), 0.0) or 0.0) / 100.0
        if change_pct > 0.00005:
            advancing += 1
        elif change_pct < -0.00005:
            falling += 1
        else:
            flat += 1
        changes.append(change_pct)

        horizon = (snapshot.get("horizons") or {}).get("5") or {}
        core_close = num(snapshot.get("close"))
        target = num(horizon.get("expectedPrice"))
        q20 = num(horizon.get("q20Price"))
        q80 = num(horizon.get("q80Price"))
        interval_width = ((q80 - q20) / core_close) if q20 is not None and q80 is not None and core_close else 0.0
        core_upside = target / core_close - 1.0
        remaining_upside = target / live_close - 1.0
        quality = quality_score(snapshot, horizon, max(remaining_upside, 0.0), max(interval_width, 0.0))
        conviction = remaining_upside * (0.68 + 0.32 * quality)
        symbols.append({
            "symbol": symbol,
            "liveClose": live_close,
            "change": change_pct,
            "volume": num(row.get("volume"), 0.0),
            "relativeVolume10d": num(row.get("relative_volume_10d_calc")),
            "sector": str(row.get("sector") or snapshot.get("sector") or ""),
            "updateAt": updated_at.isoformat() if updated_at else None,
            "quoteCurrent": is_current,
            "coreClose": core_close,
            "coreTargetT5": target,
            "coreUpsideT5": core_upside,
            "remainingUpsideT5": remaining_upside,
            "directionValidated": horizon.get("directionValidated") is True,
            "probUp": num(horizon.get("probUp")),
            "riskStatus": snapshot.get("riskStatus") or "UNKNOWN",
            "quality": round(quality, 5),
            "conviction": round(conviction, 8),
        })

    eligible_count = len(core)
    quoted_count = len(symbols)
    coverage = quoted_count / eligible_count if eligible_count else 0.0
    current_coverage = current_quotes / eligible_count if eligible_count else 0.0
    dominant_quote_date = Counter(dated).most_common(1)[0][0] if dated else None
    status = "PASS" if coverage >= MIN_COVERAGE and current_coverage >= MIN_CURRENT_COVERAGE else "DEGRADED"

    positive = [row for row in symbols if row["coreTargetT5"] > row["liveClose"]]
    positive.sort(key=lambda row: (row["conviction"], row["remainingUpsideT5"], row["quality"]), reverse=True)
    defensive = not positive
    leaders = positive[:10] if positive else sorted(
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
        "session": session_name(now),
        "cutoffAt": now.isoformat(),
        "coreAsOf": dashboard.get("asOf"),
        "coreForecastUnchanged": True,
        "scope": "Validated HOSE core universe with current TradingView session quotes; session quotes re-rank remaining distance to the sealed T+5 target but never rewrite the core forecast.",
        "coverage": {
            "coreEligible": eligible_count,
            "quoted": quoted_count,
            "currentQuoteDate": current_quotes,
            "coverageRatio": round(coverage, 6),
            "currentCoverageRatio": round(current_coverage, 6),
            "dominantQuoteDate": dominant_quote_date,
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
            "A session snapshot is publishable only when quote coverage and same-day quote coverage pass explicit gates; otherwise the prior last-known-good file is retained.",
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
