"""Audited VN30 membership and point-in-time community signal intelligence.

Public FireAnt and 24HMoney articles are collected through publisher-attributed
RSS; publicly rendered 24HMoney community posts are admitted only when their
original text, author and publication time can be observed. Private content is
never inferred or represented as available. A forecast-moving claim requires
an identified issuer, material thesis and independent corroboration.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
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
COMMUNITY_LIVE_PATH = DATA / "community-intelligence-live-v19.json"
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
MARKET_THEMES = {
    "LÃI SUẤT": re.compile(r"lãi\s+suất|fed\b|ngân\s+hàng\s+trung\s+ương", re.IGNORECASE),
    "TỶ GIÁ": re.compile(r"tỷ\s+giá|usd|đồng\s+đô", re.IGNORECASE),
    "DẦU KHÍ": re.compile(r"dầu\s+khí|giá\s+dầu|năng\s+lượng", re.IGNORECASE),
    "CHÍNH SÁCH": re.compile(r"quốc\s+hội|chính\s+sách|luật\s+|nghị\s+định|room\s+tín\s+dụng", re.IGNORECASE),
    "THỊ TRƯỜNG": re.compile(r"vn[\s-]*index|thị\s+trường\s+chứng\s+khoán|thanh\s+khoản", re.IGNORECASE),
    "CÔNG NGHỆ": re.compile(r"trí\s+tuệ\s+nhân\s+tạo|bán\s+dẫn|nvidia|chuyển\s+đổi\s+số|\bai\b", re.IGNORECASE),
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


def community_events(events: Any, *, source_path: Path = FIREANT_PATH) -> list[dict[str, Any]]:
    """Combine audited publishers and quarantined public posts without leakage."""
    output = _rows(events)
    identities = {
        (str(item.get("symbol") or item.get("ticker") or "").upper(), str(item.get("title") or "").strip().casefold(), _source_identity(item))
        for item in output
    }
    try:
        archived = json.loads(source_path.read_text(encoding="utf-8")) if source_path.exists() else {}
    except (OSError, ValueError, TypeError):
        archived = {}
    for symbol, articles in (archived.get("symbols") or {}).items():
        for article in articles:
            item = {**article, "symbol": symbol}
            identity = (str(symbol).upper(), str(item.get("title") or "").strip().casefold(), _source_identity(item))
            if not identity[1] or identity in identities:
                continue
            identities.add(identity)
            output.append(item)
    return output


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
        "money24h": "24hmoney" in (_source_name(row) + " " + str(row.get("link") or "")).casefold(),
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
        ({"name": row["publisher"], "publishedAt": row["publishedAt"].isoformat(timespec="seconds"), "link": row["link"], "fireant": row["fireant"], "money24h": row["money24h"]} for row in ordered),
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
        "money24hMentions": sum(row["money24h"] for row in ordered),
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
                "money24hMentions": sum(claim["money24hMentions"] for claim in claims),
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
                "communityAccess": str(loaded.get("communityAccess") or "PUBLIC_PUBLISHER_RSS_ONLY"),
                "publisher": "FireAnt · 24HMoney",
                "publishers": loaded.get("publishers") or ["FireAnt"],
                "publisherCounts": loaded.get("publisherCounts") or {"FireAnt": int(loaded.get("articleCount") or 0)},
                "publicCommunityPosts": int(loaded.get("publicCommunityPosts") or 0),
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
        "policy": "ISSUER_MATCH; MATERIAL_THESIS; INDEPENDENT_CORROBORATION; PUBLIC_FIREANT_24HMONEY_ONLY; NO_SYNTHETIC_POSTS",
    }
    return output, audit


def community_watchlist(
    events: Any,
    histories: dict[str, list[dict[str, Any]]],
    decision_at: str,
    *,
    days: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Expose observed issuer discussions without treating one source as fact."""
    decision = publication_timestamp(decision_at)
    if decision is None:
        raise ValueError("decision_at requires a timezone-aware timestamp")
    cutoff = decision.date() - timedelta(days=days)
    universe = set(histories)
    output: dict[str, list[dict[str, Any]]] = {}
    identities: dict[str, set[str]] = {}
    for event in _rows(events):
        row = _normalize(event, decision, cutoff, universe)
        if row is None or row["official"]:
            continue
        if not (row["fireant"] or row["money24h"] or (row["speculative"] and row["topics"])):
            continue
        identity = hashlib.sha1(row["title"].casefold().encode("utf-8")).hexdigest()
        known = identities.setdefault(row["symbol"], set())
        if identity in known:
            continue
        known.add(identity)
        age = max(0.0, (decision - row["publishedAt"]).total_seconds() / 86_400)
        quality = round(100 * (.28 + .37 * row["credibility"] + .22 * math.exp(-age / 8.0) + (.13 if row["topics"] else .04)))
        output.setdefault(row["symbol"], []).append({
            "title": row["title"],
            "publisher": row["publisher"],
            "publishedAt": row["publishedAt"].isoformat(timespec="seconds"),
            "link": row["link"],
            "qualityScore": min(92, quality),
            "verificationState": "PENDING",
            "truthState": "UNVERIFIED",
            "sources": 1,
            "topics": sorted(row["topics"]),
            "fireant": row["fireant"],
            "money24h": row["money24h"],
            "inferenceEligible": False,
            "usedByForecast": False,
        })
    for symbol, items in output.items():
        items.sort(key=lambda row: row["publishedAt"], reverse=True)
        output[symbol] = items[:8]
    return output


