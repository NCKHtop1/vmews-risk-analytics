import argparse
import json
import math
import pathlib
import re
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
VERSION = "SOLUTION-LIVE-1.0"
MIN_ROWS = 500
EXCHANGE_PRIORITY = {"HOSE": 3, "HNX": 2, "UPCOM": 1}


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
    return {
        "HSX": "HOSE",
        "HOCHIMINH": "HOSE",
        "HANOI": "HNX",
    }.get(exchange, exchange)


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


def collect_frame():
    from tradingview_screener import stocks

    fields = [
        "name",
        "exchange",
        "close",
        "change",
        "volume",
        "open",
        "high",
        "low",
        "update_mode",
        "update_time",
    ]
    _, frame = stocks("vietnam").select(*fields).limit(3000).get_scanner_data()
    if frame is None or len(frame) < MIN_ROWS:
        raise RuntimeError(
            f"TradingView Vietnam screener returned only {0 if frame is None else len(frame)} rows"
        )
    return frame


def build_snapshot(frame, now=None):
    now = now or datetime.now(timezone.utc)
    quotes = {}
    max_source = None
    exchange_counts = {}

    for _, row in frame.iterrows():
        symbol = norm_symbol(row.get("name")) or norm_symbol(row.get("ticker"))
        exchange = norm_exchange(row.get("exchange"))
        price = num(row.get("close"))
        if not symbol or exchange not in EXCHANGE_PRIORITY or price is None or price <= 0:
            continue

        existing = quotes.get(symbol)
        if existing and EXCHANGE_PRIORITY.get(existing.get("exchange"), 0) >= EXCHANGE_PRIORITY[exchange]:
            continue

        updated_at = quote_time(row.get("update_time"))
        if updated_at and (max_source is None or updated_at > max_source):
            max_source = updated_at

        quotes[symbol] = {
            "symbol": symbol,
            "exchange": exchange,
            "price": price,
            "changePct": num(row.get("change")),
            "volume": num(row.get("volume")),
            "open": num(row.get("open")),
            "high": num(row.get("high")),
            "low": num(row.get("low")),
            "updateAt": updated_at.isoformat() if updated_at else None,
            "source": "TradingView Vietnam screener · SoluTION.AI",
            "sourceMode": str(row.get("update_mode") or "UNKNOWN"),
        }

    for quote in quotes.values():
        exchange_counts[quote["exchange"]] = exchange_counts.get(quote["exchange"], 0) + 1

    if len(quotes) < MIN_ROWS:
        raise RuntimeError(f"SoluTION.AI live coverage too small: {len(quotes)} rows")

    generated = now.astimezone(timezone.utc).isoformat()
    source_time = max_source.astimezone(timezone.utc).isoformat() if max_source else generated
    return {
        "version": VERSION,
        "scope": "solution-ai",
        "status": "ok",
        "generatedAt": generated,
        "sourceTime": source_time,
        "coverage": len(quotes),
        "expected": len(quotes),
        "exchangeCounts": exchange_counts,
        "quotes": quotes,
    }


def write_snapshot(path, snapshot):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = build_snapshot(collect_frame())
    write_snapshot(args.output, snapshot)
    print(json.dumps({
        "status": snapshot["status"],
        "coverage": snapshot["coverage"],
        "sourceTime": snapshot["sourceTime"],
        "exchangeCounts": snapshot["exchangeCounts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
