import os
import pathlib
import sys
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen

# -----------------------------------------------------------------------------
# VMEWS production entrypoint
# -----------------------------------------------------------------------------
# IMPORTANT: Vercel's deployed filesystem/home is read-only. Vnstock creates
# ~/.vnstock during import, so all writable paths MUST be redirected before any
# Vnstock module is imported.
os.environ["VNSTOCK_DATA_DIR"] = "/tmp/.vnstock"
os.environ["HOME"] = "/tmp"
os.environ["USERPROFILE"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"
os.environ["XDG_CONFIG_HOME"] = "/tmp/.config"
os.environ["XDG_DATA_HOME"] = "/tmp/.local/share"
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/pycache"
os.environ["JOBLIB_TEMP_FOLDER"] = "/tmp/joblib"

for directory in (
    "/tmp/.vnstock",
    "/tmp/.vnstock/id",
    "/tmp/.cache",
    "/tmp/.config",
    "/tmp/.local/share",
    "/tmp/matplotlib",
    "/tmp/pycache",
    "/tmp/joblib",
):
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        pass

# Some dependencies resolve home through pathlib rather than environment vars.
pathlib.Path.home = classmethod(lambda cls: cls("/tmp"))

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The research/operational model core lives outside /api, so this is the ONLY
# Python serverless entrypoint Vercel exposes for the EWS.
import ews_core as core

VERSION = "EWS-2.2.0"
YAHOO_SYMBOL = "^VNINDEX.VN"


def _yahoo_result(range_value="10y"):
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        endpoint = (
            f"https://{host}/v8/finance/chart/{quote(YAHOO_SYMBOL)}"
            f"?range={range_value}&interval=1d&includePrePost=false&events=div%2Csplits"
        )
        try:
            request = Request(endpoint, headers={
                "User-Agent": "Mozilla/5.0 VMEWS/2.2",
                "Accept": "application/json,text/plain,*/*",
            })
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = (payload.get("chart", {}).get("result") or [None])[0]
            if result:
                return result, host
            errors.append(f"{host}: no chart result")
        except Exception as exc:
            errors.append(f"{host}: {exc}")
    raise RuntimeError(" | ".join(errors) or "Yahoo chart unavailable")


def _yahoo_market():
    result, host = _yahoo_result("10y")
    timestamps = result.get("timestamp") or []
    quote_data = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []

    def at(name, i, default):
        try:
            value = float((quote_data.get(name) or [])[i])
            return value if value == value else default
        except Exception:
            return default

    for i, ts in enumerate(timestamps):
        try:
            close = float((quote_data.get("close") or [])[i])
            if not (close > 0):
                continue
            rows.append({
                "date": datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat(),
                "open": at("open", i, close),
                "high": at("high", i, close),
                "low": at("low", i, close),
                "close": close,
                "volume": at("volume", i, 0.0),
            })
        except Exception:
            continue

    rows = core.merge_rows(rows)
    rows, intraday_removed = core.strip_incomplete_session(rows)
    if len(rows) < 300:
        raise RuntimeError(f"Yahoo returned only {len(rows)} valid daily rows")

    meta = result.get("meta") or {}
    quote_payload = None
    try:
        last = float(meta.get("regularMarketPrice"))
        previous = float(meta.get("chartPreviousClose") or meta.get("previousClose"))
        quote_payload = {
            "last": last,
            "change": last - previous,
            "percentChange": (last / previous - 1) * 100 if previous else None,
            "time": datetime.fromtimestamp(
                int(meta.get("regularMarketTime") or time.time()), timezone.utc
            ).isoformat(),
        }
    except Exception:
        pass

    return rows, quote_payload, host, intraday_removed


def _operational_payload(rows, quote_payload, provider, primary_error=None, intraday_removed=False):
    feats = core.build_features(rows)
    if not feats:
        raise RuntimeError("Unable to build operational features")
    current = feats[-1]
    horizons, nearest = core.analogs(rows, feats, current)
    backtest = core.backtest(rows, feats)
    crash = core.crash_diagnostic(rows)
    meta = {
        "duplicatesRemoved": 0,
        "invalidRemoved": 0,
        "intradayBarExcluded": intraday_removed,
        "strategy": "secondary live provider after primary-provider exception",
        "requests": [{
            "type": "secondary-provider",
            "ok": True,
            "rows": len(rows),
            "provider": provider,
        }],
    }
    quality = core.data_quality(rows, meta)
    quality["status"] = "REVIEW"
    return {
        "version": VERSION,
        "symbol": "VNINDEX",
        "source": "Secondary live market feed",
        "provider": provider,
        "primaryProvider": "Vnstock v4 Community · KBS",
        "providerMode": "FAILOVER",
        "primaryError": str(primary_error)[:320] if primary_error else None,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "quote": quote_payload,
        "dataQuality": quality,
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
        "backtest": backtest,
        "analogs": nearest,
        "rows": rows,
        "scoreHistory": [
            {"date": f["date"], "score": round(f["score"], 3)} for f in feats
        ],
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


def _full():
    try:
        payload = core.load_market()
        payload["version"] = VERSION
        payload["providerMode"] = "PRIMARY"
        payload["primaryProvider"] = "Vnstock v4 Community · KBS"
        return payload
    except Exception as primary_error:
        rows, q, host, intraday_removed = _yahoo_market()
        return _operational_payload(
            rows,
            q,
            f"Yahoo Finance ({host}) · {YAHOO_SYMBOL}",
            primary_error=primary_error,
            intraday_removed=intraday_removed,
        )


def _quote():
    try:
        payload = core.load_quote()
        payload["version"] = VERSION
        payload["providerMode"] = "PRIMARY"
        payload["primaryProvider"] = "Vnstock v4 Community · KBS"
        return payload
    except Exception as primary_error:
        rows, q, host, _ = _yahoo_market()
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
            "version": VERSION,
            "symbol": "VNINDEX",
            "source": "Secondary live market feed",
            "provider": f"Yahoo Finance ({host}) · {YAHOO_SYMBOL}",
            "primaryProvider": "Vnstock v4 Community · KBS",
            "providerMode": "FAILOVER",
            "primaryError": str(primary_error)[:320],
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "quote": q,
        }


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload, cache):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-VMEWS-Version", VERSION)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        mode = parse_qs(urlparse(self.path).query).get("mode", ["full"])[0]
        try:
            if mode == "health":
                self._json(200, {
                    "ok": True,
                    "version": VERSION,
                    "runtimeHome": str(pathlib.Path.home()),
                    "vnstockDataDir": os.environ.get("VNSTOCK_DATA_DIR"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, "no-store")
            elif mode == "quote":
                self._json(200, _quote(), "s-maxage=20, stale-while-revalidate=40")
            else:
                self._json(200, _full(), "s-maxage=180, stale-while-revalidate=300")
        except Exception as exc:
            self._json(503, {
                "error": "VMEWS_ALL_LIVE_PROVIDERS_UNAVAILABLE",
                "message": str(exc),
                "version": VERSION,
                "providers": ["Vnstock v4 Community · KBS", "Yahoo Finance"],
                "retryable": True,
            }, "no-store")
