"""Conservative news -> economic exposure hypotheses; never a price forecast.

The mechanism taxonomy is intentionally separate from statistically validated
impact evidence. Neither keyword matches nor issuer mentions authorize alerts.
"""
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re
import unicodedata

VERSION = "NEWS-EXPOSURE-RESEARCH-1"
EXPOSURES = {
    "RATE_POLICY": (
        ("BANKING", "Ngân hàng", "FUNDING_COST_AND_NIM", "Chi phí vốn và biên lãi ròng có thể thay đổi theo chiều khác nhau"),
        ("REAL_ESTATE", "Bất động sản", "BORROWING_COST", "Chi phí vay và khả năng hấp thụ vốn"),
        ("SECURITIES", "Chứng khoán", "MARGIN_FUNDING", "Chi phí ký quỹ và hoạt động môi giới"),
    ),
    "FX_MOVEMENT": (
        ("NET_EXPORTERS", "Doanh nghiệp xuất khẩu ròng", "FX_REVENUE", "Doanh thu ngoại tệ, cần xác minh tỷ trọng xuất khẩu"),
        ("NET_IMPORTERS", "Doanh nghiệp nhập khẩu ròng", "FX_INPUT_COST", "Chi phí nguyên liệu nhập khẩu, cần xác minh tỷ trọng nhập khẩu"),
        ("FX_DEBTORS", "Doanh nghiệp vay ngoại tệ", "FX_DEBT", "Nợ ngoại tệ và chính sách phòng hộ, cần số liệu BCTC"),
    ),
    "OIL_PRICE_MOVE": (
        ("UPSTREAM_ENERGY", "Dầu khí thượng nguồn", "OIL_REVENUE", "Doanh thu gắn với dầu, phụ thuộc hợp đồng và cơ cấu sản phẩm"),
        ("AVIATION", "Hàng không", "FUEL_COST", "Chi phí nhiên liệu, phụ thuộc phòng hộ và khả năng chuyển giá"),
        ("TRANSPORT", "Vận tải", "FUEL_COST", "Chi phí nhiên liệu, phụ thuộc tỷ lệ phụ thu"),
    ),
    "TARIFF_TRADE": (
        ("EXPORTERS", "Doanh nghiệp xuất khẩu", "MARKET_ACCESS", "Thuế và khả năng tiếp cận thị trường, cần xác minh thị trường đích"),
        ("IMPORT_DEPENDENT", "Doanh nghiệp phụ thuộc nhập khẩu", "INPUT_TARIFF", "Chi phí đầu vào và xuất xứ, cần xác minh chuỗi cung ứng"),
    ),
}
def fold(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D").lower()

def event_family(row):
    title = fold(row.get("title"))
    text = title + " " + fold(row.get("summary"))
    topics = set(row.get("topics") or [])
    if re.search(r"\b(vo no|pha san|mat kha nang thanh toan|credit default|bankrupt)\b", text):
        return "CREDIT_EVENT"
    if re.search(r"\b(thue quan|thue nhap khau|thue xuat khau|tariff|trade barrier|cam xuat khau|cam nhap khau)\b", text):
        return "TARIFF_TRADE"
    if re.search(r"\b(lai suat|interest rates?|rate cuts?|rate hikes?)\b", text) and re.search(
        r"\b(tang|giam|ha|cat|nang|quyet dinh|dieu chinh|giu nguyen|raise|lower|cut|hike|hold|change)\b", text):
        return "RATE_POLICY"
    if ("fx" in topics or re.search(r"ty gia|exchange rate|usd\s*/\s*vnd|dxy", text)) and re.search(
        r"\b(tang|giam|manh len|yeu di|dieu chinh|bien dong|rise|fall|strengthen|weaken)\b", text):
        return "FX_MOVEMENT"
    if ("oil" in topics or re.search(r"gia dau|oil prices?|brent|wti", text)) and re.search(
        r"\b(tang|giam|lap dinh|rot|leo thang|rise|fall|surge|drop)\b", text):
        return "OIL_PRICE_MOVE"
    if re.search(r"\b(bao cao tai chinh|ket qua kinh doanh|loi nhuan|doanh thu|earnings|profit)\b", text):
        return "EARNINGS"
    if re.search(r"\b(co tuc|chia tach|phat hanh|esop|merger|acquisition|mua ban sap nhap)\b", text):
        return "CORPORATE_ACTION"
    return "UNCLASSIFIED"

def exposure_hypothesis(row):
    """Classify possible transmission channels, not observed economic impacts."""
    family = event_family(row)
    mentioned = []
    for entity in row.get("entityMentions") or []:
        try:
            confidence = float(entity.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        symbol = str(entity.get("symbol") or "").upper()
        if re.fullmatch(r"[A-Z]{3}", symbol) and confidence >= .90:
            mentioned.append(symbol)
    channels = [
        {"exposureClass": group, "label": label, "mechanism": mechanism,
         "condition": condition, "direction": "CONDITIONAL_NOT_ESTABLISHED"}
        for group, label, mechanism, condition in EXPOSURES.get(family, ())
    ]
    return {
        "version": VERSION, "eventFamily": family,
        "directIssuerMentions": sorted(set(mentioned)),
        "candidateSectorMechanisms": channels,
        "evidenceTier": "E0_UNTESTED",
        "verification": "HYPOTHESIS_ONLY",
        "verifiedAffectedSectors": [],
        "verifiedAffectedTickers": [],
        "historicalImpactCertified": False,
        "notificationEligible": False,
    }

def canonical_article_url(url):
    value = str(url or "").strip()
    try:
        p = urlsplit(value)
        if p.scheme not in ("https", "http") or not p.netloc:
            return ""
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")])
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", query, ""))
    except ValueError:
        return ""

def _certified_receipt(row, observed_at):
    if row.get("collectorFirstSeenBasis") != "COLLECTOR_RECEIPT":
        return None
    try:
        dt = datetime.fromisoformat(str(row.get("collectorFirstSeenAt") or "").replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.astimezone(timezone.utc) > observed_at:
            return None
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

def attach_collector_receipts(fetched, retained, collected_at):
    """Assign actual collector receipt; NEVER infer first-seen from publishedAt.

    Legacy rows already present before this feature have unknown first-seen
    and cannot acquire a fabricated history when fetched again.
    """
    if collected_at.tzinfo is None:
        raise ValueError("collector receipt must be timezone-aware")
    now = collected_at.astimezone(timezone.utc)
    old_by_url = {}
    for previous in retained:
        key = canonical_article_url(previous.get("url"))
        if key:
            old_by_url[key] = previous
    result = []
    for row in fetched:
        copy = dict(row)
        key = canonical_article_url(copy.get("url"))
        prev = old_by_url.get(key) if key else None
        if prev is not None:
            first = _certified_receipt(prev, now)
            copy["collectorFirstSeenAt"] = first
            copy["collectorFirstSeenBasis"] = "COLLECTOR_RECEIPT" if first else "LEGACY_UNCERTIFIED"
        else:
            copy["collectorFirstSeenAt"] = now.isoformat()
            copy["collectorFirstSeenBasis"] = "COLLECTOR_RECEIPT"
        result.append(copy)
    for row in retained:
        copy = dict(row)
        if _certified_receipt(copy, now) is None:
            copy["collectorFirstSeenAt"] = None
            copy["collectorFirstSeenBasis"] = "LEGACY_UNCERTIFIED"
        result.append(copy)
    return result
