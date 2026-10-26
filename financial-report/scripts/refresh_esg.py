"""Config-driven corporate ESG discovery and extraction for FinQuery.

The collector keeps a registry of official issuer/provider source pages, discovers
new sustainability/annual-report documents, extracts common ESG KPI mentions,
and preserves provenance. It intentionally does not manufacture a composite ESG
score because provider methodologies are not comparable.
"""
import argparse
import hashlib
import io
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/esg_sources.json"
CORE_COMPANIES = ROOT / "data/companies.json"
GENERIC_DISCLOSURE_TEMPLATE = "https://24hmoney.vn/stock/{symbol}/report"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
HISTORY_BACKFILL = os.environ.get("ESG_HISTORY_BACKFILL", "0") == "1"
DEFAULT_DOC_BYTES = (96 if HISTORY_BACKFILL else 35) * 1024 * 1024
MAX_DOC_BYTES = int(os.environ.get("ESG_MAX_DOC_BYTES", str(DEFAULT_DOC_BYTES)))
MAX_TEXT_CHARS = int(os.environ.get("ESG_MAX_TEXT_CHARS", "900000"))
MAX_PDF_PAGES = int(os.environ.get("ESG_MAX_PDF_PAGES", "280"))
DOCS_PER_RUN = int(os.environ.get("ESG_DOCS_PER_RUN", "24"))
HISTORY_DOCS_PER_RUN = int(os.environ.get("ESG_HISTORY_DOCS_PER_RUN", "10"))
RECENT_YEARS = int(os.environ.get("ESG_RECENT_YEARS", "4"))
DISCOVERY_TIMEOUT = int(os.environ.get("ESG_DISCOVERY_TIMEOUT", "8"))
DETAIL_TIMEOUT = int(os.environ.get("ESG_DETAIL_TIMEOUT", "6"))
DOCUMENT_TIMEOUT = int(os.environ.get("ESG_DOCUMENT_TIMEOUT", "22"))
EXTRACTOR_VERSION = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_company_registry(config):
    """Return all FinQuery Core 100 issuers with official sources preferred.

    The curated bank registry keeps issuer-direct URLs and verified overrides.
    Every remaining Core issuer receives a deterministic public disclosure-index
    fallback so Corporate ESG is available across the whole Core universe.
    """
    core = read(CORE_COMPANIES, [])
    symbols = {str(row.get("symbol") or "").strip().upper() for row in core}
    symbols.discard("")
    if len(symbols) != 100:
        raise RuntimeError(f"Expected 100 Core companies, got {len(symbols)}")

    banks = config.get("banks", {})
    companies_cfg = config.get("companies", {})
    curated = {**companies_cfg, **banks}
    out = {}
    for item in core:
        symbol = str(item.get("symbol") or "").strip().upper()
        cfg = dict(curated.get(symbol, {}))
        cfg["name"] = cfg.get("name") or item.get("name") or symbol
        aliases = list(cfg.get("aliases", []))
        for alias in (symbol, item.get("name")):
            if alias and alias not in aliases:
                aliases.append(alias)
        cfg["aliases"] = aliases
        seeds = list(cfg.get("seed_urls", []))
        generic = GENERIC_DISCLOSURE_TEMPLATE.format(symbol=symbol.lower())
        if generic not in seeds:
            seeds.append(generic)
        cfg["seed_urls"] = seeds
        cfg["entityType"] = "bank" if symbol in banks else "company"
        cfg["sourcePolicy"] = "curated+disclosure-index" if symbol in curated else "disclosure-index"
        out[symbol] = cfg
    return out


def normalize_url(url):
    """Percent-encode unsafe URL characters without double-encoding existing escapes."""
    parts = urlsplit(str(url or "").strip())
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="=&%:@/?+,-._~")
    fragment = quote(parts.fragment, safe="%:@/?+,-._~")
    return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))

def fetch(url, timeout=25):
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    referer = f"{parts.scheme}://{parts.netloc}/" if parts.scheme and parts.netloc else normalized_url
    req = Request(normalized_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
        "Cache-Control": "no-cache",
    })
    with urlopen(req, timeout=timeout) as response:
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_DOC_BYTES:
                    raise ValueError(f"document too large > {MAX_DOC_BYTES} bytes")
            except ValueError as exc:
                if str(exc).startswith("document too large"):
                    raise
        raw = response.read(MAX_DOC_BYTES + 1)
        if len(raw) > MAX_DOC_BYTES:
            raise ValueError(f"document too large > {MAX_DOC_BYTES} bytes")
        return raw, response.headers.get("Content-Type", ""), response.geturl()


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self._href = attrs.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def ascii_fold(text):
    folded = "".join(c for c in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(c)).lower()
    return folded.replace("\u0111", "d")


def strip_html(raw):
    text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return clean_text(unescape(text))


def looks_pdf(url, ctype=""):
    return ".pdf" in urlsplit(url).path.lower() or "application/pdf" in ctype.lower()


def extract_year(text):
    """Prefer the first year in a report title/URL as the reporting year.

    Archive labels commonly look like "Sustainability Report 2025 - published
    2026"; taking the newest number would incorrectly move 2025 KPIs into 2026.
    """
    years = [int(x) for x in re.findall(r"\b(20[0-3]\d)\b", str(text or ""))]
    return years[0] if years else None


def classify_document(text):
    s = re.sub(r"[-_/]+", " ", ascii_fold(text))
    # A sustainability report can discuss green-bond frameworks and annual
    # reporting; the explicit report label is therefore the strongest signal.
    compact = re.sub(r"[^a-z0-9]+", "", s)
    if "sustainability report" in s or "bao cao phat trien ben vung" in s or "esg report" in s or "esgreport" in compact:
        return "sustainability_report"
    if "annual report" in s or "bao cao thuong nien" in s or re.search(r"\bbctn\b", s):
        return "annual_report"
    if "second party opinion" in s or "green bond framework" in s or "sustainable finance framework" in s:
        return "sustainable_finance_assessment"
    if "tcfd" in s or "ifrs s2" in s or ("climate" in s and "disclosure" in s):
        return "climate_disclosure"
    if "vnsi" in s:
        return "vnsi"
    if "susba" in s or "sustainable banking assessment" in s:
        return "susba"
    if "sustainability" in s or "phat trien ben vung" in s or re.search(r"\besg\b", s):
        return "esg_web_content"
    return "esg_other"


def explicit_report_year_hint(title):
    """Return a year only when the document title itself explicitly labels the report."""
    raw = clean_text(title)
    folded = ascii_fold(raw)
    patterns = [
        r"(?:annual\s+report|sustainability\s+report|esg\s+report)[^0-9]{0,24}(20[0-3]\d)",
        r"(?:bao\s+cao\s+thuong\s+nien|bao\s+cao\s+phat\s+trien\s+ben\s+vung)[^0-9]{0,24}(20[0-3]\d)",
        r"(?:^|[^a-z0-9])bctn[^0-9]{0,24}(20[0-3]\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, folded, re.I)
        if match:
            return int(match.group(1))
    return None


def infer_report_year(text, fallback=None, title=None):
    """Prefer an explicit report-title year, then a year tied to the disclosure body."""
    title_year = explicit_report_year_hint(title or "")
    if title_year is not None:
        return title_year
    sample = clean_text(text[:50000])
    patterns = [
        r"(?:Sustainability|ESG|Annual)\s+Report\s+(20[0-3]\d)",
        r"(20[0-3]\d)\s+(?:Sustainability|ESG|Annual)\s+Report",
        r"Báo\s+cáo\s+(?:phát\s+triển\s+bền\s+vững|thường\s+niên)[^\d]{0,30}(20[0-3]\d)",
        r"(?:reporting|financial)\s+(?:year|period)[^\d]{0,20}(20[0-3]\d)",
        r"(?:Tải\s+báo\s+cáo|Download\s+(?:the\s+)?report)[^\d]{0,20}(20[0-3]\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sample, re.I)
        if match:
            return int(match.group(1))
    return fallback


def metric_document_allowed(doc):
    if doc.get("type") in {"sustainability_report", "annual_report", "climate_disclosure"}:
        return True
    if doc.get("type") == "esg_web_content":
        path = urlsplit(doc.get("url") or "").path.lower()
        noisy = any(x in path for x in ("/giai-thuong", "/award", "/tin-tuc", "/news", "/su-kien"))
        return not noisy
    return False


def relevant(text, keywords):
    s = ascii_fold(text)
    return any(ascii_fold(k) in s for k in keywords)


def parse_links(base_url, raw):
    parser = LinkParser()
    parser.feed(raw.decode("utf-8", "ignore"))
    out = []
    for href, label in parser.links:
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base_url, href)
        if url.startswith(("http://", "https://")):
            out.append((url, clean_text(label)))
    return out


def doc_key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:20]