def _publisher_host(element: ET.Element) -> str:
    source = element.find("source")
    if source is None:
        return ""
    try:
        return urlparse(source.get("url") or "").hostname or ""
    except ValueError:
        return ""


def publisher_article(
    symbol: str,
    element: ET.Element,
    universe: set[str],
    publisher_name: str,
) -> dict[str, Any] | None:
    source = element.find("source")
    publisher = (source.text or "").strip() if source is not None else ""
    host = _publisher_host(element).casefold()
    domain = "fireant.vn" if publisher_name == "FireAnt" else "24hmoney.vn"
    expected = "fireant" if publisher_name == "FireAnt" else "24hmoney"
    if not (host == domain or host.endswith(f".{domain}")):
        return None
    if re.sub(r"\W+", "", publisher.casefold()) != expected:
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
        "publisher": publisher_name,
        "sourceClass": "RUMOR_UNVERIFIED" if speculative else "MAINSTREAM",
        "sourceQuality": .66 if publisher_name == "FireAnt" else .65,
        "event": next(iter(_topics(title)), "GENERAL"),
        "materiality": .63 if _topics(title) else .35,
        "relevance": 1.0,
        "sentimentLabel": label,
        "sentimentScore": sentiment,
        "sourceOrigin": f"https://{domain}",
        "collectionMethod": "PUBLIC_PUBLISHER_ATTRIBUTED_GOOGLE_NEWS_RSS",
    }


def fireant_article(symbol: str, element: ET.Element, universe: set[str]) -> dict[str, Any] | None:
    return publisher_article(symbol, element, universe, "FireAnt")


def money24h_article(symbol: str, element: ET.Element, universe: set[str]) -> dict[str, Any] | None:
    return publisher_article(symbol, element, universe, "24HMoney")


def _fetch_publisher(symbol: str, universe: set[str], publisher: str) -> tuple[str, str, list[dict[str, Any]], str | None]:
    domain = "fireant.vn/bai-viet" if publisher == "FireAnt" else "24hmoney.vn"
    query = quote_plus(f'site:{domain} "{symbol}" when:21d')
    address = f"https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi"
    try:
        request = Request(address, headers={"User-Agent": "Mozilla/5.0 VMEWS-Community-Intelligence/19.0"})
        with urlopen(request, timeout=float(os.environ.get("V18_FIREANT_TIMEOUT", "6"))) as response:
            root = ET.fromstring(response.read())
        return publisher, symbol, [item for element in root.findall(".//item")[:12] if (item := publisher_article(symbol, element, universe, publisher)) is not None], None
    except Exception as error:
        return publisher, symbol, [], f"{type(error).__name__}: {error}"[:120]


