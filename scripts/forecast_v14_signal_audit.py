"""Point-in-time news and institutional-flow features for Vietnam equities.

Publication timestamps, security identity and source availability are treated as
data, not presentation details.  Realized post-event returns are intentionally
excluded from every feature and are reserved for independent event studies.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
MARKET_CLOSE_HOUR = 15

NEWS_COLUMNS = [
    "news_sentiment1", "news_sentiment5", "news_sentiment20", "news_count1",
    "news_count5", "news_materiality5", "news_credibility5", "news_novelty5",
    "news_positive5", "news_negative5", "news_official5", "news_rumor5",
    "news_earnings5", "news_regulatory5", "news_ownership5",
    "news_flow_event5", "news_sentiment_acceleration", "news_days_since",
]
FLOW_COLUMNS = [
    "flow_foreign_imbalance1", "flow_foreign_imbalance5",
    "flow_foreign_imbalance20", "flow_foreign_turnover1",
    "flow_foreign_z20", "flow_prop_imbalance1", "flow_prop_imbalance5",
    "flow_prop_z20", "flow_foreign_available", "flow_prop_available",
    "flow_days_since",
]

POSITIVE_TERMS = (
    "tăng trưởng", "tăng mạnh", "bứt phá", "vượt kế hoạch", "lợi nhuận tăng",
    "lãi tăng", "kỷ lục", "trúng thầu", "mua ròng", "nâng hạng", "khởi sắc",
    "cổ tức", "hồi phục", "tích cực", "mở rộng", "được phê duyệt", "hoàn thành",
)
NEGATIVE_TERMS = (
    "giảm mạnh", "lao dốc", "bán tháo", "thua lỗ", "lỗ ròng", "lợi nhuận giảm",
    "bán ròng", "xả hàng", "vi phạm", "xử phạt", "khởi tố", "điều tra",
    "cảnh báo", "đình chỉ", "hủy niêm yết", "rủi ro", "suy giảm", "nợ xấu",
    "mất giá", "bốc hơi", "phá sản", "thanh tra", "tin đồn",
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def publication_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 and RSS timestamps without discarding their timezone."""
    if not value:
        return None
    text = str(value).strip()
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            timestamp = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=VN_TZ)
    return timestamp.astimezone(VN_TZ)


def effective_trading_session(timestamp: datetime) -> str:
    """An article after the 15:00 close is eligible only next trading day."""
    local = timestamp.astimezone(VN_TZ)
    session = local.date()
    if (local.hour, local.minute, local.second) >= (MARKET_CLOSE_HOUR, 0, 0):
        session += timedelta(days=1)
    while session.weekday() >= 5:
        session += timedelta(days=1)
    return session.isoformat()


def security_match(symbol: str, title: str, universe: set[str]) -> bool:
    """Reject subsidiary/affiliate articles incorrectly bucketed under a parent."""
    symbol = symbol.upper()
    text = str(title or "")
    explicit = [
        item.upper()
        for item in re.findall(r"\(([A-Z][A-Z0-9]{2,4})\)", text)
        if item.upper() in universe
    ]
    if explicit and symbol not in explicit:
        return False
    # Google News commonly routes FPT Retail / FPT Securities to the FPT query;
    # those are FRT and FTS, not the FPT common share being forecast.
    aliases: dict[str, tuple[tuple[str, str], ...]] = {
        "FPT": (
            (r"\bfpt\s+retail\b|\bfpt\s+long\s+châu\b", "FRT"),
            (r"\bchứng\s+khoán\s+fpt\b", "FTS"),
            (r"\bfpt\s+online\b", "FOC"),
        ),
    }
    for pattern, other in aliases.get(symbol, ()):
        if re.search(pattern, text, flags=re.IGNORECASE) and other != symbol:
            return False
    # Articles without an exact ticker can be issuer announcements already
    # linked by the audited historical archive; keep those records.
    return True


def infer_sentiment(title: str) -> tuple[str, float]:
    text = str(title or "").casefold()
    positive = sum(term in text for term in POSITIVE_TERMS)
    negative = sum(term in text for term in NEGATIVE_TERMS)
    if positive > negative:
        return "POS", min(1.0, .42 + .18 * (positive - negative))
    if negative > positive:
        return "NEG", -min(1.0, .42 + .18 * (negative - positive))
    return "NEU", 0.0