def discover_seed(seed_url, keywords, max_candidates=36, follow_detail_limit=12):
    documents = {}
    try:
        raw, ctype, final_url = fetch(seed_url, timeout=DISCOVERY_TIMEOUT)
    except Exception as exc:
        return [], {"url": seed_url, "status": "error", "error": str(exc)}
    if looks_pdf(final_url, ctype):
        title = Path(urlsplit(final_url).path).name
        documents[final_url] = {
            "id": doc_key(final_url), "url": final_url, "title": title,
            "sourcePage": seed_url, "year": extract_year(title + " " + final_url),
            "type": classify_document(title + " " + final_url),
        }
        return list(documents.values()), {"url": seed_url, "status": "ok", "documents": 1}

    links = parse_links(final_url, raw)
    html_text = strip_html(raw)
    candidates = []
    for url, label in links:
        combined = f"{label} {url}"
        folded = re.sub(r"[-_/]+", " ", ascii_fold(combined))
        pdf_relevant = looks_pdf(url) and (
            relevant(combined, keywords)
            or re.search(r"\b(?:bao cao|report|sustainab|esg|tcfd|climate|green bond|annual)\b", folded)
        )
        if pdf_relevant or relevant(combined, keywords):
            candidates.append((url, label))
    # Keep bounded; prefer PDFs and newest-looking titles.
    candidates = sorted(
        {(u, t) for u, t in candidates},
        key=lambda x: (0 if looks_pdf(x[0]) else 1, -(extract_year(x[0] + " " + x[1]) or 0))
    )[:max_candidates]

    followed = 0
    for url, label in candidates:
        combined = clean_text(f"{label} {url}")
        if looks_pdf(url):
            documents[url] = {
                "id": doc_key(url), "url": url, "title": label or Path(urlsplit(url).path).name,
                "sourcePage": seed_url, "year": extract_year(combined),
                "type": classify_document(combined),
            }
            continue
        # One-level follow for detail pages that contain the actual PDF.
        if followed >= follow_detail_limit:
            continue
        followed += 1
        try:
            detail_raw, detail_type, detail_final = fetch(url, timeout=DETAIL_TIMEOUT)
            if looks_pdf(detail_final, detail_type):
                documents[detail_final] = {
                    "id": doc_key(detail_final), "url": detail_final, "title": label or Path(urlsplit(detail_final).path).name,
                    "sourcePage": seed_url, "year": extract_year(combined),
                    "type": classify_document(combined),
                }
                continue
            detail_text = strip_html(detail_raw)
            if relevant(combined + " " + detail_text[:5000], keywords):
                documents[detail_final] = {
                    "id": doc_key(detail_final), "url": detail_final, "title": label or clean_text(detail_text[:160]),
                    "sourcePage": seed_url, "year": extract_year(combined + " " + detail_text[:1000]),
                    "type": classify_document(combined + " " + detail_text[:1000]),
                    "contentType": "html",
                }
                parent_kind = classify_document(combined + " " + detail_text[:5000])
                report_parent = parent_kind in {"sustainability_report", "annual_report", "climate_disclosure"}
                generic_followed = 0
                for child, child_label in parse_links(detail_final, detail_raw):
                    child_combined = clean_text(child_label + " " + child)
                    label_fold = ascii_fold(child_label)
                    generic_download = bool(re.search(
                        r"\b(?:here|download|view|pdf|tai|tai ve|tai bao cao|xem|xem bao cao|report|bao cao)\b",
                        label_fold
                    ))
                    if looks_pdf(child) and (relevant(child_combined, keywords) or report_parent or generic_download):
                        documents[child] = {
                            "id": doc_key(child), "url": child, "title": child_label or Path(urlsplit(child).path).name,
                            "sourcePage": detail_final, "year": extract_year(combined + " " + child_combined),
                            "type": classify_document(combined + " " + child_combined),
                        }
                        continue
                    # Some issuer sites expose a generic "here/download" URL that
                    # redirects to a PDF without a .pdf suffix. Probe only a few
                    # such links and only from a page already identified as a report.
                    if report_parent and generic_download and generic_followed < 4:
                        generic_followed += 1
                        try:
                            child_raw, child_type, child_final = fetch(child, timeout=DETAIL_TIMEOUT)
                            if looks_pdf(child_final, child_type) and child_raw.lstrip().startswith(b"%PDF"):
                                documents[child_final] = {
                                    "id": doc_key(child_final), "url": child_final,
                                    "title": child_label or Path(urlsplit(child_final).path).name,
                                    "sourcePage": detail_final,
                                    "year": extract_year(combined + " " + child_combined + " " + child_final),
                                    "type": classify_document(combined + " " + child_combined + " " + child_final),
                                }
                        except Exception:
                            pass
        except Exception:
            # Discovery is best-effort; seed page remains authoritative provenance.
            pass

    # Use the landing page itself only when it does not expose a stable report
    # document/detail link. This prevents a dynamic archive page from consuming
    # extraction slots on every run.
    if not documents and relevant(html_text[:30000], keywords):
        documents[final_url] = {
            "id": doc_key(final_url), "url": final_url,
            "title": clean_text(html_text[:140]) or final_url, "sourcePage": seed_url,
            "year": extract_year(html_text[:3000]), "type": classify_document(html_text[:5000]),
            "contentType": "html",
        }
    return list(documents.values()), {"url": seed_url, "status": "ok", "documents": len(documents)}


def _pdf_text_pypdf(raw):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    parts, size = [], 0
    for page_number, page in enumerate(reader.pages):
        if page_number >= MAX_PDF_PAGES:
            break
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            parts.append(page_text)
            size += len(page_text)
        if size >= MAX_TEXT_CHARS:
            break
    return clean_text(" ".join(parts))[:MAX_TEXT_CHARS]


def _pdf_text_pymupdf(raw):
    import fitz
    doc = fitz.open(stream=raw, filetype="pdf")
    parts, size = [], 0
    try:
        for page_number in range(min(doc.page_count, MAX_PDF_PAGES)):
            try:
                page_text = doc.load_page(page_number).get_text("text") or ""
            except Exception:
                page_text = ""
            if page_text:
                parts.append(page_text)
                size += len(page_text)
            if size >= MAX_TEXT_CHARS:
                break
    finally:
        doc.close()
    return clean_text(" ".join(parts))[:MAX_TEXT_CHARS]


def extract_document_text(url):
    raw, ctype, final_url = fetch(url, timeout=DOCUMENT_TIMEOUT)
    if looks_pdf(final_url, ctype) and raw.lstrip().startswith(b"%PDF"):
        primary_error = None
        text = ""
        try:
            text = _pdf_text_pypdf(raw)
        except Exception as exc:
            primary_error = exc
        # Some annual reports use fonts/layouts that pypdf cannot recover, and
        # some encrypted PDFs require a second engine even when decryption works.
        if len(text) < 200:
            try:
                fallback = _pdf_text_pymupdf(raw)
                if len(fallback) > len(text):
                    text = fallback
            except Exception as fallback_exc:
                if primary_error is not None and not text:
                    raise RuntimeError(f"{primary_error}; PyMuPDF fallback: {fallback_exc}") from fallback_exc
        if primary_error is not None and not text:
            raise primary_error
        return text, final_url, "pdf"
    # Some sites return an HTML download gate from a URL ending in .pdf.
    return strip_html(raw)[:MAX_TEXT_CHARS], final_url, "html"