def _plain_html(value: str) -> str:
    cleaned = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cleaned))).strip()


def publisher_archive_eligible(item: dict[str, Any]) -> bool:
    """Unverified community posts stay outside the fitted news feature archive."""
    return item.get("collectionMethod") != "PUBLIC_RENDERED_COMMUNITY_POST"


def _relative_publication(raw: str, observed: datetime) -> datetime | None:
    text = _plain_html(raw).casefold()
    if text in {"vừa xong", "vài giây", "mới đây"}:
        return observed
    match = re.search(r"(\d{1,3})\s*(phút|giờ|ngày)", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(minutes=amount) if unit == "phút" else timedelta(hours=amount) if unit == "giờ" else timedelta(days=amount)
        return observed - delta
    if text.startswith("hôm qua"):
        time = re.search(r"(\d{1,2}):(\d{2})", text)
        prior = observed - timedelta(days=1)
        return prior.replace(hour=int(time.group(1)), minute=int(time.group(2)), second=0, microsecond=0) if time else prior
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if match:
        try:
            return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)), int(match.group(4) or 0), int(match.group(5) or 0), tzinfo=VN_TZ)
        except ValueError:
            return None
    return None


def parse_24hmoney_social(document: str, universe: set[str], observed_at: datetime) -> dict[str, Any]:
    """Parse observable post bodies only; quote widgets never identify an issuer."""
    observed = observed_at.astimezone(VN_TZ)
    cards = re.findall(r"<article\b[^>]*class=[\"'][^\"']*article-item-social[^\"']*[\"'][^>]*>(.*?)</article>", document, re.IGNORECASE | re.DOTALL)
    symbols: dict[str, list[dict[str, Any]]] = {}
    market: list[dict[str, Any]] = []
    accepted = 0
    for card in cards:
        posted = re.search(r"class=[\"'][^\"']*post-time[^\"']*[\"'][^>]*>(.*?)<", card, re.IGNORECASE | re.DOTALL)
        timestamp = _relative_publication(posted.group(1), observed) if posted else None
        if timestamp is None or timestamp > observed:
            continue
        author = re.search(r"<a\b[^>]*class=[\"'][^\"']*user-name[^\"']*[\"'][^>]*>(.*?)</a>", card, re.IGNORECASE | re.DOTALL)
        author_name = _plain_html(author.group(1))[:90] if author else "Thành viên 24HMoney"
        descriptions = []
        for anchor in re.finditer(r"<a\b([^>]*)>(.*?)</a>", card, re.IGNORECASE | re.DOTALL):
            attributes, body = anchor.groups()
            if "description_" not in attributes or "/posts/" not in attributes:
                continue
            path = re.search(r"href=[\"']([^\"']*/posts/[^\"']*)[\"']", attributes, re.IGNORECASE)
            content = _plain_html(body)
            if path and content:
                descriptions.append((content, path.group(1)))
        if not descriptions:
            continue
        content, path = max(descriptions, key=lambda item: len(item[0]))
        title = content[:300].rstrip()
        matched = [symbol for symbol in sorted(universe) if security_match(symbol, title, universe, require_explicit=True)]
        label, sentiment = infer_sentiment(title)
        item = {
            "title": title,
            "link": urljoin("https://24hmoney.vn", html.unescape(path)),
            "published": timestamp.isoformat(timespec="seconds"),
            "publisher": "24HMoney",
            "author": author_name,
            "sourceClass": "RUMOR_UNVERIFIED" if SPECULATION.search(title) and _topics(title) else "COMMUNITY_UNVERIFIED",
            "sourceQuality": .46,
            "event": next(iter(_topics(title)), "GENERAL"),
            "materiality": .55 if _topics(title) else .30,
            "relevance": 1.0,
            "sentimentLabel": label,
            "sentimentScore": sentiment,
            "sourceOrigin": "https://24hmoney.vn/social",
            "collectionMethod": "PUBLIC_RENDERED_COMMUNITY_POST",
            "authorVerified": False,
        }
        if matched:
            for symbol in matched[:2]:
                symbols.setdefault(symbol, []).append(dict(item))
            accepted += 1
        else:
            theme = next((name for name, pattern in MARKET_THEMES.items() if pattern.search(title)), "")
            if theme:
                market.append({"title": title[:200], "publisher": "24HMoney", "author": author_name, "publishedAt": item["published"], "link": item["link"], "theme": theme, "verificationState": "UNVERIFIED"})
                accepted += 1
    market.sort(key=lambda row: row["publishedAt"], reverse=True)
    return {"symbols": symbols, "marketContext": market[:15], "observedPosts": len(cards), "acceptedPosts": accepted}


