"""Fail loudly when public FinQuery quote snapshots lag the published market source."""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

SOURCE = "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/financial-market-data/market/quotes.json"
PAGES = "https://nckhtop1.github.io/vmews-risk-analytics/financial-report/market/quotes.json"
DOMAIN = "https://finquery.info.vn/financial-report/market/quotes.json"
MAX_PUBLIC_LAG_SECONDS = 25 * 60


class PricePublicationError(ValueError):
    pass


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise PricePublicationError("missing quote source timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PricePublicationError("invalid quote source timestamp") from exc
    if dt.tzinfo is None:
        raise PricePublicationError("timezone missing from quote source timestamp")
    dt = dt.astimezone(timezone.utc)
    if dt > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise PricePublicationError("future quote source timestamp")
    return dt


def validate(data, label):
    if not isinstance(data, dict) or data.get("status") != "ok":
        raise PricePublicationError(f"{label}: missing or invalid status")
    expected = int(data.get("expected") or 0)
    covered = int(data.get("coverage") or 0)
    quotes = data.get("quotes") or {}
    if expected < 100 or not isinstance(quotes, dict):
        raise PricePublicationError(f"{label}: no complete HOSE Core+Liquid universe")
    minimum = math.ceil(expected * .95)
    valid = sum(1 for q in quotes.values() if isinstance(q, dict)
                and isinstance(q.get("price"), (int, float)) and q["price"] > 0
                and isinstance(q.get("sourceTime"), str))
    if covered < minimum or valid < minimum:
        raise PricePublicationError(f"{label}: quote coverage too low: {valid}/{expected} records, declared {covered}")
    dt = timestamp(data.get("latestSourceTime"))
    return {"sourceTime": dt, "expected": expected, "covered": valid, "label": label}


def compare(source, public, label, max_lag=MAX_PUBLIC_LAG_SECONDS):
    raw = validate(source, "source")
    view = validate(public, label)
    if raw["expected"] != view["expected"]:
        raise PricePublicationError(f"{label}: expected universe mismatch {view['expected']} != {raw['expected']}")
    lag = (raw["sourceTime"] - view["sourceTime"]).total_seconds()
    if lag > max_lag:
        raise PricePublicationError(f"{label}: public quotes lag source by {lag:.0f}s (allowed {max_lag}s)")
    return {"site": label, "coverage": view["covered"], "expected": view["expected"],
            "sourceTime": view["sourceTime"].isoformat(), "lagSeconds": max(0, int(lag))}


def read(url):
    req = Request(url + "?availability_probe=" + str(int(datetime.now(timezone.utc).timestamp())),
                  headers={"User-Agent": "FinQuery-Price-Availability-Guard/1.0",
                           "Cache-Control": "no-cache", "Accept": "application/json"})
    with urlopen(req, timeout=14) as response:
        if response.status != 200:
            raise PricePublicationError(f"HTTP {response.status}")
        return json.load(response)


def main():
    try:
        source = read(SOURCE)
        validate(source, "source")
    except Exception as exc:
        print(f"::error::SOURCE_PRICE_UNAVAILABLE {type(exc).__name__}: {exc}")
        return 22
    for label, url, code in (("pages", PAGES, 21), ("domain", DOMAIN, 23)):
        try:
            report = compare(source, read(url), label)
            print(json.dumps(report, ensure_ascii=False))
        except Exception as exc:
            print(f"::error::{label.upper()}_PRICE_PUBLICATION_FAILURE {type(exc).__name__}: {exc}")
            return code
    print("FINQUERY PUBLIC PRICE AVAILABILITY: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
