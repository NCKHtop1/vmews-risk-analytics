#!/usr/bin/env python3
"""Exploratory, offline FinQuery news-impact event study. NEVER emits live alerts.

Data lineage matters: backfilled RSS dates are publication dates, not verified
first-visible-in-FinQuery times. Every result remains RESEARCH_ONLY until a
separate forward, point-in-time evaluation passes.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
HORIZONS = (1, 3, 5)
AMBIGUOUS = {"HCM", "VND", "CEO", "GAS", "PET", "POW"}
SUBSIDIARIES = {
    "FPT": ("fpt telecom", "fpt retail", "fpt securities", "fpt shop", "fpt long chau"),
    "VIC": ("vinfast", "vinpearl", "vinschool"),
}


def parse_time(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            ts = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, IndexError):
            return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def normalize(value):
    s = unicodedata.normalize("NFD", str(value or "").lower().replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+-\s+[^-]{2,40}$", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def polarity(title):
    s = normalize(title)
    positive = ("loi nhuan tang", "lai tang", "lai ky luc", "doanh thu tang", "trung thau",
                "duoc phe duyet", "duoc cap phep", "ha lai suat", "giam thue",
                "giam chi phi", "tang truong manh")
    negative = ("loi nhuan giam", "bao lo", "lo rong", "loi nhuan lao doc",
                "khoi to", "xu phat", "dinh chi", "truy thu", "vo no",
                "vi pham", "thu hoi giay phep", "giam doanh thu")
    pos = any(v in s for v in positive)
    neg = any(v in s for v in negative)
    return "MIXED" if pos and neg else "POS" if pos else "NEG" if neg else "UNKNOWN"


def issuer_identity(symbol, title):
    t = normalize(title)
    if symbol in AMBIGUOUS and not (
        re.search(r"\b(co phieu|ma co phieu|ma ck|hose|hnx)\s+" + symbol.lower() + r"\b", t)
        or symbol == "VND" and "vndirect" in t
        or symbol == "GAS" and "pv gas" in t
    ):
        return False
    if symbol in SUBSIDIARIES and any(x in t for x in SUBSIDIARIES[symbol]):
        if not ("tap doan " + symbol.lower()) in t and not ("co phieu " + symbol.lower()) in t:
            return False
    return bool(re.search(r"\b" + re.escape(symbol.lower()) + r"\b", t))


def entry_index(days, published):
    local = published.astimezone(VN)
    day = local.date().isoformat()
    # Daily OHLCV cannot establish an executable intraday entry at publication.
    # Use the next session open after any publication at/after 09:00 VN.
    if local.hour * 60 + local.minute >= 9 * 60:
        return bisect.bisect_right(days, day)
    return bisect.bisect_left(days, day)


def read_history(directory):
    histories = {}
    today = datetime.now(VN).date().isoformat()
    for file in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            rows = data.get("bars") or []
            bars = []
            for row in rows:
                day = str(row.get("time", ""))[:10]
                if not re.fullmatch(r"\d{4}-\d\d-\d\d", day) or day >= today:
                    continue  # exclude still-forming intraday EOD bar
                opening, closing = float(row.get("open", 0)), float(row.get("close", 0))
                if opening > 0 and closing > 0 and math.isfinite(opening + closing):
                    bars.append({"day": day, "open": opening, "close": closing})
            bars.sort(key=lambda v: v["day"])
            if len(bars) >= 100 and len({v["day"] for v in bars}) == len(bars):
                histories[file.stem] = {"bars": bars, "days": [v["day"] for v in bars],
                                        "index": {v["day"]: i for i, v in enumerate(bars)}}
        except (OSError, ValueError, TypeError):
            continue
    return histories


def log_return(hist, index, horizon):
    bars = hist["bars"]
    last = index + horizon - 1
    if index < 0 or last >= len(bars):
        return None
    val = math.log(bars[last]["close"] / bars[index]["open"])
    return val if abs(val) <= 0.50 else None  # split/corporate-action guard


def read_sectors(risk_file):
    if not risk_file.exists():
        return {}
    try:
        raw = json.loads(risk_file.read_text(encoding="utf-8"))
        return {member["symbol"]: sector["id"] for sector in raw.get("sectors", [])
                for member in sector.get("memberRows", [])
                if member.get("symbol") and sector.get("id")}
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def ingest_news(path, histories):
    rows = json.loads(path.read_text(encoding="utf-8")).get("symbols", {})
    counters = Counter()
    first_seen = 0
    candidates = []
    for symbol, articles in rows.items():
        counters["symbols_in_archive"] += 1
        if symbol not in histories:
            counters["no_price_symbol_articles"] += len(articles)
            continue
        days = histories[symbol]["days"]
        seen_titles = set()
        for item in articles:
            counters["all_news_rows"] += 1
            timestamp = parse_time(item.get("publishedAt") or item.get("published"))
            if not timestamp:
                counters["invalid_publish_time"] += 1
                continue
            if item.get("firstSeenAt") or item.get("firstObservedAt"):
                first_seen += 1
            title = str(item.get("title", ""))
            if not issuer_identity(symbol, title):
                counters["ambiguous_or_unverified_issuer"] += 1
                continue
            if item.get("sourceClass") == "RUMOR_UNVERIFIED":
                counters["rumor_quarantine"] += 1
                continue
            key = normalize(title)
            if not key or key in seen_titles:
                counters["duplicate_headline"] += 1
                continue
            seen_titles.add(key)
            index = entry_index(days, timestamp)
            if index >= len(days):
                counters["unmatured"] += 1
                continue
            candidates.append({
                "symbol": symbol, "timestamp": timestamp, "day": days[index],
                "index": index, "sector": "", "event": str(item.get("event") or "GENERAL"),
                "polarity": polarity(title), "source": str(item.get("publisher") or item.get("source") or "UNKNOWN"),
                "titleHash": hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
                "verifiedFirstSeen": bool(item.get("firstSeenAt") or item.get("firstObservedAt")),
            })
    counters["first_seen_timestamp_rows"] = first_seen
    candidates.sort(key=lambda e: (e["timestamp"], e["symbol"], e["event"]))
    accepted = []
    last_event = {}
    for e in candidates:
        cooldown_key = (e["symbol"], e["event"], e["polarity"])
        prev = last_event.get(cooldown_key)
        if prev is not None and e["index"] - prev < 5:
            counters["overlapping_event_cooldown"] += 1
            continue
        last_event[cooldown_key] = e["index"]
        accepted.append(e)
    counters["independent_proxy_events"] = len(accepted)
    counters["archive_news_rows_total"] = counters["all_news_rows"] + counters["no_price_symbol_articles"]
    counters["proxy_year_distribution"] = {str(y): sum(e["day"].startswith(str(y)) for e in accepted) for y in range(2019, 2027)}
    return accepted, counters


def market_controls(histories, days):
    control = {}
    for day in sorted(days):
        for h in HORIZONS:
            vals = []
            for sym, hist in histories.items():
                idx = hist["index"].get(day)
                if idx is None:
                    continue
                r = log_return(hist, idx, h)
                if r is not None:
                    vals.append(r)
            if len(vals) >= 20:
                control[(day, h)] = statistics.median(vals)
    return control


def one_sided_sign_p(values, sign):
    wins = sum(v * sign > 0 for v in values)
    n = len(values)
    if n == 0:
        return 1.0
    return min(1.0, sum(math.comb(n, k) for k in range(wins, n + 1)) / (2 ** n))


def benjamini_hochberg(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    q = [1.0] * len(pvals)
    prior = 1.0
    for rank in range(len(order), 0, -1):
        index = order[rank - 1]
        prior = min(prior, pvals[index] * len(pvals) / rank)
        q[index] = prior
    return q


def report_impact(events, histories, sectors):
    controls = market_controls(histories, {e["day"] for e in events})
    valid = []
    for event in events:
        hist = histories[event["symbol"]]
        enriched = dict(event)
        enriched["sector"] = sectors.get(event["symbol"], "UNMAPPED")
        enriched["ar"] = {}
        for h in HORIZONS:
            r = log_return(hist, event["index"], h)
            baseline = controls.get((event["day"], h))
            if r is not None and baseline is not None:
                enriched["ar"][h] = r - baseline
        if enriched["ar"]:
            valid.append(enriched)
    days = sorted(set(e["day"] for e in valid))
    if not days:
        return {"status": "NO_MATURE_EVENTS", "groups": [], "eventsWithReturn": 0}
    split = days[int(len(days) * 0.7)]
    embargo_from = (date.fromisoformat(split) - timedelta(days=7)).isoformat()
    embargo_to = (date.fromisoformat(split) + timedelta(days=7)).isoformat()
    groups = defaultdict(list)
    for e in valid:
        if e["sector"] == "UNMAPPED" or e["polarity"] not in ("POS", "NEG"):
            continue
        groups[(e["sector"], e["event"], e["polarity"])].append(e)
    summaries = []
    tests = []
    for (sector, event_type, sentiment), rows in groups.items():
        train = [r for r in rows if r["day"] < embargo_from]
        test = [r for r in rows if r["day"] > embargo_to]
        for h in HORIZONS:
            tr = [r["ar"][h] for r in train if h in r["ar"]]
            te = [r["ar"][h] for r in test if h in r["ar"]]
            if not tr or not te:
                continue
            direction = 1 if statistics.median(tr) > 0 else -1
            hit = sum(direction * v > 0 for v in te)
            result = {
                "sector": sector, "event": event_type, "semanticPolarity": sentiment,
                "horizonSessions": h, "trainN": len(tr), "holdoutN": len(te),
                "distinctHoldoutDates": len(set(r["day"] for r in test if h in r["ar"])),
                "holdoutMonths": len(set(r["day"][:7] for r in test if h in r["ar"])),
                "trainSign": "UP" if direction > 0 else "DOWN",
                "trainMedianARbps": round(statistics.median(tr) * 10000, 1),
                "holdoutMedianARbps": round(statistics.median(te) * 10000, 1),
                "holdoutHitRate": round(hit / len(te), 3),
                "pValueExploratory": round(one_sided_sign_p(te, direction), 6),
            }
            # Important: pooled articles about multiple tickers on one date are
            # correlated. This sign test is DIAGNOSTIC, never a production gate.
            result["sampleSufficient"] = (
                len(tr) >= 40 and len(te) >= 20
                and result["distinctHoldoutDates"] >= 15
                and result["holdoutMonths"] >= 4
            )
            summaries.append(result)
            tests.append(one_sided_sign_p(te, direction))
    q = benjamini_hochberg(tests)
    for row, qq in zip(summaries, q):
        row["fdrQExploratory"] = round(qq, 6)
        row["tentativePattern"] = (
            row["sampleSufficient"] and qq <= 0.10
            and row["holdoutHitRate"] >= 0.60
            and (row["holdoutMedianARbps"] if row["trainSign"] == "UP"
                 else -row["holdoutMedianARbps"]) >= 30
        )
        row["productionEligible"] = False  # No PIT ingestion and no forward validation.
    summaries.sort(key=lambda r: (-r["holdoutN"], r["sector"], r["event"]))
    return {
        "status": "EXPLORATORY_ONLY",
        "eventsWithReturn": len(valid), "uniqueEventDays": len(days),
        "earliestEventDay": days[0], "latestEventDay": days[-1],
        "splitDate": split, "embargoCalendarDays": 7,
        "groupsTested": len(summaries),
        "tentativePatterns": sum(r["tentativePattern"] for r in summaries),
        "groups": summaries[:60],
    }


def archive_info(path):
    if not path.exists():
        return {"available": False}
    try:
        o = json.loads(path.read_text(encoding="utf-8"))
        rows = o.get("records")
        if isinstance(rows, dict):
            example = next(iter(rows.values()), {})
            record_count = len(rows)
        elif isinstance(rows, list):
            example = rows[0] if rows else {}
            record_count = len(rows)
        else:
            example = {}
            record_count = 0
        pit = o.get("pointInTimePolicy") or o.get("pointInTime") or {}
        sector_pit = o.get("sectorPITStatus") or {}
        return {
            "available": True, "bytes": path.stat().st_size,
            "version": o.get("version"), "generatedAt": o.get("generatedAt"),
            "events": o.get("events"), "topLevelKeys": sorted(list(o))[:25],
            "historicalRecordCount": record_count,
            "recordSchema": sorted(example)[:30] if isinstance(example, dict) else [],
            "pointInTimePolicy": str(pit)[:1200],
            "sectorPITStatus": str(sector_pit)[:1200],
            "summaryKeys": sorted((o.get("summary") or {}).keys())[:25] if isinstance(o.get("summary"), dict) else [],
            "warning": o.get("warning") or "",
        }
    except (OSError, ValueError, TypeError):
        return {"available": True, "unreadable": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--news", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--sector", type=Path, required=True)
    parser.add_argument("--event-study", type=Path, required=True)
    parser.add_argument("--event-intelligence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    histories = read_history(args.history)
    events, quality = ingest_news(args.news, histories)
    sectors = read_sectors(args.sector)
    stats = report_impact(events, histories, sectors)
    report = {
        "version": "FINQUERY-NEWS-IMPACT-RESEARCH-0.1",
        "status": "RESEARCH_ONLY_NO_ALERTS",
        "input": {"news": str(args.news), "histories": len(histories),
                  "sectorMapping": len(sectors), "newsTimestamp": "RETROSPECTIVE_PUBLISHED_AT"},
        "quality": dict(quality),
        "archiveAudit": {
            "eventStudyV11": archive_info(args.event_study),
            "eventIntelligenceV12": archive_info(args.event_intelligence),
        },
        "backtest": stats,
        "limits": [
            "No verified historical firstSeenAt; retrospective RSS is NOT a tradable point-in-time news tape",
            "Latest sector map is not an historical point-in-time classification",
            "Daily OHLCV cannot price execution immediately after intraday news",
            "Ticker/issuer/subsidiary ambiguity requires human-labelled evaluation",
            "Contemporaneous multi-ticker events are correlated; exploratory p-values are NOT final inference",
            "Company actions, fee/slippage and trading suspensions require PIT validation",
            "No sector or ticker alert may be enabled before independent forward shadow tests",
        ],
        "releaseGate": {"liveTickerAlerts": False, "liveSectorAlerts": False,
                        "allowExposureHypotheses": True,
                        "required": ["verified_first_seen", "issuer_entity_QA",
                                     "historical_PIT_sector", "block_bootstrap_by_event_day",
                                     "FDR_control", "non_event_placebo", "forward_shadow",
                                     "net_cost_positive_and_stable"]},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "quality": report["quality"],
        "priceHistories": report["input"]["histories"], "sectorMapped": len(sectors),
        "backtest": {k: v for k, v in stats.items() if k != "groups"},
        "largestExploratoryGroups": stats.get("groups", [])[:8],
        "archiveAudit": report["archiveAudit"],
        "productionAlerts": False
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