def _fetch_public_social(universe: set[str], observed: datetime) -> tuple[dict[str, Any], str | None]:
    try:
        request = Request("https://24hmoney.vn/social", headers={"User-Agent": "Mozilla/5.0 VMEWS-Community-Intelligence/19.0", "Accept": "text/html"})
        with urlopen(request, timeout=float(os.environ.get("V19_SOCIAL_TIMEOUT", "10"))) as response:
            document = response.read(2_500_000).decode("utf-8", errors="replace")
        return parse_24hmoney_social(document, universe, observed), None
    except Exception as error:
        return {"symbols": {}, "marketContext": [], "observedPosts": 0, "acceptedPosts": 0}, f"{type(error).__name__}: {error}"[:120]


def collect_community() -> dict[str, Any]:
    """Refresh attributed public sources while retaining the last valid archive."""
    source = json.loads((DATA / "research-news-v10.json").read_text(encoding="utf-8"))
    universe = set(source.get("symbols") or {})
    symbols = [symbol for symbol in VN30_CONSTITUENTS if symbol in universe]
    existing: dict[str, Any] = {}
    if FIREANT_PATH.exists():
        try:
            existing = json.loads(FIREANT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            existing = {}
    observed = datetime.now(VN_TZ)
    failures: dict[str, str] = {}
    output = dict(existing.get("symbols") or {})
    successful = 0
    collected: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(symbols) * 2 + 1))) as pool:
        social_future = pool.submit(_fetch_public_social, universe, observed)
        futures = [pool.submit(_fetch_publisher, symbol, universe, publisher) for symbol in symbols for publisher in ("FireAnt", "24HMoney")]
        for future in as_completed(futures):
            publisher, symbol, articles, error = future.result()
            if error:
                failures[f"{publisher}:{symbol}"] = error
                continue
            successful += 1
            collected.setdefault(symbol, []).extend(articles)
        social, social_error = social_future.result()
    if social_error:
        failures["24HMoney:social"] = social_error
    for symbol, articles in social.get("symbols", {}).items():
        if symbol in universe:
            collected.setdefault(symbol, []).extend(articles)
    tracked_symbols = sorted(set(symbols) | set(collected))
    for symbol in tracked_symbols:
        prior = output.get(symbol) or []
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in [*(collected.get(symbol) or []), *prior]:
            identity = hashlib.sha1(str(item.get("title") or "").casefold().encode("utf-8")).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(item)
        merged.sort(key=lambda row: publication_timestamp(row.get("published")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        output[symbol] = merged[:60]
        broad = source.setdefault("symbols", {}).setdefault(symbol, [])
        prior_titles = {str(item.get("title") or "").casefold() for item in broad}
        for item in collected.get(symbol) or []:
            if not publisher_archive_eligible(item):
                continue
            if item["title"].casefold() not in prior_titles:
                broad.append(item)
                prior_titles.add(item["title"].casefold())

    articles_count = sum(len(rows) for rows in output.values())
    counts = {publisher: sum(str(item.get("publisher") or "") == publisher for rows in output.values() for item in rows) for publisher in ("FireAnt", "24HMoney")}
    market_context = social.get("marketContext") or existing.get("marketContext") or []
    payload = {
        "version": "VMEWS-COMMUNITY-INTELLIGENCE-19.0.0",
        "generatedAt": observed.isoformat(timespec="seconds"),
        "status": "ACTIVE" if articles_count else "NO_PUBLIC_PUBLISHER_ARTICLES",
        "publisher": "FireAnt · 24HMoney",
        "publishers": ["FireAnt", "24HMoney"],
        "publisherCounts": counts,
        "collectionMethod": "PUBLIC_ATTRIBUTED_PUBLISHER_RSS_AND_PUBLIC_24HMONEY_POSTS",
        "communityAccess": "PUBLIC_24HMONEY_RENDERED_POSTS_AND_ATTRIBUTED_PUBLISHER_RSS",
        "authenticatedCommunityFeed": False,
        "publicCommunityPosts": int(social.get("acceptedPosts") or 0),
        "observedCommunityPosts": int(social.get("observedPosts") or 0),
        "marketContext": market_context[:15],
        "universe": "VN30_FOCUS_AND_ALL_PUBLIC_HOSE_COMMUNITY_POSTS",
        "requested": len(symbols) * 2,
        "successful": successful,
        "failed": len(failures),
        "articleCount": articles_count,
        "symbols": output,
        "failures": failures,
    }
    FIREANT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if articles_count:
        (DATA / "research-news-v10.json").write_text(json.dumps(source, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {key: value for key, value in payload.items() if key not in {"symbols", "failures", "marketContext"}}


def collect_fireant() -> dict[str, Any]:
    """Backward-compatible entry point; both public publishers are refreshed."""
    return collect_community()


def _live_tick(price: float) -> int:
    return 10 if price < 10_000 else 50 if price < 50_000 else 100


def _live_snap(price: float, mode: str = "nearest") -> int:
    tick = _live_tick(price)
    units = price / tick
    rounded = math.floor(units) if mode == "down" else math.ceil(units) if mode == "up" else math.floor(units + .5)
    candidate = max(tick, int(rounded * tick))
    if candidate % _live_tick(candidate):
        edge_tick = _live_tick(candidate)
        candidate = (candidate // edge_tick) * edge_tick if mode == "down" else math.ceil(candidate / edge_tick) * edge_tick
    return int(candidate)


def _adjusted_horizons(snapshot: dict[str, Any], context: dict[str, Any], observed: datetime) -> dict[str, Any]:
    from forecast_v17_live_intelligence import decision_prior

    close = _float(snapshot.get("close"))
    if close <= 0 or not context.get("inferenceEligible"):
        return {}
    output: dict[str, Any] = {}
    for key, horizon in (snapshot.get("horizons") or {}).items():
        if horizon.get("priceValidated") is not True:
            continue
        prior = decision_prior(snapshot.get("fundContext"), snapshot.get("flow"), snapshot.get("fundamentalContext"), _float(snapshot.get("dailyVolatility"), .02), int(key), news=snapshot.get("decisionNews"), rumor=context)
        previous = horizon.get("liveEvidence") or {}
        delta = prior["totalReturn"] - _float(previous.get("totalReturn"))
        if abs(delta) < 1e-10:
            continue
        lower = _live_snap(close * .93 ** int(key), "up")
        upper = _live_snap(close * 1.07 ** int(key), "down")
        expected = max(lower, min(upper, _live_snap(close * (1.0 + _float(horizon.get("expectedReturn")) + delta))))
        low = max(lower, min(expected, _live_snap(_float(horizon.get("q20Price"), expected) + close * delta, "down")))
        high = min(upper, max(expected, _live_snap(_float(horizon.get("q80Price"), expected) + close * delta, "up")))
        factors = dict(horizon.get("expertContributions") or {})
        for name, amount in prior["components"].items():
            factors[name] = _float(factors.get(name)) + amount - _float((previous.get("components") or {}).get(name))
        output[key] = {
            "expectedPrice": expected,
            "expectedReturn": expected / close - 1.0,
            "q20Price": low,
            "q80Price": high,
            "tickSize": _live_tick(expected),
            "expertContributions": factors,
            "liveEvidence": prior,
            "liveAdjustment": {"observedAt": observed.isoformat(timespec="seconds"), "deltaReturn": delta, "bounded": True, "qualifiedClaims": int(context.get("claimCount") or 0)},
        }
    return output


def publish_live_overlay() -> dict[str, Any]:
    dashboard = json.loads((DATA / "forecast-dashboard-v12.json").read_text(encoding="utf-8"))
    archive = json.loads((DATA / "research-news-v10.json").read_text(encoding="utf-8"))
    observed = datetime.now(VN_TZ)
    histories = {symbol: dashboard.get("charts", {}).get(symbol) or [{"date": row.get("date"), "rawClose": row.get("close"), "volume": 0}] for symbol, row in dashboard.get("symbols", {}).items()}
    roster = set(dashboard.get("lists", {}).get("vn30", {}).get("symbols") or VN30_CONSTITUENTS)
    source = {}
    if FIREANT_PATH.exists():
        source = json.loads(FIREANT_PATH.read_text(encoding="utf-8"))
    tracked = (roster | set(source.get("symbols") or {})) & set(histories)
    events = community_events([{**article, "symbol": symbol} for symbol in tracked for article in archive.get("symbols", {}).get(symbol, [])])
    claims, audit = rumor_intelligence(events, histories, str(dashboard.get("asOf") or ""), observed.isoformat(timespec="seconds"))
    watchlists = community_watchlist(events, histories, observed.isoformat(timespec="seconds"))
    published = publication_timestamp((dashboard.get("marketForecast") or {}).get("decisionAt"))
    output: dict[str, Any] = {}
    for symbol in sorted(tracked):
        snapshot = dashboard.get("symbols", {}).get(symbol)
        if not snapshot:
            continue
        context = claims.get(symbol) or {}
        watchlist = watchlists.get(symbol) or []
        if not context and not watchlist:
            continue
        fresh = any((stamp := publication_timestamp(item.get("publishedAt"))) is not None and published is not None and stamp > published for claim in context.get("claims", []) for item in claim.get("sourceDetails", []))
        updates = _adjusted_horizons(snapshot, context, observed) if fresh else {}
        output[symbol] = {
            "claims": context.get("claims") or [],
            "watchlist": watchlist,
            "rumorContext": context or snapshot.get("rumorContext") or {},
            "horizons": updates,
            "forecastUpdated": bool(updates),
        }
    payload = {
        "version": "VMEWS-COMMUNITY-LIVE-19.0.0",
        "generatedAt": observed.isoformat(timespec="seconds"),
        "asOf": dashboard.get("asOf"),
        "modelDecisionAt": (dashboard.get("marketForecast") or {}).get("decisionAt"),
        "publishers": source.get("publishers") or ["FireAnt", "24HMoney"],
        "publisherCounts": source.get("publisherCounts") or {},
        "publicCommunityPosts": int(source.get("publicCommunityPosts") or 0),
        "marketContext": (source.get("marketContext") or [])[:10],
        "audit": audit,
        "symbols": output,
        "watchedSymbols": len(output),
        "forecastUpdatedSymbols": sum(bool(item["forecastUpdated"]) for item in output.values()),
        "refreshPolicy": "INTRADAY_PUBLIC_SOURCES; ISSUER_MATCH; INDEPENDENT_CORROBORATION; VOLATILITY_BOUNDED; VALID_HOSE_TICKS",
    }
    COMMUNITY_LIVE_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return {key: value for key, value in payload.items() if key not in {"symbols", "audit", "marketContext"}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-fireant", action="store_true")
    parser.add_argument("--collect-community", action="store_true")
    parser.add_argument("--publish-live", action="store_true")
    arguments = parser.parse_args()
    if arguments.collect_fireant or arguments.collect_community:
        print(json.dumps(collect_community(), ensure_ascii=False))
    if arguments.publish_live:
        print(json.dumps(publish_live_overlay(), ensure_ascii=False))
