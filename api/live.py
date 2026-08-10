import os
import pathlib
import importlib.util
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen

# Vercel deployment files are read-only; /tmp is writable. Bootstrap all common
# user/cache locations before importing Vnstock or any transitive dependency.
os.environ["HOME"] = "/tmp"
os.environ["USERPROFILE"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"
os.environ["XDG_CONFIG_HOME"] = "/tmp/.config"
os.environ["XDG_DATA_HOME"] = "/tmp/.local/share"
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/pycache"
os.environ["JOBLIB_TEMP_FOLDER"] = "/tmp/joblib"

for directory in (
    "/tmp/.cache", "/tmp/.config", "/tmp/.local/share",
    "/tmp/matplotlib", "/tmp/pycache", "/tmp/joblib",
):
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        pass

# Some libraries use pathlib.Path.home() rather than the HOME environment value.
pathlib.Path.home = classmethod(lambda cls: cls("/tmp"))

# Import the EWS core only after the writable runtime bootstrap is complete.
core_path = pathlib.Path(__file__).with_name("ews.py")
spec = importlib.util.spec_from_file_location("vmews_ews_core", core_path)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

WRAPPER_VERSION = "EWS-2.1.3"
YAHOO_SYMBOL = "^VNINDEX.VN"


def _yahoo_json(range_value="10y"):
    hosts = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
    last_error = None
    for host in hosts:
        url = (
            f"https://{host}/v8/finance/chart/{quote(YAHOO_SYMBOL)}"
            f"?range={range_value}&interval=1d&includePrePost=false&events=div%2Csplits"
        )
        try:
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 VMEWS/2.1",
                "Accept": "application/json,text/plain,*/*",
            })
            with urlopen(req, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = payload.get("chart", {}).get("result", [None])[0]
            if result:
                return result, host
            last_error = RuntimeError(str(payload.get("chart", {}).get("error") or "No chart result"))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Yahoo fallback unavailable: {last_error}")


def _yahoo_rows():
    # Yahoo supports 10y natively; using it avoids a non-standard 8y range and
    # supplies a longer resilience window if Vnstock is temporarily unavailable.
    result, host = _yahoo_json("10y")
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    qd = (indicators.get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(timestamps):
        try:
            close = float((qd.get("close") or [])[i])
            if close <= 0:
                continue
            def number(name, default):
                try:
                    value = float((qd.get(name) or [])[i])
                    return value if value == value else default
                except Exception:
                    return default
            rows.append({
                "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                "open": number("open", close),
                "high": number("high", close),
                "low": number("low", close),
                "close": close,
                "volume": number("volume", 0.0),
            })
        except Exception:
            continue
    rows = core.merge_rows(rows)
    rows, intraday_removed = core.strip_incomplete_session(rows)
    if len(rows) < 300:
        raise RuntimeError(f"Yahoo fallback returned only {len(rows)} valid daily rows")

    meta = result.get("meta") or {}
    quote_payload = None
    try:
        regular = float(meta.get("regularMarketPrice"))
        previous = float(meta.get("chartPreviousClose") or meta.get("previousClose"))
        quote_payload = {
            "last": regular,
            "change": regular - previous,
            "percentChange": (regular / previous - 1) * 100 if previous else None,
            "time": datetime.fromtimestamp(
                int(meta.get("regularMarketTime") or time.time()), timezone.utc
            ).isoformat(),
        }
    except Exception:
        pass
    return rows, quote_payload, host, intraday_removed


def _payload_from_rows(rows, quote_payload, provider, primary_error):
    feats = core.build_features(rows)
    if not feats:
        raise RuntimeError("No operational features could be built from secondary data")
    current = feats[-1]
    horizons, nearest = core.analogs(rows, feats, current)
    bt = core.backtest(rows, feats)
    crash = core.crash_diagnostic(rows)
    meta = {
        "duplicatesRemoved": 0,
        "invalidRemoved": 0,
        "intradayBarExcluded": False,
        "strategy": "secondary provider after Vnstock failure",
        "requests": [{"type": "secondary-provider", "ok": True, "rows": len(rows), "provider": provider}],
    }
    dq = core.data_quality(rows, meta)
    # A secondary provider may be fresh and internally valid, but it is still a
    # failover condition. Mark REVIEW so the frontend cannot label it VNSTOCK LIVE.
    dq["status"] = "REVIEW"
    return {
        "version": WRAPPER_VERSION,
        "symbol": "VNINDEX",
        "source": "Secondary live market feed",
        "provider": provider,
        "primaryProvider": "Vnstock v4 Community · KBS",
        "providerMode": "FAILOVER",
        "primaryError": str(primary_error)[:240],
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "quote": quote_payload,
        "dataQuality": dq,
        "current": current,
        "risk": {
            "score": current["score"],
            "state": core.state(current["score"]),
            "narrative": core.narrative(current, horizons),
            "horizons": horizons,
            "alerts": core.build_alerts(current, crash),
            "playbook": core.playbook_for(core.state(current["score"])),
        },
        "crashDiagnostic": crash,
        "backtest": bt,
        "analogs": nearest,
        "rows": rows,
        "scoreHistory": [{"date": f["date"], "score": round(f["score"], 3)} for f in feats],
        "research": {
            "anfisAuc": 0.970,
            "crashSignals": 81,
            "crashWeeks": 31,
            "stress20Accuracy": 0.95,
            "sampleStocks": 251,
            "sectors": 10,
            "researchWindow": "2007–2023",
        },
    }


def _full_payload():
    try:
        payload = core.load_market()
        payload["version"] = WRAPPER_VERSION
        payload["providerMode"] = "PRIMARY"
        payload["primaryProvider"] = "Vnstock v4 Community · KBS"
        return payload
    except Exception as primary_error:
        rows, q, host, intraday_removed = _yahoo_rows()
        payload = _payload_from_rows(rows, q, f"Yahoo Finance ({host}) · {YAHOO_SYMBOL}", primary_error)
        payload["dataQuality"]["intradayBarExcluded"] = intraday_removed
        return payload


def _quote_payload():
    try:
        payload = core.load_quote()
        payload["version"] = WRAPPER_VERSION
        payload["providerMode"] = "PRIMARY"
        return payload
    except Exception as primary_error:
        rows, q, host, _ = _yahoo_rows()
        if not q:
            last = rows[-1]
            prev = rows[-2] if len(rows) > 1 else last
            q = {
                "last": last["close"],
                "change": last["close"] - prev["close"],
                "percentChange": (last["close"] / prev["close"] - 1) * 100 if prev["close"] else None,
                "time": f"EOD {last['date']}",
            }
        return {
            "version": WRAPPER_VERSION,
            "symbol": "VNINDEX",
            "source": "Secondary live market feed",
            "provider": f"Yahoo Finance ({host}) · {YAHOO_SYMBOL}",
            "primaryProvider": "Vnstock v4 Community · KBS",
            "providerMode": "FAILOVER",
            "primaryError": str(primary_error)[:240],
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "quote": q,
        }


class handler(BaseHTTPRequestHandler):
    def _json(self, code, payload, cache):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        mode = parse_qs(urlparse(self.path).query).get("mode", ["full"])[0]
        try:
            if mode == "quote":
                self._json(200, _quote_payload(), "s-maxage=20, stale-while-revalidate=40")
            else:
                self._json(200, _full_payload(), "s-maxage=180, stale-while-revalidate=300")
        except Exception as exc:
            self._json(503, {
                "error": "VMEWS_ALL_PROVIDERS_UNAVAILABLE",
                "message": str(exc),
                "version": WRAPPER_VERSION,
                "providers": ["Vnstock v4 Community · KBS", "Yahoo Finance"],
                "retryable": True,
            }, "no-store")
