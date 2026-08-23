"""Audited VN30 membership and point-in-time community signal intelligence.

Public FireAnt articles are collected only through publisher-attributed RSS.
Private dashboard/community content is never inferred, scraped without access,
or represented as available.  A claim requires an identified issuer, an
explicit material thesis, independent corroboration and a known timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from forecast_v14_signal_audit import (
    effective_trading_session,
    infer_sentiment,
    publication_timestamp,
    security_match,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIREANT_PATH = DATA / "fireant-intelligence-v18.json"
VN_TZ = timezone(timedelta(hours=7))
VN30_EFFECTIVE_DATE = "2026-08-03"
VN30_CONSTITUENTS = (
    "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
    "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
    "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE",
)
SPECULATION = re.compile(
    r"tin\s+đồn|đồn\s+đoán|rộ\s+tin|lan\s+truyền|được\s+cho\s+là|"
    r"nguồn\s+tin|chưa\s+xác\s+nhận|dự\s+kiến|có\s+thể|khả\s+năng|"
    r"vào\s+tầm\s+ngắm|đàm\s+phán|tin\s+hành\s+lang",
    re.IGNORECASE,
)
MATERIAL_TOPICS = {
    "DIVESTMENT": re.compile(r"thoái\s+vốn|bán\s+vốn|bán\s+cổ\s+phần", re.IGNORECASE),
    "TAKEOVER": re.compile(r"thâu\s+tóm|sáp\s+nhập|m&a|mua\s+lại|chuyển\s+nhượng", re.IGNORECASE),
    "DIVIDEND": re.compile(r"cổ\s+tức|cổ\s+phiếu\s+thưởng|chia\s+tách", re.IGNORECASE),
    "FINANCING": re.compile(r"phát\s+hành|chào\s+bán|tăng\s+vốn|trái\s+phiếu", re.IGNORECASE),
    "EARNINGS": re.compile(r"lợi\s+nhuận|kết\s+quả\s+kinh\s+doanh|doanh\s+thu", re.IGNORECASE),
    "REGULATORY": re.compile(r"khởi\s+tố|thanh\s+tra|xử\s+phạt|điều\s+tra", re.IGNORECASE),
    "OPERATIONS": re.compile(r"dự\s+án|trúng\s+thầu|hợp\s+đồng|room\s+tín\s+dụng", re.IGNORECASE),
}
DENIAL = re.compile(r"bác\s+bỏ|phủ\s+nhận|đính\s+chính|sai\s+sự\s+thật|không\s+đúng", re.IGNORECASE)
CONFIRMATION = re.compile(
    r"chính\s+thức\s+xác\s+nhận|đã\s+ký|ký\s+kết|phê\s+duyệt|chấp\s+thuận|thông\s+qua|hoàn\s+tất",
    re.IGNORECASE,
)
STOPWORDS = {
    "công", "ty", "ctcp", "của", "với", "trong", "trên", "cho", "được", "sau",
    "trước", "theo", "thông", "tin", "phiếu", "chứng", "khoán", "doanh", "nghiệp",
    "ngày", "mới", "những", "các", "một", "là", "này", "tại", "giá", "đồng",
}


def vn30_metadata(as_of: str) -> dict[str, Any]:
    """Return the dated index roster; July members apply before its rebalance."""
    after_rebalance = str(as_of or "")[:10] >= VN30_EFFECTIVE_DATE
    members = set(VN30_CONSTITUENTS)
    if not after_rebalance:
        members.difference_update({"MCH", "TCX"})
        members.update({"PLX", "TPB"})
    return {
        "name": "VN30",
        "effectiveDate": VN30_EFFECTIVE_DATE if after_rebalance else "2026-02-02",
        "review": "2026-07" if after_rebalance else "2026-01",
        "source": "HOSE_REBALANCE_AND_SSIAM_VN30_BASKET",
        "symbols": sorted(members),
        "count": len(members),
    }


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _tokens(title: str) -> set[str]:
    normalized = re.sub(r"[^\wà-ỹ]+", " ", str(title or "").casefold(), flags=re.UNICODE)
    return {word for word in normalized.split() if len(word) > 2 and word not in STOPWORDS}


def _similarity(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _topics(title: str) -> set[str]:
    return {name for name, expression in MATERIAL_TOPICS.items() if expression.search(title)}


def _source_name(row: dict[str, Any]) -> str:
    return str(row.get("publisher") or row.get("source") or "").strip()


def _source_identity(row: dict[str, Any]) -> str:
    name = re.sub(r"[^\wà-ỹ]+", "", _source_name(row).casefold())
    return name or "unknown"


def _market_confirmation(history: list[dict[str, Any]], first_date: str) -> dict[str, float | None]:
    before = [row for row in history if str(row.get("date") or "")[:10] < first_date]
    if not before:
        return {"preMove2": None, "preMove5": None, "preVolumeLead": None}
    latest = _float(before[-1].get("rawClose") or before[-1].get("close"))

    def move(period: int) -> float | None:
        if len(before) <= period or latest <= 0:
            return None
        previous = _float(before[-period - 1].get("rawClose") or before[-period - 1].get("close"))
        return latest / previous - 1 if previous > 0 else None

    recent = [_float(row.get("volume")) for row in before[-5:]]
    baseline = [_float(row.get("volume")) for row in before[-25:-5]]
    lead = (sum(recent) / len(recent)) / (sum(baseline) / len(baseline)) if recent and baseline and sum(baseline) > 0 else None
    return {"preMove2": move(2), "preMove5": move(5), "preVolumeLead": lead}


def _rows(events: Any) -> list[dict[str, Any]]:
    if hasattr(events, "to_dict"):
        return list(events.to_dict("records"))
    return [dict(row) for row in events or [] if isinstance(row, dict)]


def _normalize(row: dict[str, Any], decision: datetime, cutoff: date, universe: set[str]) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
    title = str(row.get("title") or "").strip()
    timestamp = publication_timestamp(row.get("publishedAt") or row.get("published"))
    if symbol not in universe or not title or timestamp is None or timestamp > decision or timestamp.date() < cutoff:
        return None
    if not security_match(symbol, title, universe, require_explicit=True):
        return None
    source_type = str(row.get("sourceType") or row.get("sourceClass") or "NARRATIVE").upper()
    label, inferred = infer_sentiment(title)
    return {
        "symbol": symbol,
        "title": title,
        "publishedAt": timestamp,
        "availableDate": str(row.get("date") or row.get("availableDate") or effective_trading_session(timestamp))[:10],
        "publisher": _source_name(row),
        "sourceType": source_type,
        "credibility": max(0.0, min(1.0, _float(row.get("credibility"), _float(row.get("sourceQuality"), .58)))),
        "sentiment": max(-1.0, min(1.0, _float(row.get("sentiment"), _float(row.get("sentimentScore"), inferred)))),
        "label": str(row.get("label") or row.get("sentimentLabel") or label),
        "link": str(row.get("link") or ""),
        "topics": _topics(title),
        "tokens": _tokens(title),
        "fireant": "fireant" in (_source_name(row) + " " + str(row.get("link") or "")).casefold(),
        "speculative": bool(SPECULATION.search(title) or "RUMOR" in source_type),
        "official": "OFFICIAL" in source_type or "CLARIFICATION" in source_type,
    }


def _cluster_snapshot(
    symbol: str,
    items: list[dict[str, Any]],
    officials: list[dict[str, Any]],
    history: list[dict[str, Any]],
    decision: datetime,
    as_of: str,
    ordinal: int,
) -> dict[str, Any] | None:
    ordered = sorted(items, key=lambda row: row["publishedAt"])
    if not any(row["speculative"] for row in ordered):
        return None
    independent_sources = {_source_identity(row) for row in ordered}
    first, latest = ordered[0], ordered[-1]
    shared_tokens = set().union(*(row["tokens"] for row in ordered))
    shared_topics = set().union(*(row["topics"] for row in ordered))
    resolution = next(
        (
            row
            for row in officials
            if row["publishedAt"] >= first["publishedAt"]
            and bool(row["topics"] & shared_topics)
            and _similarity(shared_tokens, row["tokens"]) >= .16
        ),
        None,
    )
    if len(independent_sources) < 2 and resolution is None:
        return None

    age_days = max(0, (decision.date() - latest["publishedAt"].date()).days)
    source_score = min(1.0, len(independent_sources) / 3.0)
    credibility = sum(row["credibility"] for row in ordered) / len(ordered)
    freshness = math.exp(-age_days / 14.0)
    market = _market_confirmation(history, first["availableDate"])
    volume_support = min(1.0, max(0.0, _float(market["preVolumeLead"], 1.0) - 1.0))
    quality = round(100 * (.25 + .28 * source_score + .20 * freshness + .17 * credibility + .10 * volume_support))
    if quality < 64:
        return None

    truth_state = "UNVERIFIED"
    if resolution is not None:
        if DENIAL.search(resolution["title"]):
            truth_state = "DENIED"
        elif CONFIRMATION.search(resolution["title"]):
            truth_state = "CONFIRMED"
    verification = truth_state if truth_state != "UNVERIFIED" else "CORROBORATED"
    weighted = sum(row["sentiment"] * max(.15, row["credibility"]) for row in ordered)
    divisor = sum(max(.15, row["credibility"]) for row in ordered)
    sentiment = weighted / divisor if divisor else 0.0
    if truth_state == "DENIED":
        sentiment = 0.0
    post_close = any(row["availableDate"] > as_of for row in ordered)
    eligible = post_close and verification in {"CORROBORATED", "CONFIRMED"} and abs(sentiment) > .05 and quality >= 70
    source_rows = sorted(
        ({"name": row["publisher"], "publishedAt": row["publishedAt"].isoformat(timespec="seconds"), "link": row["link"], "fireant": row["fireant"]} for row in ordered),
        key=lambda row: row["publishedAt"],
        reverse=True,
    )
    return {
        "claimId": f"{symbol}-Q{ordinal:03d}",
        "title": next((row["title"] for row in reversed(ordered) if row["speculative"]), latest["title"]),
        "firstDate": first["availableDate"],
        "lastDate": latest["availableDate"],
        "firstPublishedAt": first["publishedAt"].isoformat(timespec="seconds"),
        "items": len(ordered),
        "sources": len(independent_sources),
        "velocity": len(ordered) / max(1, (latest["publishedAt"].date() - first["publishedAt"].date()).days + 1),
        "sourceDiversity": len(independent_sources) / len(ordered),
        "qualityScore": quality,
        "sourceCredibility": credibility,
        "topics": sorted(shared_topics),
        "truthState": truth_state,
        "verificationState": verification,
        "resolutionDate": resolution["availableDate"] if resolution is not None else None,
        "resolutionTitle": resolution["title"] if resolution is not None else None,
        "sentimentScore": sentiment,
        "sourceDetails": source_rows[:6],
        "fireantMentions": sum(row["fireant"] for row in ordered),
        "postCloseEvidence": post_close,
        "inferenceEligible": eligible,
        "confidence": min(.82, quality / 100.0 * min(1.0, .55 + .15 * len(independent_sources))),
        **market,
    }


def rumor_intelligence(
    events: Any,
    histories: dict[str, list[dict[str, Any]]],
    as_of: str,
    decision_at: str,
    *,
    source_path: Path = FIREANT_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Cluster material narratives without assuming a rumor is true."""
    decision = publication_timestamp(decision_at)
    if decision is None:
        raise ValueError("decision_at requires a timezone-aware timestamp")
    universe = set(histories)
    cutoff = decision.date() - timedelta(days=35)
    normalized = [row for event in _rows(events) if (row := _normalize(event, decision, cutoff, universe)) is not None]
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        by_symbol.setdefault(row["symbol"], []).append(row)

    output: dict[str, dict[str, Any]] = {}
    candidates = 0
    for symbol, rows in by_symbol.items():
        material = sorted((row for row in rows if row["topics"]), key=lambda row: row["publishedAt"])
        speculative = [row for row in material if row["speculative"]]
        candidates += len(speculative)
        officials = [row for row in material if row["official"]]
        clusters: list[list[dict[str, Any]]] = []
        for candidate in speculative:
            match = next(
                (
                    cluster
                    for cluster in reversed(clusters)
                    if bool(candidate["topics"] & set().union(*(row["topics"] for row in cluster)))
                    and _similarity(candidate["tokens"], set().union(*(row["tokens"] for row in cluster))) >= .16
                ),
                None,
            )
            if match is None:
                clusters.append([candidate])
            else:
                match.append(candidate)

        claims: list[dict[str, Any]] = []
        for ordinal, cluster in enumerate(clusters, 1):
            cluster_topics = set().union(*(row["topics"] for row in cluster))
            cluster_tokens = set().union(*(row["tokens"] for row in cluster))
            start = min(row["publishedAt"] for row in cluster) - timedelta(days=4)
            end = max(row["publishedAt"] for row in cluster) + timedelta(days=7)
            identities = {(row["title"].casefold(), _source_identity(row)) for row in cluster}
            for supporting in material:
                identity = (supporting["title"].casefold(), _source_identity(supporting))
                if identity in identities or supporting["official"]:
                    continue
                if start <= supporting["publishedAt"] <= end and bool(supporting["topics"] & cluster_topics) and _similarity(cluster_tokens, supporting["tokens"]) >= .14:
                    cluster.append(supporting)
                    identities.add(identity)
            claim = _cluster_snapshot(symbol, cluster, officials, histories.get(symbol, []), decision, as_of, ordinal)
            if claim is not None:
                claims.append(claim)

        claims.sort(key=lambda claim: (claim["qualityScore"], claim["lastDate"]), reverse=True)
        live = [claim for claim in claims if claim["inferenceEligible"]]
        signal = sum(claim["sentimentScore"] * claim["confidence"] for claim in live)
        confidence = min(.8, sum(claim["confidence"] for claim in live) / len(live)) if live else 0.0
        if claims:
            output[symbol] = {
                "claims": claims[:8],
                "claimCount": len(claims),
                "corroboratedCount": sum(claim["sources"] >= 2 for claim in claims),
                "confirmedCount": sum(claim["truthState"] == "CONFIRMED" for claim in claims),
                "deniedCount": sum(claim["truthState"] == "DENIED" for claim in claims),
                "fireantMentions": sum(claim["fireantMentions"] for claim in claims),
                "inferenceEligible": bool(live),
                "usedByForecast": bool(live),
                "signalScore": max(-1.0, min(1.0, signal)),
                "confidence": confidence,
                "historicallyBacktested": False,
            }

    source = {"status": "UNAVAILABLE", "articles": 0, "communityAccess": "NOT_AUTHENTICATED"}
    try:
        if source_path.exists():
            loaded = json.loads(source_path.read_text(encoding="utf-8"))
            source = {
                "status": str(loaded.get("status") or "UNAVAILABLE"),
                "articles": int(loaded.get("articleCount") or 0),
                "collectedAt": loaded.get("generatedAt"),
                "communityAccess": "PUBLIC_PUBLISHER_RSS_ONLY",
                "publisher": "FireAnt",
            }
    except (OSError, ValueError, TypeError):
        pass
    audit = {
        "status": "ACTIVE" if output else "NO_QUALITY_CLAIMS",
        "candidateMentions": candidates,
        "qualifiedClaims": sum(item["claimCount"] for item in output.values()),
        "symbols": len(output),
        "decisionPriorSymbols": sum(item["usedByForecast"] for item in output.values()),
        "source": source,
        "pointInTime": True,
        "minimumIndependentSources": 2,
        "minimumQualityScore": 64,
        "futurePublicationsUsed": 0,
        "unverifiedClaimsReportedAsFacts": 0,
        "historicalBackfillRows": 0,
        "policy": "ISSUER_MATCH; MATERIAL_THESIS; INDEPENDENT_CORROBORATION; NO_SYNTHETIC_FIREANT_POSTS",
    }
    return output, audit