def _normalize_event(value: Any, title: str = "") -> str:
    direct = str(value or "GENERAL").upper().replace(" ", "_")
    aliases = {
        "CORPORATEACTION": "CORPORATE_ACTION",
        "CAPITAL_/_CORPORATE_ACTION": "CORPORATE_ACTION",
        "REGULATORY_/_LEGAL": "REGULATORY",
        "OWNERSHIP_/_GOVERNANCE": "OWNERSHIP",
        "FINANCING_/_LEVERAGE": "FINANCING",
        "OPERATIONS_/_M&A": "OPERATIONS_MA",
        "M&A": "OPERATIONS_MA",
    }
    direct = aliases.get(direct, direct)
    lower = str(title).casefold()
    if direct == "GENERAL" and any(term in lower for term in ("lợi nhuận", "doanh thu", "báo cáo tài chính", "bán niên")):
        return "EARNINGS"
    if direct == "GENERAL" and any(term in lower for term in ("mua ròng", "bán ròng", "tự doanh", "khối ngoại")):
        return "MARKET_FLOW"
    return direct


def _title_identity(title: str) -> str:
    cleaned = re.sub(r"\W+", " ", str(title or "").casefold()).strip()
    return hashlib.sha1(cleaned.encode("utf-8")).hexdigest()


def load_signal_sources(universe: set[str]) -> tuple[pd.DataFrame, dict[str, list[dict[str, Any]]], dict[str, Any]]:
    archive = json.loads((DATA / "event-intelligence-v12.json").read_text(encoding="utf-8"))
    recent = json.loads((DATA / "research-news.json").read_text(encoding="utf-8"))
    broad_news = json.loads((DATA / "research-news-v10.json").read_text(encoding="utf-8"))
    flow = json.loads((DATA / "flow-v12.json").read_text(encoding="utf-8"))
    accepted: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()

    def accept(symbol: str, item: dict[str, Any], *, historical: bool) -> None:
        symbol = symbol.upper()
        if symbol not in universe:
            rejected["outside_hose_universe"] += 1
            return
        title = str(item.get("title") or "").strip()
        if not title:
            rejected["missing_title"] += 1
            return
        if not security_match(symbol, title, universe):
            rejected["issuer_mismatch"] += 1
            return
        timestamp = publication_timestamp(item.get("publishedAt") or item.get("published"))
        if timestamp is None:
            rejected["missing_publication_timestamp"] += 1
            return
        identity = (symbol, _title_identity(title))
        if identity in seen:
            rejected["duplicate_symbol_headline"] += 1
            return
        seen.add(identity)
        session = effective_trading_session(timestamp)
        archived_session = str(item.get("availableDate") or "")[:10]
        if historical and archived_session and archived_session > session:
            session = archived_session
        label, score = infer_sentiment(title)
        if historical:
            label = str(item.get("sentimentLabel") or label).upper()
            score = _number(item.get("sentimentScore"), score)
        source_type = str(item.get("sourceType") or item.get("sourceClass") or "NARRATIVE").upper()
        accepted.append(
            {
                "symbol": symbol,
                "date": pd.Timestamp(session),
                "publishedAt": timestamp.isoformat(),
                "title": title,
                "link": str(item.get("link") or ""),
                "publisher": str(item.get("source") or item.get("publisher") or ""),
                "eventType": _normalize_event(item.get("eventType") or item.get("event"), title),
                "label": label if label in {"POS", "NEG", "NEU"} else "NEU",
                "sentiment": float(np.clip(score, -1, 1)),
                "materiality": float(np.clip(_number(item.get("materialityScore"), _number(item.get("materiality"), .35)), 0, 1)),
                "credibility": float(np.clip(_number(item.get("sourceCredibility"), _number(item.get("sourceQuality"), .6)), 0, 1)),
                "novelty": float(np.clip(_number(item.get("noveltyScore"), 1.0), 0, 1)),
                "sourceType": source_type,
                "historical": historical,
            }
        )

    for event in archive.get("records", []):
        accept(str(event.get("ticker") or ""), event, historical=True)
    for symbol, articles in (recent.get("symbols") or {}).items():
        for article in articles:
            accept(str(symbol), article, historical=False)
    for symbol, articles in (broad_news.get("symbols") or {}).items():
        for article in articles:
            accept(str(symbol), article, historical=False)

    events = pd.DataFrame(accepted)
    if events.empty:
        raise RuntimeError("no point-in-time, correctly linked HOSE news events")
    events.sort_values(["date", "symbol", "publishedAt"], inplace=True)
    metadata = {
        "newsArchiveVersion": archive.get("version"),
        "newsArchiveGeneratedAt": archive.get("generatedAt"),
        "recentNewsGeneratedAt": recent.get("generatedAt"),
        "broadNewsGeneratedAt": broad_news.get("generatedAt"),
        "broadNewsSymbols": len(broad_news.get("symbols", {})),
        "flowArchiveVersion": flow.get("version"),
        "flowArchiveGeneratedAt": flow.get("generatedAt"),
        "acceptedEvents": len(events),
        "historicalEvents": int(events["historical"].sum()),
        "recentEvents": int((~events["historical"]).sum()),
        "newsSymbols": int(events["symbol"].nunique()),
        "flowSymbols": len(flow.get("symbols", {})),
        "rejected": dict(rejected),
        "closeCutoff": "15:00 Asia/Ho_Chi_Minh",
        "afterClosePolicy": "NEXT_TRADING_SESSION",
        "outcomeFieldsUsedAsFeatures": 0,
        "archiveLimitation": "Historical publisher timestamps are preserved, but retrospective RSS retrieval cannot prove historical discovery availability.",
        "accountingPolicy": "Quarterly accounting ratios remain excluded without verified publication timestamps.",
    }
    return events, dict(flow.get("symbols", {})), metadata


