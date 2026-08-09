from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, timedelta, datetime, timezone
import json
import math

try:
    from vnstock.ui import Market
except Exception:
    from vnstock import Market


def _range_start(label: str) -> date:
    today = date.today()
    if label == "1y":
        return today - timedelta(days=400)
    if label == "5y":
        return today - timedelta(days=5 * 366 + 30)
    # Vnstock Community documents an 8-year daily-history limit.
    return today - timedelta(days=8 * 366 + 30)


def _normalise_dataframe(df):
    if df is None or getattr(df, "empty", True):
        return []

    frame = df.copy()
    try:
        frame = frame.reset_index()
    except Exception:
        pass

    # Flatten any MultiIndex-like columns and normalise to lowercase strings.
    flat_cols = []
    for c in frame.columns:
        if isinstance(c, tuple):
            name = "_".join(str(x) for x in c if str(x) != "")
        else:
            name = str(c)
        flat_cols.append(name.strip().lower().replace(" ", "_"))
    frame.columns = flat_cols

    def pick(candidates):
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate
        for col in frame.columns:
            for candidate in candidates:
                if col.endswith("_" + candidate):
                    return col
        return None

    time_col = pick(["time", "date", "datetime", "trading_date", "index"])
    open_col = pick(["open"])
    high_col = pick(["high"])
    low_col = pick(["low"])
    close_col = pick(["close"])
    volume_col = pick(["volume", "match_volume", "total_volume"])

    if close_col is None:
        raise ValueError(f"Vnstock response has no close column: {list(frame.columns)}")

    rows = []
    for _, r in frame.iterrows():
        close = r.get(close_col)
        try:
            close = float(close)
        except Exception:
            continue
        if not math.isfinite(close) or close <= 0:
            continue

        raw_time = r.get(time_col) if time_col else None
        if raw_time is None:
            continue
        try:
            if hasattr(raw_time, "isoformat"):
                d = raw_time.isoformat()[:10]
            else:
                d = str(raw_time)[:10]
        except Exception:
            continue

        def num(col, default):
            if not col:
                return default
            try:
                v = float(r.get(col))
                return v if math.isfinite(v) else default
            except Exception:
                return default

        rows.append({
            "date": d,
            "open": num(open_col, close),
            "high": num(high_col, close),
            "low": num(low_col, close),
            "close": close,
            "volume": num(volume_col, 0),
        })

    # Deduplicate and sort because upstream providers can occasionally repeat bars.
    by_date = {x["date"]: x for x in rows}
    return [by_date[k] for k in sorted(by_date)]


def _load_vnindex(range_label: str):
    start = _range_start(range_label)
    end = date.today() + timedelta(days=1)

    market = Market()
    df = market.index("VNINDEX").ohlcv(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1D",
    )
    rows = _normalise_dataframe(df)
    if len(rows) < 10:
        raise ValueError(f"Only {len(rows)} valid VNINDEX rows returned")

    return {
        "symbol": "VNINDEX",
        "source": "Vnstock v4 Unified UI",
        "provider": "KBS via Vnstock",
        "range": range_label,
        "asOf": rows[-1]["date"],
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }


class handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=900")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        range_label = query.get("range", ["5y"])[0]
        if range_label not in {"1y", "5y", "max"}:
            range_label = "5y"

        try:
            self._json(200, _load_vnindex(range_label))
        except Exception as exc:
            self._json(502, {
                "error": "VNSTOCK_FETCH_FAILED",
                "message": str(exc),
                "source": "Vnstock v4 Unified UI",
                "provider": "KBS via Vnstock",
            })