def _publisher_host(element: ET.Element) -> str:
    source = element.find("source")
    if source is None:
        return ""
    try:
        return urlparse(source.get("url") or "").hostname or ""
    except ValueError:
        return ""


def fireant_article(symbol: str, element: ET.Element, universe: set[str]) -> dict[str, Any] | None:
    source = element.find("source")
    publisher = (source.text or "").strip() if source is not None else ""
    host = _publisher_host(element).casefold()
    if not (host == "fireant.vn" or host.endswith(".fireant.vn") or publisher.casefold() == "fireant"):
        return None
    title = str(element.findtext("title") or "").strip()
    timestamp = publication_timestamp(element.findtext("pubDate"))
    if timestamp is None or not security_match(symbol, title, universe, require_explicit=True):
        return None
    label, sentiment = infer_sentiment(title)
    speculative = bool(SPECULATION.search(title) and _topics(title))
    return {
        "title": title,
        "link": str(element.findtext("link") or ""),
        "published": timestamp.isoformat(timespec="seconds"),
        "publisher": "FireAnt",
        "sourceClass": "RUMOR_UNVERIFIED" if speculative else "MAINSTREAM",
        "sourceQuality": .66,
        "event": next(iter(_topics(title)), "GENERAL"),
        "materiality": .63 if _topics(title) else .35,
        "relevance": 1.0,
        "sentimentLabel": label,
        "sentimentScore": sentiment,
        "sourceOrigin": "https://fireant.vn",
        "collectionMethod": "PUBLIC_PUBLISHER_ATTRIBUTED_GOOGLE_NEWS_RSS",
    }