def symbol_signal_features(frame: pd.DataFrame, symbol_events: pd.DataFrame, flow_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Join only already-published headlines and completed same-session flows."""
    dates = pd.to_datetime(frame["date"]).reset_index(drop=True)
    result = pd.DataFrame(index=range(len(frame)))

    if len(symbol_events):
        event = symbol_events.copy()
        event["weight"] = event["materiality"] * event["credibility"] * (.65 + .35 * event["novelty"])
        event["weighted_sentiment"] = event["sentiment"] * event["weight"]
        event["positive"] = (event["label"] == "POS").astype(float)
        event["negative"] = (event["label"] == "NEG").astype(float)
        event["official"] = event["sourceType"].str.contains("OFFICIAL", na=False).astype(float)
        event["rumor"] = event["sourceType"].str.contains("RUMOR", na=False).astype(float)
        for event_type in ("EARNINGS", "REGULATORY", "OWNERSHIP", "MARKET_FLOW"):
            event[event_type.lower()] = (event["eventType"] == event_type).astype(float)
        grouped = event.groupby("date", observed=True).agg(
            weighted_sentiment=("weighted_sentiment", "sum"),
            weight=("weight", "sum"),
            count=("title", "size"),
            materiality=("materiality", "mean"),
            credibility=("credibility", "mean"),
            novelty=("novelty", "mean"),
            positive=("positive", "sum"),
            negative=("negative", "sum"),
            official=("official", "sum"),
            rumor=("rumor", "sum"),
            earnings=("earnings", "sum"),
            regulatory=("regulatory", "sum"),
            ownership=("ownership", "sum"),
            market_flow=("market_flow", "sum"),
        )
        aligned = grouped.reindex(pd.DatetimeIndex(dates), fill_value=0).reset_index(drop=True)
    else:
        aligned = pd.DataFrame(0.0, index=range(len(frame)), columns=["weighted_sentiment", "weight", "count", "materiality", "credibility", "novelty", "positive", "negative", "official", "rumor", "earnings", "regulatory", "ownership", "market_flow"])

    weighted = aligned["weighted_sentiment"].astype(float)
    weights = aligned["weight"].astype(float)
    result["news_sentiment1"] = weighted.div(weights.replace(0, np.nan)).fillna(0)
    result["news_sentiment5"] = weighted.rolling(5, min_periods=1).sum().div(weights.rolling(5, min_periods=1).sum().replace(0, np.nan)).fillna(0)
    result["news_sentiment20"] = weighted.rolling(20, min_periods=1).sum().div(weights.rolling(20, min_periods=1).sum().replace(0, np.nan)).fillna(0)
    result["news_count1"] = aligned["count"]
    result["news_count5"] = aligned["count"].rolling(5, min_periods=1).sum()
    for source, destination in (("materiality", "news_materiality5"), ("credibility", "news_credibility5"), ("novelty", "news_novelty5")):
        active = aligned[source].where(aligned["count"] > 0)
        result[destination] = active.rolling(5, min_periods=1).mean().fillna(0)
    for source, destination in (("positive", "news_positive5"), ("negative", "news_negative5"), ("official", "news_official5"), ("rumor", "news_rumor5"), ("earnings", "news_earnings5"), ("regulatory", "news_regulatory5"), ("ownership", "news_ownership5"), ("market_flow", "news_flow_event5")):
        result[destination] = aligned[source].rolling(5, min_periods=1).sum()
    result["news_sentiment_acceleration"] = result["news_sentiment5"] - result["news_sentiment20"]
    positions = np.arange(len(frame))
    last_event = np.where(aligned["count"].to_numpy() > 0, positions, np.nan)
    last_event = pd.Series(last_event).ffill()
    result["news_days_since"] = (positions - last_event).clip(upper=60).fillna(60)

    flow = pd.DataFrame(flow_rows)
    if len(flow) and "date" in flow:
        flow["date"] = pd.to_datetime(flow["date"], errors="coerce")
        flow = flow.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
        flow = flow.set_index("date").reindex(pd.DatetimeIndex(dates)).reset_index(drop=True)
    else:
        flow = pd.DataFrame(index=range(len(frame)))

    def numeric(name: str) -> pd.Series:
        return pd.to_numeric(flow.get(name, pd.Series(np.nan, index=flow.index)), errors="coerce")

    foreign_buy, foreign_sell, foreign_net = numeric("foreignBuyValue"), numeric("foreignSellValue"), numeric("foreignNetValue")
    prop_buy, prop_sell, prop_net = numeric("propBuyValue"), numeric("propSellValue"), numeric("propNetValue")
    foreign_present = foreign_net.notna()
    prop_present = prop_net.notna()
    foreign_imbalance = foreign_net.div((foreign_buy.abs() + foreign_sell.abs()).replace(0, np.nan)).clip(-1, 1)
    prop_imbalance = prop_net.div((prop_buy.abs() + prop_sell.abs()).replace(0, np.nan)).clip(-1, 1)
    turnover = pd.to_numeric(frame["close"], errors="coerce").reset_index(drop=True) * pd.to_numeric(frame["volume"], errors="coerce").reset_index(drop=True)
    result["flow_foreign_imbalance1"] = foreign_imbalance
    result["flow_foreign_imbalance5"] = foreign_imbalance.rolling(5, min_periods=2).mean()
    result["flow_foreign_imbalance20"] = foreign_imbalance.rolling(20, min_periods=5).mean()
    result["flow_foreign_turnover1"] = foreign_net.div(turnover.replace(0, np.nan)).clip(-1, 1)
    result["flow_foreign_z20"] = foreign_net.sub(foreign_net.rolling(20, min_periods=8).mean()).div(foreign_net.rolling(20, min_periods=8).std().replace(0, np.nan)).clip(-5, 5)
    result["flow_prop_imbalance1"] = prop_imbalance
    result["flow_prop_imbalance5"] = prop_imbalance.rolling(5, min_periods=2).mean()
    result["flow_prop_z20"] = prop_net.sub(prop_net.rolling(20, min_periods=8).mean()).div(prop_net.rolling(20, min_periods=8).std().replace(0, np.nan)).clip(-5, 5)
    result["flow_foreign_available"] = foreign_present.astype(float)
    result["flow_prop_available"] = prop_present.astype(float)
    last_flow = pd.Series(np.where(foreign_present | prop_present, positions, np.nan)).ffill()
    result["flow_days_since"] = (positions - last_flow).clip(upper=60).fillna(60)
    # Never present old institutional activity as fresh evidence.
    stale = result["flow_days_since"] > 3
    result.loc[stale, [name for name in FLOW_COLUMNS if name not in {"flow_foreign_available", "flow_prop_available", "flow_days_since"}]] = np.nan
    return result


def latest_evidence(symbol_events: pd.DataFrame, as_of: str, limit: int = 12) -> list[dict[str, Any]]:
    cutoff = pd.Timestamp(as_of)
    eligible = symbol_events.loc[symbol_events["date"] <= cutoff].tail(limit).iloc[::-1]
    return [
        {
            "title": row["title"],
            "link": row["link"],
            "publishedAt": row["publishedAt"],
            "availableDate": str(row["date"].date()),
            "publisher": row["publisher"],
            "event": row["eventType"],
            "label": row["label"],
            "sentimentScore": float(row["sentiment"]),
            "materiality": float(row["materiality"]),
            "sourceCredibility": float(row["credibility"]),
            "sourceClass": row["sourceType"],
        }
        for _, row in eligible.iterrows()
    ]
