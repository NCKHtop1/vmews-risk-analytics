"""Refresh one publisher-timestamped RSS feed per current HOSE common stock.

A failed publisher request never erases its prior audited articles.  Security
identity is checked again by the model's point-in-time feature pipeline.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from forecast_v14_signal_audit import infer_sentiment, publication_timestamp, security_match


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_universe() -> set[str]:
    with gzip.open(DATA / "v12-frozen-source.json.gz", "rt", encoding="utf-8") as stream:
        frozen = json.load(stream)
    return {str(symbol).upper() for symbol in frozen.get("currentHOSESymbols", [])}


def article(symbol: str, item: ET.Element) -> dict[str, object] | None:
    title = str(item.findtext("title") or "").strip()
    published = str(item.findtext("pubDate") or "").strip()
    if not title or publication_timestamp(published) is None:
        return None
    publisher = title.rsplit(" - ", 1)[-1] if " - " in title else "Unknown"
    lower = title.casefold()
    event = "GENERAL"
    if any(term in lower for term in ("lợi nhuận", "doanh thu", "bán niên", "kết quả kinh doanh")):
        event = "EARNINGS"
    elif any(term in lower for term in ("khởi tố", "xử phạt", "thanh tra", "điều tra")):
        event = "REGULATORY"
    elif any(term in lower for term in ("khối ngoại", "tự doanh", "mua ròng", "bán ròng")):
        event = "MARKET_FLOW"
    elif any(term in lower for term in ("cổ tức", "phát hành", "niêm yết", "chia tách")):
        event = "CORPORATE_ACTION"
    source_class = "OFFICIAL" if any(term in lower for term in ("hsx.vn", "hose", "ủy ban chứng khoán")) else "MAINSTREAM"
    if any(term in lower for term in ("tin đồn", "đồn đoán", "lan truyền")):
        source_class = "RUMOR_UNVERIFIED"
    trusted = any(term in publisher.casefold() for term in ("cafef", "vietstock", "vnexpress", "vneconomy", "đầu tư", "vietnambiz"))
    label, score = infer_sentiment(title)
    return {
        "title": title,
        "link": str(item.findtext("link") or "").strip(),
        "published": published,
        "publisher": publisher,
        "sourceClass": source_class,
        "sourceQuality": 1.0 if source_class == "OFFICIAL" else .9 if trusted else .65,
        "event": event,
        "materiality": .58 if event != "GENERAL" else .35,
        "relevance": 1.0,
        "sentimentLabel": label,
        "sentimentScore": score,
        "query": f'"{symbol}" cổ phiếu',
    }


def fetch_symbol(symbol: str, universe: set[str]) -> tuple[str, list[dict[str, object]], str | None]:
    query = quote_plus(f'"{symbol}" cổ phiếu when:14d')
    url = f"https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi"
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 VMEWS-HOSE-News/14.0"})
        with urlopen(request, timeout=float(os.environ.get("V14_NEWS_TIMEOUT", "7"))) as response:
            root = ET.fromstring(response.read())
        items: list[dict[str, object]] = []
        for element in root.findall(".//item")[:18]:
            parsed = article(symbol, element)
            if parsed and security_match(symbol, str(parsed["title"]), universe):
                items.append(parsed)
        return symbol, items, None
    except Exception as exc:  # One failing publisher must not abort the universe.
        return symbol, [], f"{type(exc).__name__}: {exc}"[:160]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="diagnostic symbol limit")
    args = parser.parse_args()
    universe = load_universe()
    broad_path = DATA / "research-news-v10.json"
    existing = json.loads(broad_path.read_text(encoding="utf-8"))
    symbols = sorted(universe)[:args.limit] if args.limit else sorted(universe)
    failures: dict[str, str] = {}
    succeeded = 0
    new_articles = 0
    workers = min(int(os.environ.get("V14_NEWS_WORKERS", "20")), len(symbols))

    # Google News may temporarily rate-limit an entire runner address after a
    # full-market sweep.  Three independent liquid-symbol probes distinguish a
    # provider outage from an issuer with no headlines and prevent 404 doomed
    # eleven-second requests; the caller retains the previous verified archive.
    probe_symbols = [symbol for symbol in ("FPT", "VCB", "HPG") if symbol in symbols]
    probe_results: dict[str, tuple[str, list[dict[str, object]], str | None]] = {}
    if len(probe_symbols) >= 2:
        with ThreadPoolExecutor(max_workers=len(probe_symbols)) as probes:
            for future in as_completed(probes.submit(fetch_symbol, symbol, universe) for symbol in probe_symbols):
                outcome = future.result()
                probe_results[outcome[0]] = outcome
        if all(outcome[2] is not None for outcome in probe_results.values()):
            reasons = ", ".join(f"{symbol}: {outcome[2]}" for symbol, outcome in probe_results.items())
            raise RuntimeError(f"HOSE news publisher preflight unavailable; existing archive preserved ({reasons})")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        pending = [symbol for symbol in symbols if symbol not in probe_results]
        futures = [pool.submit(fetch_symbol, symbol, universe) for symbol in pending]
        outcomes = list(probe_results.values())
        outcomes.extend(future.result() for future in as_completed(futures))
        for symbol, items, error in outcomes:
            if error:
                failures[symbol] = error
                continue
            prior = list(existing.get("symbols", {}).get(symbol, []))
            combined: list[dict[str, object]] = []
            seen: set[str] = set()
            for row in items + prior:
                identity = re.sub(r"\W+", " ", str(row.get("title") or "").casefold()).strip()
                if not identity or identity in seen or not security_match(symbol, str(row.get("title") or ""), universe):
                    continue
                seen.add(identity)
                combined.append(row)
            combined.sort(key=lambda row: publication_timestamp(row.get("published") or row.get("publishedAt")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            existing.setdefault("symbols", {})[symbol] = combined[:80]
            existing.setdefault("coverage", {}).setdefault(symbol, {})["used"] = len(combined[:80])
            succeeded += 1
            new_articles += len(items)

    minimum = max(1, int(len(symbols) * .55))
    if succeeded < minimum:
        raise RuntimeError(f"HOSE news refresh only reached {succeeded}/{len(symbols)} issuers; existing archive preserved")
    existing.update(
        {
            "version": "VMEWS-NEWS-14.0.0",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "universe": len(universe),
            "refreshAudit": {
                "requested": len(symbols),
                "succeeded": succeeded,
                "failed": len(failures),
                "recentArticlesCollected": new_articles,
                "preservesPriorArticlesOnFailure": True,
                "issuerIdentityChecked": True,
                "failures": failures,
            },
        }
    )
    broad_path.write_text(json.dumps(existing, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(existing["refreshAudit"], ensure_ascii=False))


if __name__ == "__main__":
    main()