def _fetch_fireant(symbol: str, universe: set[str]) -> tuple[str, list[dict[str, Any]], str | None]:
    query = quote_plus(f'site:fireant.vn/bai-viet "{symbol}" when:21d')
    address = f"https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi"
    try:
        request = Request(address, headers={"User-Agent": "Mozilla/5.0 VMEWS-FireAnt-Intelligence/18.0"})
        with urlopen(request, timeout=float(os.environ.get("V18_FIREANT_TIMEOUT", "6"))) as response:
            root = ET.fromstring(response.read())
        return symbol, [item for element in root.findall(".//item")[:12] if (item := fireant_article(symbol, element, universe)) is not None], None
    except Exception as error:
        return symbol, [], f"{type(error).__name__}: {error}"[:120]


def collect_fireant() -> dict[str, Any]:
    """Refresh public publisher articles while preserving the last valid archive."""
    source = json.loads((DATA / "research-news-v10.json").read_text(encoding="utf-8"))
    universe = set(source.get("symbols") or {})
    symbols = [symbol for symbol in VN30_CONSTITUENTS if symbol in universe]
    existing: dict[str, Any] = {}
    if FIREANT_PATH.exists():
        try:
            existing = json.loads(FIREANT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            existing = {}
    failures: dict[str, str] = {}
    output = dict(existing.get("symbols") or {})
    successful = 0
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(symbols)))) as pool:
        futures = [pool.submit(_fetch_fireant, symbol, universe) for symbol in symbols]
        for future in as_completed(futures):
            symbol, articles, error = future.result()
            if error:
                failures[symbol] = error
                continue
            successful += 1
            prior = output.get(symbol) or []
            seen: set[str] = set()
            merged: list[dict[str, Any]] = []
            for item in [*articles, *prior]:
                identity = hashlib.sha1(str(item.get("title") or "").casefold().encode("utf-8")).hexdigest()
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(item)
            merged.sort(key=lambda row: publication_timestamp(row.get("published")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            output[symbol] = merged[:35]
            if articles:
                broad = source.setdefault("symbols", {}).setdefault(symbol, [])
                prior_titles = {str(item.get("title") or "").casefold() for item in broad}
                for item in articles:
                    if item["title"].casefold() not in prior_titles:
                        broad.append(item)
                        prior_titles.add(item["title"].casefold())

    articles_count = sum(len(rows) for rows in output.values())
    payload = {
        "version": "VMEWS-FIREANT-INTELLIGENCE-18.0.0",
        "generatedAt": datetime.now(VN_TZ).isoformat(timespec="seconds"),
        "status": "ACTIVE" if articles_count else "NO_PUBLIC_PUBLISHER_ARTICLES",
        "publisher": "FireAnt",
        "collectionMethod": "PUBLIC_PUBLISHER_ATTRIBUTED_GOOGLE_NEWS_RSS",
        "authenticatedCommunityFeed": False,
        "universe": "VN30",
        "requested": len(symbols),
        "successful": successful,
        "failed": len(failures),
        "articleCount": articles_count,
        "symbols": output,
        "failures": failures,
    }
    FIREANT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if articles_count:
        (DATA / "research-news-v10.json").write_text(json.dumps(source, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {key: value for key, value in payload.items() if key not in {"symbols", "failures"}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-fireant", action="store_true")
    arguments = parser.parse_args()
    if arguments.collect_fireant:
        print(json.dumps(collect_fireant(), ensure_ascii=False))
