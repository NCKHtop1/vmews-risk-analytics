"""Isolated VBMA, corporate-event and SBV money-market research feed probes.

NEVER publishes quotes, model inputs, public JSON or generated recommendations.
Only records source-linked observations in private CI artifacts until license,
point-in-time and independent quant gates are explicitly approved.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

UTC = timezone.utc
MAX_BYTES = 1_500_000
UA = "FinQueryResearchProbe/1.0 (+https://github.com/NCKHtop1/vmews-risk-analytics)"
VBMA = {
    "vbma_gov_bond_yield": {
        "url": "https://vbma.org.vn/csv/markets/charts/vi/government_bond_yield.csv",
        "market": "GOVERNMENT_BOND_OUTRIGHT",
        "instrument": "VND_GOVERNMENT_BONDS",
        "unit": "SOURCE_UNIT_NOT_VERIFIED",
    },
    "vbma_repo_benchmark": {
        "url": "https://vbma.org.vn/csv/markets/charts/vi/short_term_benchmark_rate.csv",
        "market": "SECURED_GOVERNMENT_BOND_REPO",
        "instrument": "VND_GOVERNMENT_BOND_REPO",
        "unit": "SOURCE_UNIT_NOT_VERIFIED",
    },
    "vbma_fx_swap": {
        "url": "https://vbma.org.vn/csv/markets/charts/vi/fx_swap_curve.csv",
        "market": "USD_VND_FX_SWAP",
        "instrument": "USD_VND_FX_SWAP_POINTS",
        "unit": "SOURCE_UNIT_NOT_VERIFIED",
    },
    "vbma_fi_bond_cd": {
        "url": "https://vbma.org.vn/csv/markets/charts/vi/fi_bond_yield_curve.csv",
        "market": "FINANCIAL_INSTITUTION_BOND_CD",
        "instrument": "FINANCIAL_INSTITUTION_BONDS_AND_CD",
        "unit": "SOURCE_UNIT_NOT_VERIFIED",
    },
}
EVENTS_URL = (
    "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics/"
    "financial-insights-data/data/corporate-events.json"
)
_ALLOWED_DOMAINS = ("vbma.org.vn", "raw.githubusercontent.com")
_DATE = re.compile(
    r"(?<!\d)(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}[-/]\d{1,2}[-/]20\d{2})(?!\d)"
)


def now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def approved_url(url, provider=None):
    parts = urlsplit(str(url))
    if parts.scheme != "https" or parts.username or parts.password or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if provider == "vbma":
        return host in ("vbma.org.vn", "www.vbma.org.vn")
    if provider == "events":
        return host == "raw.githubusercontent.com"
    return host in _ALLOWED_DOMAINS


def fetch_bytes(url, provider, timeout=9, limit=MAX_BYTES):
    if not approved_url(url, provider):
        raise ValueError("Unapproved research source URL")
    request = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,text/html,application/json,*/*;q=0.5"})
    with urlopen(request, timeout=timeout) as response:
        if not approved_url(response.geturl(), provider):
            raise ValueError("Source redirected outside approved domain")
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Source response exceeds size cap")
        return raw


def _clean(value):
    return " ".join(str(value or "").replace("\ufeff", "").replace("\xa0", " ").split()).strip()


def _norm(value):
    value = unicodedata.normalize("NFD", _clean(value).casefold())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def _decode_candidates(raw):
    encodings = ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1258", "latin1")
    for encoding in encodings:
        try:
            text = raw.decode(encoding, errors="strict")
        except (UnicodeError, LookupError):
            continue
        if not text or "\x00" in text[:1000]:
            continue
        if sum(ord(c) < 32 and c not in "\t\r\n" for c in text[:1000]) > 2:
            continue
        yield encoding, text


def parse_vbma_csv(raw):
    """Preserve source header/labels; never infer a rate from an unknown column."""
    if len(raw) > MAX_BYTES or len(raw) < 6 or b"<html" in raw[:300].lower():
        raise ValueError("Not a bounded numeric CSV")
    best = None
    for encoding, text in _decode_candidates(raw):
        if text.lstrip().startswith(("<html", "{", "[")):
            continue
        if text.startswith("sep="):
            text = "\n".join(text.splitlines()[1:])
        for separator in (",", ";", "\t", "|"):
            try:
                grid = list(csv.reader(io.StringIO(text), delimiter=separator, strict=True))
            except (csv.Error, UnicodeError):
                continue
            grid = [[_clean(v) for v in row] for row in grid if any(_clean(v) for v in row)]
            if len(grid) < 2:
                continue
            # A 1-column blob or wildly ragged HTML is never accepted as a curve.
            width = len(grid[0])
            if width < 2 or width > 160:
                continue
            consistent = sum(len(r) == width for r in grid[1:51])
            if consistent < max(1, min(len(grid) - 1, 5) // 2):
                continue
            score = consistent * 100 + width * 2 - sum(abs(len(r) - width) for r in grid[1:51])
            if encoding == "utf-8-sig":
                score += 1
            if best is None or score > best[0]:
                best = (score, encoding, separator, grid)
    if best is None:
        raise ValueError("No valid CSV grid detected")
    _, encoding, separator, grid = best
    headers = [value or "Column " + str(i + 1) for i, value in enumerate(grid[0])]
    if len(set(headers)) != len(headers):
        used = {}
        unique = []
        for header in headers:
            used[header] = used.get(header, 0) + 1
            unique.append(header + (" [" + str(used[header]) + "]" if used[header] > 1 else ""))
        headers = unique
    rows = [
        {headers[i]: item[i] if i < len(item) and item[i] not in ("", "-", "—", "N/A") else None
         for i in range(len(headers))}
        for item in grid[1:501]
        if len(item) == len(headers)
    ]
    if not rows or not any(re.search(r"\d", str(v or "")) for row in rows for v in row.values()):
        raise ValueError("No numeric-looking observations")
    stamps = [
        _DATE.search(str(value)).group(1)
        for row in [dict(zip(headers, headers))] + rows[:6]
        for value in row.values() if _DATE.search(str(value))
    ]
    return {
        "sourceEncoding": encoding,
        "delimiter": separator,
        "columns": headers,
        "rows": rows,
        "rawRowCount": len(grid) - 1,
        "sourceDateCandidates": sorted(set(stamps))[:16],
        "parsedNumericUnit": False,
        "quality": "date_and_unit_unverified",
        "modelEligible": False,
        "publicationEligible": False,
    }


def _aware_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def review_pit_events(payload):
    """Do not turn event date or crawl date into first-publication time."""
    events = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(events, list):
        raise ValueError("Corporate events payload malformed")
    safe, withheld = [], []
    for row in events[:10000]:
        if not isinstance(row, dict) or not row.get("symbol") or not row.get("date"):
            continue
        source = row.get("source") or {}
        publisher = str(source.get("publisher") or "").lower()
        url = str(source.get("url") or "")
        disclosed = (row.get("details") or {}).get("publishedAt") or row.get("publishedAt")
        timestamp = _aware_timestamp(disclosed)
        official = any(key in publisher for key in ("hose", "vsdc"))
        valid = bool(
            timestamp and official and url.startswith("https://")
            and timestamp <= datetime.now(UTC)
            and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", str(row.get("date")))
        )
        record = {
            "id": str(row.get("id") or "")[:100],
            "symbol": str(row.get("symbol"))[:12],
            "eventDate": row.get("date"),
            "firstPublishedAt": timestamp.isoformat() if timestamp else None,
            "sourceUrl": url[:500],
            "eventType": str(row.get("type") or "other")[:48],
            "pitVerified": valid,
            "modelEligible": False,
        }
        (safe if valid else withheld).append(record)
    return {"verifiedCandidates": safe, "withheld": withheld, "checked": len(safe) + len(withheld)}


def probe(fetch=fetch_bytes):
    stamp = now_iso()
    results = {}
    for name, spec in VBMA.items():
        try:
            data = fetch(spec["url"], "vbma")
            parsed = parse_vbma_csv(data)
            results[name] = {
                "status": "needs_review",
                "market": spec["market"], "instrument": spec["instrument"],
                "unit": spec["unit"], "sourceUrl": spec["url"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "observations": parsed, "checkedAt": stamp,
                "licenseStatus": "review_required",
            }
        except Exception as exc:
            results[name] = {
                "status": "unavailable", "market": spec["market"],
                "sourceUrl": spec["url"], "checkedAt": stamp,
                "reason": (type(exc).__name__ + ": " + str(exc))[:220],
                "modelEligible": False, "publicationEligible": False,
            }
    try:
        raw = fetch(EVENTS_URL, "events")
        checked = review_pit_events(json.loads(raw))
        results["corporate_events_pit"] = {
            "status": "needs_review", "checkedAt": stamp,
            "sourceUrl": EVENTS_URL, "sha256": hashlib.sha256(raw).hexdigest(),
            "checked": checked["checked"], "candidates": checked["verifiedCandidates"][:100],
            "withheldCount": len(checked["withheld"]),
            "modelEligible": False, "publicationEligible": False,
        }
    except Exception as exc:
        results["corporate_events_pit"] = {
            "status": "unavailable", "checkedAt": stamp, "sourceUrl": EVENTS_URL,
            "reason": (type(exc).__name__ + ": " + str(exc))[:220],
            "modelEligible": False, "publicationEligible": False,
        }
    # The official NHNN ON fixing is distinct from VBMA government-bond repo.
    # No synthetic or aggregator replacement is permitted as an official series.
    for key, tenor in [
        ("nhnn_unsecured_interbank_on", "ON"),
        ("nhnn_unsecured_interbank_1w", "1W"),
        ("nhnn_unsecured_interbank_2w", "2W"),
        ("nhnn_unsecured_interbank_1m", "1M"),
        ("nhnn_unsecured_interbank_3m", "3M"),
        ("nhnn_unsecured_interbank_6m", "6M"),
    ]:
        results[key] = {
            "status": "pending_official_machine_readable_source",
            "market": "UNSECURED_INTERBANK",
            "instrument": "VND_" + tenor,
            "sourceAgency": "State Bank of Vietnam",
            "sourceUrl": "https://www.sbv.gov.vn/",
            "checkedAt": stamp,
            "rate": None,
            "unit": "%_PER_ANNUM",
            "modelEligible": False,
            "publicationEligible": False,
        }
    for key, instrument in [
        ("nhnn_omo", "OPEN_MARKET_OPERATIONS"),
        ("nhnn_tin_phieu", "SBV_BILLS"),
    ]:
        results[key] = {
            "status": "pending_official_machine_readable_source",
            "market": "SBV_POLICY_OPERATIONS",
            "instrument": instrument,
            "sourceAgency": "State Bank of Vietnam",
            "sourceUrl": "https://www.sbv.gov.vn/",
            "checkedAt": stamp,
            "value": None,
            "unit": "SOURCE_UNIT_NOT_VERIFIED",
            "modelEligible": False,
            "publicationEligible": False,
        }
    return {
        "schemaVersion": 1, "checkedAt": stamp, "mode": "SHADOW_ONLY",
        "pipeline": "finquery_research_feeds",
        "publicServingEnabled": False, "strategyInputsChanged": False,
        "forecastInputsChanged": False, "licenseApproved": False,
        "quality": "needs_review" if any(v["status"] == "needs_review" for v in results.values()) else "unavailable",
        "sources": results,
    }


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", default="/tmp/finquery-research-shadow/research-feed-status.json")
    args = cli.parse_args()
    result = probe()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix(target.suffix + ".tmp")
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(target)
    report = {
        "mode": result["mode"], "quality": result["quality"],
        "sources": {key: value["status"] for key, value in result["sources"].items()},
        "artifact": str(target),
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