def parse_number(raw, unit=None):
    s = re.sub(r"[^\d,.\-+]", "", str(raw or "").strip().replace(" ", ""))
    if not s:
        return None
    unit_l = ascii_fold(unit or "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") >= 1:
        if s.count(",") == 1 and len(s.rsplit(",", 1)[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif s.count(".") == 1:
        left, right = s.split(".", 1)
        # Vietnamese disclosures commonly use "." as a thousands separator.
        # Preserve leading-zero decimals (0.220), but normalize 19.321 m3,
        # 7.714 tỷ đồng, etc. to 19,321 / 7,714.
        thousands_units = ("ty dong", "trieu dong", "billion vnd", "million vnd",
                           "tco2e", "kwh", "mwh", "gwh", "m3", "kg", "hour", "gio")
        if len(right) == 3 and left not in {"0", "+0", "-0"} and any(x in unit_l for x in thousands_units + ("ty vnd", "trieu vnd")):
            s = left + right
    try:
        return float(s)
    except ValueError:
        return None


VALUE_RE = re.compile(
    r"(?:(?P<prefix>VND|VNĐ)\s*)?"
    r"(?P<value>[-+]?\d[\d.,]*)\s*"
    r"(?P<unit>nghìn\s+tỷ\s+đồng|tỷ\s+đồng|triệu\s+đồng|trillion|billion|million|"
    r"million\s+VND|billion\s+VND|trillion\s+VND|VND|%|tCO2e|tCO₂e|CO2e|CO₂e|"
    r"kWh|MWh|GWh|m3|m³|kg|tấn|tons?|training\s+hours?|hours?|giờ)?",
    re.I,
)


def normalized_unit(match):
    prefix = clean_text(match.groupdict().get("prefix") or "")
    suffix = clean_text(match.groupdict().get("unit") or "")
    s = ascii_fold(suffix)
    if prefix:
        if s in {"trillion", "billion", "million"}:
            return s + " VND"
        if not suffix:
            return "VND"
    if suffix:
        if s in {"trillion", "billion", "million"} and prefix:
            return s + " VND"
        if s.startswith("training hour"):
            return "hours"
        if s in {"gio", "hour", "hours"}:
            return "hours"
        if "co2e" in s:
            return "tCO2e"
        if s == "m3":
            return "m3"
        return suffix
    return None


def unit_family(unit):
    s = ascii_fold(unit or "")
    if not s:
        return None
    if "vnd" in s or "dong" in s:
        return "currency"
    if "%" in s:
        return "percent"
    if "co2e" in s:
        return "emissions"
    if any(x in s for x in ("kwh", "mwh", "gwh")):
        return "energy"
    if s in {"m3", "m³"}:
        return "water"
    if any(x in s for x in ("kg", "tan", "ton")):
        return "mass"
    if "hour" in s or s == "gio":
        return "hours"
    return None


def expected_family(rule):
    return unit_family(rule.get("unit_hint"))


def normalize_metric_value(value, unit, family):
    if value is None:
        return None, unit
    s = ascii_fold(unit or "")
    if family == "currency":
        if "nghin ty" in s or "trillion vnd" in s:
            return value * 1000, "billion VND"
        if "ty dong" in s or "ty vnd" in s or "billion vnd" in s:
            return value, "billion VND"
        if "trieu dong" in s or "trieu vnd" in s or "million vnd" in s:
            return value / 1000, "billion VND"
        if s == "vnd":
            return value / 1_000_000_000, "billion VND"
    if family == "energy":
        if "gwh" in s:
            return value * 1_000_000, "kWh"
        if "mwh" in s:
            return value * 1000, "kWh"
        return value, "kWh"
    if family == "mass":
        if "tan" in s or "ton" in s:
            return value * 1000, "kg"
        return value, "kg"
    if family == "emissions":
        return value, "tCO2e"
    if family == "water":
        return value, "m3"
    if family == "hours":
        return value, "hours"
    if family == "percent":
        return value, "%"
    return value, unit


def candidate_from_match(match, rule, distance, alias, report_year, implicit_alias_unit=False):
    explicit_unit = normalized_unit(match)
    family = expected_family(rule)
    unit = explicit_unit
    if not unit and implicit_alias_unit and distance <= 18:
        unit = rule.get("unit_hint")
    detected_family = unit_family(unit)
    if not detected_family or (family and detected_family != family):
        return None
    value = parse_number(match.group("value"), unit)
    raw_digits = re.sub(r"\D", "", match.group("value"))
    if value is None:
        return None
    if len(raw_digits) == 4 and 1990 <= value <= 2039 and not explicit_unit:
        return None
    value, unit = normalize_metric_value(value, unit, family)
    if value is None or not (float("-inf") < value < float("inf")):
        return None
    if family == "percent" and not (0 <= value <= 100):
        return None
    if family in {"currency", "emissions", "energy", "water", "mass", "hours"} and value < 0:
        return None
    score = (110 if implicit_alias_unit else 100) - min(40, distance / 3)
    if explicit_unit:
        score += 8
    return {
        "value": value, "rawValue": match.group("value"), "unit": unit,
        "qualityScore": round(score, 2), "explicitUnit": bool(explicit_unit)
    }


def extract_metrics(text, rules, year, source_url, source_title, source_type=None):
    results = []
    lower = text.lower()
    for rule in rules:
        best = None
        expected = expected_family(rule)
        for alias in rule["aliases"]:
            alias_l = alias.lower()
            start = 0
            while True:
                idx = lower.find(alias_l, start)
                if idx < 0:
                    break
                window_start = max(0, idx - 180)
                window_end = min(len(text), idx + len(alias) + 260)
                snippet = clean_text(text[window_start:window_end])
                snippet_fold = ascii_fold(snippet)
                # Scope 1/2/3 listed together describes a combined boundary, not
                # an individual scope value.
                if rule["id"] in {"scope1", "scope2", "scope3"} and re.search(
                    r"scope\s*1\s*(?:,|and|&)\s*(?:scope\s*)?2|scope\s*1\s*,\s*2\s*(?:,|and)\s*3",
                    snippet_fold
                ):
                    start = idx + len(alias_l)
                    continue
                if rule["id"] == "green_credit":
                    package_context = re.search(r"\b(?:goi|package|program(?:me)?)\s+(?:tin dung xanh|green credit)", snippet_fold)
                    outstanding_context = re.search(r"du no\s+(?:tin dung\s+)?xanh|green credit\s+(?:outstanding|balance|exposure)", snippet_fold)
                    if package_context and not outstanding_context:
                        start = idx + len(alias_l)
                        continue

                candidates = []
                # Scaled hour disclosures such as "1,05 triệu giờ đào tạo" are
                # common in Vietnamese ESG reports and cannot be represented by
                # the generic VALUE_RE alone because the scale sits between the
                # number and the hour unit.
                if expected == "hours":
                    for scaled in re.finditer(
                        r"(?P<value>\d[\d\s.,]*)\s*(?P<scale>triệu|nghìn|million|thousand)\s*(?:giờ|hours?)",
                        snippet, re.I
                    ):
                        value = parse_number(scaled.group("value"), "hours")
                        scale = ascii_fold(scaled.group("scale"))
                        if value is not None:
                            if scale in {"trieu", "million"}:
                                value *= 1_000_000
                            elif scale in {"nghin", "thousand"}:
                                value *= 1_000
                            candidates.append({
                                "value": value,
                                "rawValue": clean_text(scaled.group("value") + " " + scaled.group("scale")),
                                "unit": "hours",
                                "qualityScore": 116,
                            })
                after = text[idx + len(alias):window_end]
                alias_has_unit = (
                    expected == "hours" and ("hour" in ascii_fold(alias) or "gio" in ascii_fold(alias))
                )
                for match in list(VALUE_RE.finditer(after))[:10]:
                    candidate = candidate_from_match(
                        match, rule, match.start(), alias, year, implicit_alias_unit=alias_has_unit
                    )
                    if candidate:
                        candidates.append(candidate)

                before = text[window_start:idx]
                before_matches = list(VALUE_RE.finditer(before))[-10:]
                # "respectively/lần lượt" with several same-unit values cannot
                # be mapped safely to one KPI using proximity alone.
                ambiguous_pairing = ("lan luot" in ascii_fold(before[-120:] + text[idx:idx+100])
                                     or "respectively" in ascii_fold(before[-120:] + text[idx:idx+100]))
                if not ambiguous_pairing:
                    for match in before_matches:
                        distance = len(before) - match.end()
                        candidate = candidate_from_match(
                            match, rule, distance, alias, year,
                            implicit_alias_unit=alias_has_unit
                        )
                        if candidate:
                            candidates.append(candidate)

                for candidate in candidates:
                    candidate["metricId"] = rule["id"]
                    candidate["pillar"] = rule["pillar"]
                    candidate["label"] = rule["label"]
                    candidate["year"] = year
                    candidate["sourceUrl"] = source_url
                    candidate["sourceTitle"] = source_title
                    candidate["sourceType"] = source_type
                    candidate["snippet"] = snippet[:500]
                    candidate["confidence"] = "high" if candidate["qualityScore"] >= 100 else "medium"
                    candidate.pop("explicitUnit", None)
                    if best is None or candidate["qualityScore"] > best["qualityScore"]:
                        best = candidate
                start = idx + len(alias_l)
        if best:
            results.append(best)
    return results


def vnsi_membership_context(text):
    s = ascii_fold(text)
    patterns = [
        r"\b(?:included|selected|constituent|member|continued\s+in|remained\s+in|continues\s+in)\b.{0,160}\bvnsi\b",
        r"\bvnsi\b.{0,160}\b(?:included|selected|constituent|member|continued|remained)\b",
        r"\b(?:top\s*20|nam trong|thuoc top|duoc lua chon|duoc chon|tiep tuc thuoc)\b.{0,180}\bvnsi\b",
        r"\bvnsi\b.{0,180}\b(?:top\s*20|nam trong|thuoc top|duoc lua chon|duoc chon)\b",
    ]
    return any(re.search(pattern, s, re.S) for pattern in patterns)


def infer_vnsi_year(text):
    """Infer the reporting year nearest the VNSI evidence phrase."""
    raw = clean_text(text)
    if not raw:
        return None
    marker = raw.lower().find("vnsi")
    years = []
    for match in re.finditer(r"\b(20[0-3]\d)\b", raw):
        year = int(match.group(1))
        distance = abs(match.start() - marker) if marker >= 0 else match.start()
        years.append((distance, -year, year))
    return min(years)[2] if years else None


def assessment_source_score(row):
    path = urlsplit(row.get("sourceUrl") or "").path.lower()
    title = ascii_fold(row.get("sourceTitle") or "")
    score = 0
    if ".pdf" in path:
        score += 40
    if "bao cao phat trien ben vung" in title or "sustainability report" in title:
        score += 30
    if "bao cao thuong nien" in title or "annual report" in title:
        score += 20
    if row.get("year") is not None:
        score += 5
    return score


def sanitize_external_assessments(rows):
    cleaned = []
    for raw_row in rows:
        row = dict(raw_row)
        if row.get("assessmentType") == "VNSI membership":
            if not vnsi_membership_context(row.get("snippet") or ""):
                continue
            if row.get("year") is None:
                inferred = infer_vnsi_year(row.get("snippet") or "")
                if inferred is not None:
                    row["year"] = inferred
                    row["yearInferred"] = True
        cleaned.append(row)

    groups = {}
    for row in cleaned:
        if row.get("assessmentType") != "VNSI membership":
            continue
        key = (
            row.get("provider"),
            row.get("assessmentType"),
            row.get("year"),
            ascii_fold(row.get("value") or ""),
        )
        groups.setdefault(key, []).append(row)

    out, emitted = [], set()
    for row in cleaned:
        if row.get("assessmentType") != "VNSI membership":
            out.append(row)
            continue
        key = (
            row.get("provider"),
            row.get("assessmentType"),
            row.get("year"),
            ascii_fold(row.get("value") or ""),
        )
        if key in emitted:
            continue
        emitted.add(key)
        group = groups[key]
        primary = dict(max(group, key=assessment_source_score))
        evidence, seen_urls = [], set()
        for item in sorted(group, key=assessment_source_score, reverse=True):
            url = item.get("sourceUrl")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            evidence.append({
                "sourceUrl": url,
                "sourceTitle": item.get("sourceTitle"),
            })
        if len(evidence) > 1:
            primary["evidenceCount"] = len(evidence)
            primary["evidenceSources"] = evidence
        out.append(primary)
    return out


def extract_ratings(text, patterns, year, source_url, source_title, provider_hint=None):
    out = []
    for row in patterns:
        if provider_hint and row["provider"] != provider_hint:
            continue
        m = re.search(row["pattern"], text, re.I)
        if not m:
            continue
        start, end = max(0, m.start() - 420), min(len(text), m.end() + 420)
        context = text[start:end]
        context_pattern = row.get("context_pattern")
        if not provider_hint and context_pattern and not re.search(context_pattern, context, re.I):
            continue
        if row.get("type") == "VNSI membership" and not vnsi_membership_context(context):
            continue
        out.append({
            "provider": row["provider"], "assessmentType": row["type"],
            "year": year, "value": clean_text(m.group(0)),
            "sourceUrl": source_url, "sourceTitle": source_title,
            "snippet": clean_text(context)[:700],
            "confidence": "medium",
        })
    return out


def bank_in_text(bank_cfg, text):
    s = ascii_fold(text)
    names = [bank_cfg.get("name", "")] + bank_cfg.get("aliases", [])
    for name in names:
        folded = ascii_fold(name).strip()
        if len(folded) < 3:
            continue
        if re.fullmatch(r"[a-z0-9]{3,4}", folded):
            if re.search(rf"(?<![a-z0-9]){re.escape(folded)}(?![a-z0-9])", s):
                return True
        elif folded in s:
            return True
    return False


def merge_unique(rows, key_fields):
    seen, out = set(), []
    for row in rows:
        key = tuple(str(row.get(k, "")) for k in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


MONEY_TEXT = (
    r"(?P<value>\d[\d\s.,]*\d|\d)\s*"
    r"(?P<unit>nghìn\s+tỷ\s+đồng|tỷ\s+(?:đồng|VND|VNĐ)|triệu\s+đồng|"
    r"trillion\s+VND|billion\s+VND|million\s+VND)"
)


def _apply_money_repair(row, match):
    out = dict(row)
    unit = clean_text(match.group("unit"))
    value = parse_number(match.group("value"), unit)
    value, unit = normalize_metric_value(value, unit, "currency")
    if value is None:
        return row
    out["canonicalizedFromRawValue"] = row.get("rawValue")
    out["rawValue"] = clean_text(match.group("value"))
    out["value"] = value
    out["unit"] = unit
    out["qualityScore"] = max(float(out.get("qualityScore") or 0), 116)
    out["confidence"] = "high"
    out["repaired"] = True
    return out


def _apply_numeric_repair(row, raw_value, unit):
    out = dict(row)
    value = parse_number(raw_value, unit)
    family = unit_family(unit)
    value, normalized = normalize_metric_value(value, unit, family)
    if value is None:
        return row
    out["canonicalizedFromRawValue"] = row.get("rawValue")
    out["rawValue"] = clean_text(raw_value)
    out["value"] = value
    out["unit"] = normalized
    out["qualityScore"] = max(float(out.get("qualityScore") or 0), 116)
    out["confidence"] = "high"
    out["repaired"] = True
    return out


def _raw_context(row, radius=95):
    snippet = clean_text(row.get("snippet") or "")
    raw = clean_text(row.get("rawValue") or "")
    if not snippet or not raw:
        return snippet
    idx = snippet.find(raw)
    if idx < 0:
        compact = raw.replace(" ", "")
        idx = snippet.replace(" ", "").find(compact)
        if idx < 0:
            return snippet
    return snippet[max(0, idx-radius):min(len(snippet), idx+len(raw)+radius)]


def repair_canonical_row(row):
    out = dict(row)
    snippet = clean_text(out.get("snippet") or "")
    metric_id = out.get("metricId")
    year = out.get("year")
    if not snippet:
        return out

    if metric_id == "green_credit":
        bank_specific_after_systemwide = re.search(
            r"TPBank[^.;•]{0,140}?cấp\s+tín\s+dụng\s+xanh[^.;•]{0,180}?"
            r"(?:tổng\s+dư\s+nợ\s+vay\s+và\s+đầu\s+tư\s+TPDN|tổng\s+dư\s+nợ|dư\s+nợ)"
            r"[^.;•]{0,70}?(?:đạt|là|ở\s+mức)\s*" + MONEY_TEXT,
            snippet, re.I
        )
        if bank_specific_after_systemwide:
            return _apply_money_repair(out, bank_specific_after_systemwide)
        tcb_layout = re.search(
            r"(?P<scale>trillion|billion)\s+VND\s*(?P<value>\d[\d.,]*)\s+green\s+credit\s+exposure",
            snippet, re.I
        )
        if tcb_layout:
            fake = re.match(
                r"(?P<value>\d[\d.,]*)\s*(?P<unit>trillion VND|billion VND)",
                tcb_layout.group("value") + " " + tcb_layout.group("scale") + " VND", re.I
            )
            if fake:
                return _apply_money_repair(out, fake)
        direct = re.search(
            r"dư\s+nợ\s+tín\s+dụng\s+xanh.{0,300}?lên\s+đến\s+~?\s*"
            r"(?P<value>\d[\d\s.,]*\d|\d)\s*(?P<unit>tỷ\s+(?:VND|VNĐ|đồng))",
            snippet, re.I | re.S
        )
        if direct:
            return _apply_money_repair(out, direct)
        patterns = [
            r"(?:tổng\s+)?dư\s+nợ\s+tín\s+dụng\s+xanh[^.;•]{0,260}?"
            r"(?:lên\s+đến|lên\s+tới|đạt(?:\s+gần)?|ở\s+mức|khoảng|gần|:)\s*~?\s*" + MONEY_TEXT,
            MONEY_TEXT + r"\s+(?:dư\s+nợ\s+)?tín\s+dụng\s+xanh",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_money_repair(out, m)
        en = re.search(
            r"green\s+credit(?:\s+(?:exposure|outstanding|balance))?[^.;•]{0,260}?"
            r"(?:reached|reaching|stood\s+at|at)\s+(?:a\s+peak\s+of\s+)?"
            r"(?:VND\s*)?(?P<value>\d[\d.,]*)\s*(?P<scale>trillion|billion|million)(?:\s+VND)?",
            snippet, re.I
        )
        if en:
            fake = re.match(
                r"(?P<value>\d[\d.,]*)\s*(?P<unit>trillion VND|billion VND|million VND)",
                en.group("value") + " " + en.group("scale") + " VND", re.I
            )
            if fake:
                return _apply_money_repair(out, fake)

    if metric_id == "sustainable_finance":
        english_bond = re.search(
            r"sustainable\s+finance.{0,220}?VND\s*(?P<value>\d[\d.,]*)\s*"
            r"(?P<scale>trillion|billion|million)\s+(?:green\s+bond|sustainability\s+bond|sustainable\s+bond)",
            snippet, re.I | re.S
        )
        if english_bond:
            fake = re.match(
                r"(?P<value>\d[\d.,]*)\s*(?P<unit>trillion VND|billion VND|million VND)",
                english_bond.group("value") + " " + english_bond.group("scale") + " VND", re.I
            )
            if fake:
                return _apply_money_repair(out, fake)
        reverse_green_bond = re.search(
            r"(?:issued|phát\s+hành)[^.;•]{0,120}?VND\s*(?P<value>\d[\d.,]*)\s*"
            r"(?P<scale>trillion|billion|million)[^.;•]{0,80}?green\s+bonds?",
            snippet, re.I
        )
        if reverse_green_bond:
            fake = re.match(
                r"(?P<value>\d[\d.,]*)\s*(?P<unit>trillion VND|billion VND|million VND)",
                reverse_green_bond.group("value") + " " + reverse_green_bond.group("scale") + " VND", re.I
            )
            if fake:
                return _apply_money_repair(out, fake)
        patterns = [
            r"(?:tài\s+chính\s+bền\s+vững|sustainable\s+finance)[^.;•]{0,120}?" + MONEY_TEXT,
            MONEY_TEXT + r"[^.;•]{0,55}(?:trái\s+phiếu\s+bền\s+vững|sustainability\s+bonds?|sustainable\s+bonds?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_money_repair(out, m)

    if metric_id == "csr_spend":
        total_social = re.search(
            r"(?:tổng\s+(?:ngân\s+sách|số\s+tiền|kinh\s+phí)[^\d.;•]{0,35}|"
            r"con\s+số\s+vàng\s+an\s+sinh\s+xã\s+hội(?:\s+20[0-3]\d)?[^\d.;•]{0,55})"
            r"(?:hơn|gần|khoảng|trên)?\s*(?P<value>\d[\d\s.,]*\d|\d)\s*\+?\s*"
            r"(?P<unit>tỷ\s+(?:đồng|VND|VNĐ)|triệu\s+đồng)",
            snippet, re.I
        )
        if total_social:
            return _apply_money_repair(out, total_social)
        negative = r"dư\s+nợ|cho\s+vay|tín\s+dụng|giải\s+ngân|lợi\s+nhuận|thu\s+nhập|vốn\s+(?:điều\s+lệ|thực\s+góp)|ngân\s+sách\s+nhà\s+nước|thuế|tax"
        positive = r"đóng\s+góp|dành(?:\s+cho)?|chi\s+cho|tài\s+trợ|hỗ\s+trợ|trao\s+tặng|ủng\s+hộ|từ\s+thiện|an\s+sinh|community\s+investment|community\s+development|csr"
        if not re.search(negative, snippet, re.I):
            if year and re.search(r"cộng\s+đồng|an\s+sinh|community|csr", snippet, re.I):
                yearly = re.search(
                    rf"riêng\s+(?:trong\s+)?năm\s+{int(year)}\s*(?:là|đạt|:)\s*" + MONEY_TEXT,
                    snippet, re.I
                )
                if yearly:
                    return _apply_money_repair(out, yearly)
                yearly_action = re.search(
                    rf"riêng\s+(?:trong\s+)?năm\s+{int(year)}[^.;•]{{0,70}}?(?:dành|chi|tài\s+trợ|hỗ\s+trợ|đóng\s+góp)[^.;•]{{0,35}}?" + MONEY_TEXT,
                    snippet, re.I
                )
                if yearly_action:
                    return _apply_money_repair(out, yearly_action)
            patterns = [
                r"(?:nguồn\s+kinh\s+phí|kinh\s+phí)[^.;•]{0,55}?" + MONEY_TEXT + r"[^.;•]{0,35}?(?:từ\s+ngân\s+hàng|do\s+ngân\s+hàng)",
                MONEY_TEXT + rf"[^.;•]{{0,70}}?(?:cộng\s+đồng|community|tài\s+trợ|hỗ\s+trợ|trao\s+tặng|ủng\s+hộ|từ\s+thiện|an\s+sinh)",
                rf"(?:{positive})[^.;•]{{0,100}}?" + MONEY_TEXT,
            ]
            for pattern in patterns:
                m = re.search(pattern, snippet, re.I)
                if m:
                    return _apply_money_repair(out, m)

    if metric_id == "women_workforce_pct":
        patterns = [
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%(?=[^%]{0,120}(?:trong\s+)?(?:lực\s+lượng\s+CBNV|workforce))",
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%\s*(?:nhân\s+sự|nhân\s+viên|CBNV|người\s+lao\s+động|"
            r"employees?|workforce)[^.;•]{0,35}(?:là\s+)?(?:nữ|female|women)",
            r"(?:nữ|female|women)[^.;•]{0,35}?(?:nhân\s+sự|nhân\s+viên|employees?|workforce)"
            r"[^.;•\d]{0,35}(?:chiếm|là|at)?\s*(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%",
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%[^.;•]{0,45}(?:trong\s+)?(?:lực\s+lượng\s+CBNV|workforce)",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_numeric_repair(out, m.group("value"), "%")

    if metric_id in {"women_management_pct", "female_board_pct"}:
        patterns = [
            r"(?:nữ|female|women)\s+(?:quản\s+lý|lãnh\s+đạo|management|leaders?|board)[^.;•\d]{0,30}(?:chiếm|là|at)?\s*(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%",
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%\s*(?:cán\s+bộ\s+quản\s+lý|quản\s+lý|lãnh\s+đạo|"
            r"management|leaders?|board)[^.;•]{0,40}(?:là\s+)?(?:nữ|female|women)",
            r"(?:tỷ\s+lệ\s+)?(?:nữ|female|women)[^.;•]{0,55}?(?:quản\s+lý|lãnh\s+đạo|management|board)"
            r"[^.;•\d]{0,45}(?:chiếm|là|at)?\s*(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*%",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_numeric_repair(out, m.group("value"), "%")

    if metric_id == "training_hours_per_employee":
        patterns = [
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*(?:giờ|hours?)\s*/\s*(?:CBNV|employee)",
            r"(?:số\s+giờ\s+đào\s+tạo\s+trung\s+bình|giờ\s+đào\s+tạo\s+trung\s+bình|"
            r"training\s+hours\s+per\s+employee|average\s+training\s+hours)"
            r"[^.;•]{0,150}?\d+\s*[,\.]?\s*\d*\s*(?:giờ|hours?)\s+"
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*(?:giờ|hours?)",
            r"(?:số\s+giờ\s+đào\s+tạo\s+trung\s+bình|giờ\s+đào\s+tạo\s+trung\s+bình|"
            r"trung\s+bình\s+trên\s+một\s+cán\s+bộ|training\s+hours\s+per\s+employee|"
            r"average\s+training\s+hours)[^.;•]{0,120}?(?:là|đạt|:)\s*"
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*(?:giờ|hours?)",
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*(?:giờ|hours?)[^.;•]{0,20}"
            r"(?:số\s+giờ\s+đào\s+tạo\s+trung\s+bình|average\s+training\s+hours)",
            r"(?P<value>\d+(?:\s*[,\.]\s*\d+)?)\s*(?:giờ\s+học|giờ|hours?)\s*/\s*(?:CBNV|employee)",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_numeric_repair(out, m.group("value"), "hours")

    if metric_id == "electricity":
        m = re.search(
            r"(?:total\s+electricity\s+consumption|tổng\s+(?:lượng\s+)?điện\s+(?:tiêu\s+thụ|sử\s+dụng))"
            r"[^.;•]{0,90}?(?:was|is|đạt|là|:)\s*(?P<value>\d[\d\s.,]*)\s*(?:kWh)",
            snippet, re.I
        )
        if m:
            return _apply_numeric_repair(out, m.group("value"), "kWh")

    if metric_id == "water":
        if year:
            table = re.search(
                rf"{int(year)}\s+{int(year)-1}[^.;•]{{0,140}}?(?:Lượng\s+nước\s+tiêu\s+thụ|water\s+consumption)"
                rf"\s+(?P<value>\d[\d\s.,]*)\s+\d[\d\s.,]*\s*(?:m3|m³)",
                snippet, re.I
            )
            if table:
                return _apply_numeric_repair(out, table.group("value"), "m3")
        m = re.search(
            r"(?:total\s+water\s+consumption|tổng\s+(?:lượng\s+)?nước\s+(?:tiêu\s+thụ|sử\s+dụng))"
            r"[^.;•]{0,90}?(?:was|is|đạt|là|:)\s*(?P<value>\d[\d\s.,]*)\s*(?:m3|m³)",
            snippet, re.I
        )
        if m:
            return _apply_numeric_repair(out, m.group("value"), "m3")

    if metric_id == "paper":
        if year:
            table = re.search(
                rf"{int(year)}\s+{int(year)-1}[^.;•]{{0,140}}?(?:Lượng\s+giấy\s+tiêu\s+thụ|paper\s+consumption)"
                rf"\s+(?P<value>\d[\d\s.,]*)\s+\d[\d\s.,]*\s*(?P<unit>Tấn|tons?|kg)",
                snippet, re.I
            )
            if table:
                unit = "tons" if ascii_fold(table.group("unit")).startswith(("tan","ton")) else "kg"
                return _apply_numeric_repair(out, table.group("value"), unit)

    if metric_id == "electricity":
        if year:
            table = re.search(
                rf"{int(year)}\s+{int(year)-1}[^.;•]{{0,140}}?(?:Lượng\s+điện\s+tiêu\s+thụ|electricity\s+consumption)"
                rf"\s+(?P<value>\d[\d\s.,]*)\s+\d[\d\s.,]*\s*(?:kWh)",
                snippet, re.I
            )
            if table:
                return _apply_numeric_repair(out, table.group("value"), "kWh")

    if metric_id == "training_hours":
        nab_total = re.search(
            r"\d+(?:\s*[,\.]\s*\d+)?\s*(?:giờ|hours?)\s*/\s*(?:CBNV|employee)"
            r"\s+(?P<value>\d[\d\s.,]*)\s*(?:giờ|hours?)[^.;•]{0,100}"
            r"(?:Tổng\s+thời\s+lượng\s+đào\s+tạo|total\s+training\s+duration)",
            snippet, re.I
        )
        if nab_total:
            return _apply_numeric_repair(out, nab_total.group("value"), "hours")
        reverse_total = re.search(
            r"(?P<value>\d[\d\s.,]*)\s*(?:hours?|giờ)\s+"
            r"(?:Total\s+training\s+hours|Tổng\s+số\s+giờ\s+đào\s+tạo)",
            snippet, re.I
        )
        if reverse_total:
            return _apply_numeric_repair(out, reverse_total.group("value"), "hours")
        table = re.search(
            r"(?:số\s+giờ\s+đào\s+tạo|training\s+hours)\s*"
            r"(?P<value>\d[\d\s.,]*)\s*(?:giờ|hours?)"
            r"[^.;•]{0,70}(?:tổng\s+số\s+CBNV|total\s+employees|number\s+of\s+employees)",
            snippet, re.I
        )
        if table:
            return _apply_numeric_repair(out, table.group("value"), "hours")
        patterns = [
            r"(?:a\s+total\s+of|tổng(?:\s+số)?)\s*(?P<value>\d[\d\s.,]*)\s*(?:training\s+hours?|giờ\s+đào\s+tạo)",
            r"(?:tổng\s+số\s+giờ\s+đào\s+tạo)[^.;•]{0,90}?(?:là|đạt|:)\s*(?P<value>\d[\d\s.,]*)\s*(?:giờ)?",
            r"(?P<value>\d[\d\s.,]*)\s*(?:training\s+hours?|giờ\s+đào\s+tạo)[^.;•]{0,35}(?:were\s+recorded|được\s+ghi\s+nhận)",
        ]
        for pattern in patterns:
            m = re.search(pattern, snippet, re.I)
            if m:
                return _apply_numeric_repair(out, m.group("value"), "hours")

    return out


def metric_row_valid(row):
    metric_id = row.get("metricId")
    if row.get("year") is None or row.get("value") is None:
        return False
    snippet = clean_text(row.get("snippet") or "")
    context = _raw_context(row)
    folded = ascii_fold(context)

    # Reject table-of-contents/GRI disclosure codes masquerading as values.
    if metric_id in {"training_hours", "training_hours_per_employee"}:
        if re.search(r"\bGRI\s*404\b", snippet, re.I) and re.search(r"\b404(?:\.1)?\.?\b", str(row.get("rawValue") or "")):
            return False
        bankwide_training = re.search(
            r"overall\s+training|tổng\s+(?:số\s+)?giờ\s+đào\s+tạo(?:\s+trong)?\s+năm|"
            r"total\s+(?:number\s+of\s+)?training\s+hours|"
            r"cung\s+cấp[^.;•]{0,90}(?:triệu|nghìn)?\s*giờ\s+đào\s+tạo[^.;•]{0,50}(?:nhân\s+viên|CBNV)|"
            r"provided[^.;•]{0,90}training\s+hours[^.;•]{0,50}employees?|"
            r"số\s+giờ\s+đào\s+tạo\s+\d[\d\s.,]*\s*(?:giờ|hours?)[^.;•]{0,70}"
            r"(?:tổng\s+số\s+CBNV|total\s+employees|number\s+of\s+employees)",
            snippet, re.I
        )
        if metric_id == "training_hours" and not row.get("repaired") and not bankwide_training:
            return False
        if metric_id == "training_hours" and not bankwide_training:
            return False
        if metric_id == "training_hours_per_employee" and not row.get("repaired"):
            return False
        if metric_id == "training_hours_per_employee" and float(row.get("value") or 0) > 500:
            return False

    if metric_id in {"women_workforce_pct", "women_management_pct", "female_board_pct"} and not row.get("repaired"):
        return False

    if metric_id == "board_independence_pct":
        direct = re.search(
            r"(?:tỷ\s+lệ|percentage|proportion)[^.;•]{0,60}(?:thành\s+viên\s+HĐQT\s+độc\s+lập|independent\s+(?:board|director))"
            r"[^.;•]{0,40}\d+[,.]?\d*\s*%|"
            r"\d+[,.]?\d*\s*%[^.;•]{0,60}(?:thành\s+viên\s+HĐQT\s+độc\s+lập|independent\s+(?:board|director))",
            context, re.I
        )
        if not direct:
            return False

    if metric_id == "green_credit":
        # Reject microscopic currency values caused by a bare VND token being
        # normalized to billion VND (e.g. "VND 1.2" -> 1.2e-9 billion).
        if 0 < float(row.get("value") or 0) < 0.01:
            return False
        if not row.get("repaired") and re.search(
            r"toàn\s+nền\s+kinh\s+tế|dư\s+nợ\s+tín\s+dụng\s+xanh\s+của\s+cả\s+nước|"
            r"system[-\s]?wide|banking\s+system",
            snippet, re.I
        ):
            return False
        if re.search(r"toàn\s+nền\s+kinh\s+tế|system[-\s]?wide|banking\s+system", context, re.I) and not row.get("repaired"):
            return False
        raw_token = re.escape(clean_text(row.get("rawValue") or ""))
        if raw_token and re.search(
            rf"(?:gói\s+tín\s+dụng\s+xanh|green\s+credit\s+(?:package|program(?:me)?))"
            rf"[^.;•]{{0,35}}{raw_token}",
            context, re.I
        ):
            return False
        if not row.get("repaired") and not re.search(r"tín\s+dụng\s+xanh|green\s+credit|dư\s+nợ\s+xanh", context, re.I):
            return False

    if metric_id == "sustainable_finance" and not row.get("repaired"):
        return False

    if metric_id == "csr_spend":
        if re.search(r"ngân\s+sách\s+nhà\s+nước|thuế|tax", context, re.I):
            return False
        if not row.get("repaired"):
            return False

    if metric_id in {"water", "electricity", "paper"}:
        if re.search(
            r"trên\s+mỗi\s+đơn\s+vị\s+doanh\s+thu|per\s+unit\s+of\s+revenue|"
            r"per\s+(?:employee|capita)|/\s*(?:employee|CBNV)|"
            r"(?:kWh|m3|m³)\s*/\s*(?:employee|CBNV)|intensity\s+per\s+revenue|"
            r"/\s*(?:tỷ|triệu)\s+VND",
            context, re.I
        ):
            return False

    if metric_id == "ghg_total":
        if not re.search(
            r"tổng\s+(?:lượng\s+)?phát\s+thải|total\s+(?:ghg|greenhouse\s+gas)?\s*emissions|"
            r"total\s+emissions|tổng\s+phát\s+thải\s+cả\s+3",
            snippet, re.I
        ):
            return False

    if metric_id in {"scope1", "scope2", "scope3", "ghg_total", "water", "electricity"}:
        if re.search(r"riêng\s+hội\s+sở|head\s+office\s+only|only\s+at\s+head\s+office", snippet, re.I):
            return False

    # Medium-confidence generic matches are too risky for the canonical layer.
    if not row.get("repaired") and row.get("confidence") != "high":
        return False
    return True


def canonical_metrics(rows):
    chosen = {}
    for raw_row in rows:
        row = repair_canonical_row(raw_row)
        if not metric_row_valid(row):
            continue
        key = (row["metricId"], row["year"])
        score = float(row.get("qualityScore") or 0)
        if row.get("sourceType") in {"sustainability_report", "annual_report", "climate_disclosure"}:
            score += 8
        if row.get("confidence") == "high":
            score += 4
        if row.get("repaired"):
            score += 8
        current = chosen.get(key)
        if current is None or score > current[0]:
            chosen[key] = (score, row)
    return [item[1] for item in sorted(chosen.values(), key=lambda x: (x[1].get("year") or 0, x[1].get("metricId") or ""))]


def fill_validated_metrics(live_rows, cfg):
    """Fill only missing metric/year keys with source-verified fallback rows."""
    out = [dict(row) for row in live_rows]
    existing = {(row.get("metricId"), row.get("year")) for row in out}
    for raw in (cfg or {}).get("validated_metrics", []):
        row = dict(raw)
        key = (row.get("metricId"), row.get("year"))
        if not all(key) or key in existing:
            continue
        row.setdefault("confidence", "high")
        row.setdefault("qualityScore", 120)
        row["validatedFallback"] = True
        out.append(row)
        existing.add(key)
    return sorted(out, key=lambda x: (x.get("year") or 0, x.get("metricId") or ""))


def fill_validated_assessments(live_rows, cfg):
    """Fill only missing provider/type/year assessment keys with verified fallback rows."""
    out = [dict(row) for row in live_rows]
    existing = {(row.get("provider"), row.get("assessmentType"), row.get("year")) for row in out}
    for raw in (cfg or {}).get("validated_assessments", []):
        row = dict(raw)
        key = (row.get("provider"), row.get("assessmentType"), row.get("year"))
        if not all(key) or key in existing:
            continue
        row["validatedFallback"] = True
        out.append(row)
        existing.add(key)
    return sorted(out, key=lambda x: (x.get("year") or 0, x.get("provider") or "", x.get("assessmentType") or ""))


def reset_document(doc):
    row = dict(doc)
    row["type"] = classify_document((row.get("title") or "") + " " + (row.get("url") or ""))
    for key in ("processedAt", "contentHash", "textLength", "lastError", "lastAttemptAt", "retryAfter", "failedAttempts"):
        row.pop(key, None)
    return row


def revive_transport_failure(doc):
    """Retry documents that failed only because older transport limits were stricter."""
    row = dict(doc)
    error = str(row.get("lastError") or "")
    retry = (
        "URL can't contain control characters" in error
        or "cryptography>=3.1 is required for AES algorithm" in error
        or "PyMuPDF fallback" in error
    )
    match = re.search(r"document too large >\s*(\d+)\s*bytes", error)
    if match and int(match.group(1)) < MAX_DOC_BYTES:
        retry = True
    if retry:
        for key in ("lastError", "lastAttemptAt", "retryAfter", "failedAttempts"):
            row.pop(key, None)
    return row


def corrected_document_year(doc, cfg=None):
    row = dict(doc)
    cfg = cfg or {}
    url = normalize_url(row.get("url"))
    raw_url = row.get("url") or ""
    overrides = cfg.get("year_overrides", {})
    override = overrides.get(url) or overrides.get(raw_url)
    if override is not None:
        row["year"] = int(override)
    else:
        title_year = explicit_report_year_hint(row.get("title") or "")
        if title_year is not None:
            row["year"] = title_year

    type_overrides = cfg.get("type_overrides", {})
    type_override = type_overrides.get(url) or type_overrides.get(raw_url)
    if type_override:
        row["type"] = type_override

    target_reprocess_version = int(cfg.get("reprocess_version") or 0)
    reprocess_urls = {normalize_url(x) for x in cfg.get("reprocess_urls", [])}
    if target_reprocess_version and url in reprocess_urls and int(row.get("reprocessVersion") or 0) < target_reprocess_version:
        for key in ("processedAt", "contentHash", "textLength", "lastError", "lastAttemptAt", "retryAfter", "failedAttempts"):
            row.pop(key, None)
        row["reprocessVersion"] = target_reprocess_version
    return row


def align_rows_to_document_year(rows, documents):
    years = {
        normalize_url(doc.get("url")): doc.get("year")
        for doc in documents
        if doc.get("url") and doc.get("year") is not None
    }
    out = []
    for raw in rows:
        row = dict(raw)
        year = years.get(normalize_url(row.get("sourceUrl")))
        if year is not None:
            row["year"] = year
        out.append(row)
    return out


def esg_document_candidate(doc):
    """Reject listing pages and financial statements; retain real annual/ESG disclosures."""
    title = ascii_fold(doc.get("title") or "")
    url = ascii_fold(doc.get("url") or "")
    source_page = ascii_fold(doc.get("sourcePage") or "")
    text = " ".join([title, url, source_page])

    # Discovery/index pages are useful seeds, never extraction documents.
    path = urlsplit(doc.get("url") or "").path.lower().rstrip("/")
    if re.fullmatch(r"/stock/[^/]+/(?:report|financial-report)", path):
        return False

    # 24HMoney's "Báo cáo tài chính thường niên" means annual financial
    # statements, not the issuer's annual report (BCTN). It is not an ESG source.
    if "/financial-report" in source_page or re.search(
        r"bao cao tai chinh(?:\s+(?:hop nhat|rieng))?\s+thuong nien|"
        r"annual financial statements?|annual financial report",
        title, re.I
    ):
        return False

    positive = bool(re.search(
        r"bao cao thuong nien|bao cao phat trien ben vung|"
        r"annual report|sustainab|\besg\b|climate|tcfd|integrated report|"
        r"green bond|sustainable finance|second party opinion|\bvnsi\b|\bsusba\b",
        text, re.I
    ))
    pure_financial = bool(re.search(
        r"bao cao tai chinh|financial statements?|financial report",
        title, re.I
    )) and not positive
    periodic = bool(re.search(
        r"\b(?:quy\s*[1-4]|quy\s*(?:i|ii|iii|iv)|ban nien|6 thang|9 thang|"
        r"quarter(?:ly)?|half[- ]year|interim)\b",
        title, re.I
    )) and not positive

    return not (pure_financial or periodic)


def migration_keep_document(doc, keywords):
    if not esg_document_candidate(doc):
        return False
    kind = doc.get("type") or classify_document((doc.get("title") or "") + " " + (doc.get("url") or ""))
    path = urlsplit(doc.get("url") or "").path.lower()
    if kind == "esg_web_content" and any(x in path for x in ("/giai-thuong", "/award", "/tin-tuc", "/news", "/su-kien")):
        return False
    if kind == "esg_other":
        return relevant((doc.get("title") or "") + " " + (doc.get("url") or ""), keywords)
    return True


def backlog_bucket(owner, doc, current_year):
    path = urlsplit(doc.get("url") or "").path.lower()
    if owner != "__external__" and doc.get("type") == "esg_web_content" and any(
        token in path for token in ("/giai-thuong", "/award", "/tin-tuc", "/news", "/su-kien")
    ):
        return "skip"
    year = doc.get("year")
    recent_floor = current_year - RECENT_YEARS + 1
    if year is not None and year < recent_floor:
        return "history"
    return "recent"


def backlog_priority(owner, doc):
    priorities = {
        "sustainability_report": 12, "climate_disclosure": 11, "annual_report": 10,
        "sustainable_finance_assessment": 9, "vnsi": 8, "susba": 8,
        "esg_web_content": 6, "esg_other": 2,
    }
    # Bootstrap the company's own disclosure history before provider archives.
    # External ratings remain important but should not consume every bounded
    # extraction slot while bank reports are still waiting.
    base = 5 if owner == "__external__" else priorities.get(doc.get("type"), 1)
    return (base, doc.get("year") or 0)


def collect(config, output):
    previous = read(output / "company-esg.json", {"companies": {}, "externalDocuments": []})
    banks = build_company_registry(config)
    keywords = config["document_keywords"]
    if previous.get("extractorVersion") != EXTRACTOR_VERSION:
        # A stricter extractor must never keep KPI rows produced by an older,
        # more permissive parser. Rebuild from retained source documents.
        for company in previous.get("companies", {}).values():
            company["metrics"] = []
            company["canonicalMetrics"] = []
            company["externalAssessments"] = []
            company["documents"] = [
                reset_document(doc) for doc in company.get("documents", [])
                if migration_keep_document(reset_document(doc), keywords)
            ]
        previous["externalDocuments"] = [
            reset_document(doc) for doc in previous.get("externalDocuments", [])
        ]
    source_status = []
    discovered = {symbol: {} for symbol in banks}

    jobs = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        current_year = datetime.now(timezone.utc).year
        for symbol, cfg in banks.items():
            seeds = list(cfg.get("seed_urls", []))
            for template in cfg.get("year_url_templates", []):
                # Routine runs probe the current and two prior reporting years.
                # Weekend history backfill reaches further back without unbounded discovery.
                probe_years = 5 if HISTORY_BACKFILL else 3
                for year in range(current_year, current_year - probe_years, -1):
                    seeds.append(template.format(year=year))
            bank_candidates, bank_follow = ((32, 8) if HISTORY_BACKFILL else (22, 4))
            for seed in dict.fromkeys(seeds):
                jobs.append((symbol, seed, pool.submit(discover_seed, seed, keywords, bank_candidates, bank_follow)))
        for symbol, seed, future in jobs:
            try:
                docs, status = future.result()
            except Exception as exc:
                docs, status = [], {"url": seed, "status": "error", "error": str(exc)}
            status["symbol"] = symbol
            source_status.append(status)
            for doc in docs:
                doc["url"] = normalize_url(doc.get("url"))
                discovered[symbol][doc["url"]] = doc

    companies = {}
    backlog = []
    for symbol, cfg in banks.items():
        prev = previous.get("companies", {}).get(symbol, {})
        docs = {}
        for old_doc in prev.get("documents", []):
            if not old_doc.get("url") or not esg_document_candidate(old_doc):
                continue
            restored = corrected_document_year(revive_transport_failure(old_doc), cfg)
            restored["url"] = normalize_url(restored.get("url"))
            if not esg_document_candidate(restored):
                continue
            docs[restored["url"]] = restored
        report_types = {"sustainability_report", "annual_report", "climate_disclosure"}
        for url, discovered_doc in discovered[symbol].items():
            if not esg_document_candidate(discovered_doc):
                continue
            existing = docs.get(url, {})
            merged = corrected_document_year({**existing, **discovered_doc}, cfg)
            if not esg_document_candidate(merged):
                continue
            # If a stable URL is newly recognized as an actual report (rather
            # than a framework/detail page), process it again so KPI extraction
            # is not permanently skipped because of an earlier classification.
            if existing.get("processedAt") and existing.get("type") not in report_types and merged.get("type") in report_types:
                for key in ("processedAt", "contentHash", "textLength", "lastError", "lastAttemptAt", "retryAfter", "failedAttempts"):
                    merged.pop(key, None)
            docs[url] = merged
        ordered = sorted(docs.values(), key=lambda d: (d.get("year") or 0, d.get("title") or ""), reverse=True)
        allowed_urls = {normalize_url(d.get("url")) for d in ordered if d.get("url")}
        metrics = [
            row for row in align_rows_to_document_year(prev.get("metrics", []), ordered)
            if normalize_url(row.get("sourceUrl")) in allowed_urls
        ]
        ratings = [
            row for row in align_rows_to_document_year(prev.get("externalAssessments", []), ordered)
            if normalize_url(row.get("sourceUrl")) in allowed_urls
        ]
        for doc in ordered:
            if not doc.get("processedAt"):
                backlog.append((symbol, doc))
        companies[symbol] = {
            "symbol": symbol, "name": cfg["name"], "checkedAt": now(),
            "entityType": cfg.get("entityType", "company"), "sourcePolicy": cfg.get("sourcePolicy"),
            "documents": ordered, "metrics": metrics, "externalAssessments": ratings,
        }

    # External provider discovery.
    external_docs = {}
    for old_doc in previous.get("externalDocuments", []):
        if not old_doc.get("url"):
            continue
        restored = revive_transport_failure(old_doc)
        restored["url"] = normalize_url(restored.get("url"))
        external_docs[restored["url"]] = restored
    ext_jobs = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        ext_candidates, ext_follow = ((16, 6) if HISTORY_BACKFILL else (8, 2))
        for src in config.get("external_sources", []):
            for seed in src.get("seed_urls", []):
                ext_jobs.append((src, seed, pool.submit(discover_seed, seed, keywords, ext_candidates, ext_follow)))
        for src, seed, future in ext_jobs:
            try:
                docs, status = future.result()
            except Exception as exc:
                docs, status = [], {"url": seed, "status": "error", "error": str(exc)}
            status.update({"provider": src["provider"], "external": True})
            source_status.append(status)
            for doc in docs:
                doc["provider"] = src["provider"]
                doc["externalKind"] = src["kind"]
                doc["url"] = normalize_url(doc.get("url"))
                external_docs[doc["url"]] = {**external_docs.get(doc["url"], {}), **doc}
    for doc in external_docs.values():
        if not doc.get("processedAt"):
            backlog.append(("__external__", doc))

    # Bounded, parallel processing so a historical bootstrap cannot block the
    # market publisher. Failed documents back off for 24h instead of consuming
    # every subsequent run.
    current = datetime.now(timezone.utc)
    eligible_backlog = []
    recent_backlog = []
    historical_backlog = []
    skipped_backlog = []
    current_year = current.year
    for owner, doc in backlog:
        retry_after = doc.get("retryAfter")
        try:
            blocked = retry_after and datetime.fromisoformat(retry_after) > current
        except (ValueError, TypeError):
            blocked = False
        if blocked:
            continue
        eligible_backlog.append((owner, doc))
        bucket = backlog_bucket(owner, doc, current_year)
        if bucket == "recent":
            recent_backlog.append((owner, doc))
        elif bucket == "history":
            historical_backlog.append((owner, doc))
        else:
            skipped_backlog.append((owner, doc))
    recent_backlog.sort(
        key=lambda item: (backlog_priority(item[0], item[1]), item[1].get("url", "")),
        reverse=True
    )
    historical_backlog.sort(
        key=lambda item: (backlog_priority(item[0], item[1]), item[1].get("url", "")),
        reverse=True
    )
    active_backlog = historical_backlog if HISTORY_BACKFILL else recent_backlog
    run_limit = HISTORY_DOCS_PER_RUN if HISTORY_BACKFILL else DOCS_PER_RUN
    if HISTORY_BACKFILL:
        selected = historical_backlog[:run_limit]
    else:
        # Never waste bounded extraction capacity: prioritize recent reports,
        # then use any remaining slots to backfill older issuer reports.
        selected = recent_backlog[:run_limit]
        remaining = run_limit - len(selected)
        if remaining > 0:
            selected.extend(historical_backlog[:remaining])
    processed = 0
    workers = min(2 if HISTORY_BACKFILL else 4, max(1, len(selected)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_document_text, doc["url"]): (owner, doc) for owner, doc in selected}
        for future in as_completed(futures):
            owner, doc = futures[future]
            try:
                text, final_url, content_type = future.result()
                doc["url"] = final_url
                doc["contentType"] = content_type
                doc["contentHash"] = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
                doc["processedAt"] = now()
                doc["textLength"] = len(text)
                discovered_type = classify_document((doc.get("title") or "") + " " + final_url + " " + text[:5000])
                if doc.get("type") not in {"sustainability_report", "annual_report", "climate_disclosure"}:
                    doc["type"] = discovered_type
                doc["year"] = infer_report_year(text, doc.get("year"), doc.get("title"))
                doc.pop("lastError", None)
                doc.pop("retryAfter", None)
                if owner == "__external__":
                    provider_hint = doc.get("provider")
                    for symbol, cfg in banks.items():
                        if bank_in_text(cfg, text):
                            extracted = extract_ratings(
                                text, config["rating_patterns"], doc.get("year"),
                                final_url, doc.get("title"), provider_hint=provider_hint
                            )
                            companies[symbol]["externalAssessments"].extend(extracted)
                else:
                    if metric_document_allowed(doc):
                        metrics = extract_metrics(
                            text, config["metric_rules"], doc.get("year"),
                            final_url, doc.get("title"), source_type=doc.get("type")
                        )
                        companies[owner]["metrics"].extend(metrics)
                    ratings = extract_ratings(
                        text, config["rating_patterns"], doc.get("year"),
                        final_url, doc.get("title")
                    )
                    companies[owner]["externalAssessments"].extend(ratings)
                processed += 1
            except Exception as exc:
                failures = int(doc.get("failedAttempts") or 0) + 1
                doc["failedAttempts"] = failures
                doc["lastError"] = str(exc)[:300]
                doc["lastAttemptAt"] = now()
                delay = timedelta(hours=24 if failures < 3 else 168)
                doc["retryAfter"] = (datetime.now(timezone.utc) + delay).isoformat()

    for symbol in companies:
        companies[symbol]["metrics"] = merge_unique(
            companies[symbol]["metrics"],
            ["metricId", "year", "rawValue", "unit", "sourceUrl"],
        )
        live_canonical = canonical_metrics(companies[symbol]["metrics"])
        companies[symbol]["canonicalMetrics"] = fill_validated_metrics(live_canonical, banks.get(symbol, {}))
        live_assessments = merge_unique(
            sanitize_external_assessments(companies[symbol]["externalAssessments"]),
            ["provider", "assessmentType", "year", "value", "sourceUrl"],
        )
        companies[symbol]["externalAssessments"] = fill_validated_assessments(live_assessments, banks.get(symbol, {}))
        companies[symbol]["coverage"] = {
            "documents": len(companies[symbol]["documents"]),
            "processedDocuments": sum(bool(d.get("processedAt")) for d in companies[symbol]["documents"]),
            "metrics": len(companies[symbol]["metrics"]),
            "canonicalMetrics": len(companies[symbol]["canonicalMetrics"]),
            "externalAssessments": len(companies[symbol]["externalAssessments"]),
        }

    payload = {
        "checkedAt": now(),
        "extractorVersion": EXTRACTOR_VERSION,
        "sourceRegistryVersion": config.get("version"),
        "status": "ok" if any(s.get("status") == "ok" for s in source_status) else "retained",
        "methodology": {
            "compositeScore": False,
            "universe": "FinQuery Core 100",
            "discoveryPolicy": "Issuer-direct sources are preferred. A deterministic public disclosure index is used as a fallback for Core issuers without a curated source registry.",
            "note": "Provider scores/assessments are preserved on their native scales; FinQuery does not manufacture a cross-provider ESG score.",
            "metricConfidence": "KPI rows require unit-compatible evidence; canonicalMetrics selects the strongest live source per metric/year and fills only missing keys from source-verified fallbacks when issuer PDFs are blocked.",
        },
        "companies": companies,
        "externalDocuments": sorted(external_docs.values(), key=lambda d: (d.get("year") or 0, d.get("title") or ""), reverse=True),
        "sources": source_status,
        "run": {
            "mode": "history" if HISTORY_BACKFILL else "recent",
            "documentsProcessed": processed,
            "backlogBeforeRun": len(backlog),
            "activeBacklogBeforeRun": len(active_backlog),
            "backlogRemaining": max(0, len(active_backlog) - processed),
            "eligibleBacklog": len(eligible_backlog),
            "recentBacklog": len(recent_backlog),
            "historicalBacklog": len(historical_backlog),
            "skippedBacklog": len(skipped_backlog),
            "maxDocumentsPerRun": run_limit,
            "documentWorkers": workers,
        },
    }
    write(output / "company-esg.json", payload)
    write(output / "esg-status.json", {
        "checkedAt": payload["checkedAt"], "status": payload["status"],
        "companies": len(companies),
        "banks": sum(v.get("entityType") == "bank" for v in companies.values()),
        "coreUniverse": 100,
        "companiesWithMetrics": sum(bool(v.get("canonicalMetrics")) for v in companies.values()),
        "sourcesOk": sum(s.get("status") == "ok" for s in source_status),
        "sourcesTotal": len(source_status),
        "documents": sum(v["coverage"]["documents"] for v in companies.values()),
        "metrics": sum(v["coverage"]["metrics"] for v in companies.values()),
        "canonicalMetrics": sum(v["coverage"]["canonicalMetrics"] for v in companies.values()),
        "externalAssessments": sum(v["coverage"]["externalAssessments"] for v in companies.values()),
        "mode": payload["run"]["mode"],
        "documentsProcessedThisRun": processed,
        "backlogRemaining": payload["run"]["backlogRemaining"],
        "recentBacklog": payload["run"]["recentBacklog"],
        "historicalBacklog": payload["run"]["historicalBacklog"],
    })
    print(
        f"Corporate ESG: {len(companies)} Core companies; "
        f"{sum(v['coverage']['documents'] for v in companies.values())} docs; "
        f"{sum(v['coverage']['metrics'] for v in companies.values())} metrics; "
        f"{sum(v['coverage']['externalAssessments'] for v in companies.values())} external assessments; "
        f"processed {processed}; backlog {payload['run']['backlogRemaining']}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    collect(read(args.config, {}), args.output)
