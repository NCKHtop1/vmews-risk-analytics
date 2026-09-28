"""Config-driven corporate ESG discovery and extraction for FinQuery.

The collector keeps a registry of official bank/provider source pages, discovers
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
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/esg_sources.json"
USER_AGENT = "FinQuery/1.0 ESG collector (+public sources only)"
MAX_DOC_BYTES = int(os.environ.get("ESG_MAX_DOC_BYTES", str(35 * 1024 * 1024)))
MAX_TEXT_CHARS = int(os.environ.get("ESG_MAX_TEXT_CHARS", "1800000"))
DOCS_PER_RUN = int(os.environ.get("ESG_DOCS_PER_RUN", "30"))
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


def fetch(url, timeout=25):
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
    })
    with urlopen(req, timeout=timeout) as response:
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
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(c)).lower()


def strip_html(raw):
    text = raw.decode("utf-8", "ignore")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return clean_text(text)


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
    if "second party opinion" in s or "green bond framework" in s or "sustainable finance framework" in s:
        return "sustainable_finance_assessment"
    if "annual report" in s or "bao cao thuong nien" in s:
        return "annual_report"
    if "sustainability report" in s or "bao cao phat trien ben vung" in s or "esg report" in s:
        return "sustainability_report"
    if "tcfd" in s or "ifrs s2" in s or ("climate" in s and "disclosure" in s):
        return "climate_disclosure"
    if "vnsi" in s:
        return "vnsi"
    if "susba" in s or "sustainable banking assessment" in s:
        return "susba"
    if "sustainability" in s or "phat trien ben vung" in s or re.search(r"\besg\b", s):
        return "esg_web_content"
    return "esg_other"


def infer_report_year(text, fallback=None):
    """Prefer a reporting year explicitly tied to a report/disclosure label."""
    sample = clean_text(text[:50000])
    patterns = [
        r"(?:Sustainability|ESG|Annual)\s+Report\s+(20[0-3]\d)",
        r"(20[0-3]\d)\s+(?:Sustainability|ESG|Annual)\s+Report",
        r"Báo\s+cáo\s+(?:phát\s+triển\s+bền\s+vững|thường\s+niên)[^\d]{0,30}(20[0-3]\d)",
        r"(?:reporting|financial)\s+(?:year|period)[^\d]{0,20}(20[0-3]\d)",
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


def discover_seed(seed_url, keywords):
    documents = {}
    try:
        raw, ctype, final_url = fetch(seed_url)
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
    )[:80]

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
        try:
            detail_raw, detail_type, detail_final = fetch(url, timeout=15)
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
                for child, child_label in parse_links(detail_final, detail_raw):
                    if looks_pdf(child) and relevant(child_label + " " + child, keywords):
                        documents[child] = {
                            "id": doc_key(child), "url": child, "title": child_label or Path(urlsplit(child).path).name,
                            "sourcePage": detail_final, "year": extract_year(child_label + " " + child),
                            "type": classify_document(child_label + " " + child),
                        }
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


def extract_document_text(url):
    raw, ctype, final_url = fetch(url, timeout=35)
    if looks_pdf(final_url, ctype) and raw.lstrip().startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("pypdf unavailable") from exc
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        size = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text:
                parts.append(text)
                size += len(text)
            if size >= MAX_TEXT_CHARS:
                break
        return clean_text(" ".join(parts))[:MAX_TEXT_CHARS], final_url, "pdf"
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
        # Vietnamese bank disclosures often use "." as the thousands separator
        # for values reported in VND billions/millions (7.714 tỷ = 7,714).
        if len(right) == 3 and any(x in unit_l for x in ("ty dong", "trieu dong", "billion vnd", "million vnd")):
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
        if "ty dong" in s or "billion vnd" in s:
            return value, "billion VND"
        if "trieu dong" in s or "million vnd" in s:
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

                candidates = []
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


def collect(config, output):
    previous = read(output / "company-esg.json", {"companies": {}, "externalDocuments": []})
    banks = config["banks"]
    keywords = config["document_keywords"]
    source_status = []
    discovered = {symbol: {} for symbol in banks}

    jobs = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for symbol, cfg in banks.items():
            for seed in cfg.get("seed_urls", []):
                jobs.append((symbol, seed, pool.submit(discover_seed, seed, keywords)))
        for symbol, seed, future in jobs:
            try:
                docs, status = future.result()
            except Exception as exc:
                docs, status = [], {"url": seed, "status": "error", "error": str(exc)}
            status["symbol"] = symbol
            source_status.append(status)
            for doc in docs:
                discovered[symbol][doc["url"]] = doc

    companies = {}
    backlog = []
    for symbol, cfg in banks.items():
        prev = previous.get("companies", {}).get(symbol, {})
        docs = {d["url"]: d for d in prev.get("documents", []) if d.get("url")}
        for url, discovered_doc in discovered[symbol].items():
            docs[url] = {**docs.get(url, {}), **discovered_doc}
        ordered = sorted(docs.values(), key=lambda d: (d.get("year") or 0, d.get("title") or ""), reverse=True)
        metrics = list(prev.get("metrics", []))
        ratings = list(prev.get("externalAssessments", []))
        for doc in ordered:
            if not doc.get("processedAt"):
                backlog.append((symbol, doc))
        companies[symbol] = {
            "symbol": symbol, "name": cfg["name"], "checkedAt": now(),
            "documents": ordered, "metrics": metrics, "externalAssessments": ratings,
        }

    # External provider discovery.
    external_docs = {d["url"]: d for d in previous.get("externalDocuments", []) if d.get("url")}
    ext_jobs = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for src in config.get("external_sources", []):
            for seed in src.get("seed_urls", []):
                ext_jobs.append((src, seed, pool.submit(discover_seed, seed, keywords)))
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
                external_docs[doc["url"]] = {**external_docs.get(doc["url"], {}), **doc}
    for doc in external_docs.values():
        if not doc.get("processedAt"):
            backlog.append(("__external__", doc))

    # Bounded, parallel processing so a historical bootstrap cannot block the
    # market publisher. Failed documents back off for 24h instead of consuming
    # every subsequent run.
    current = datetime.now(timezone.utc)
    eligible_backlog = []
    for owner, doc in backlog:
        retry_after = doc.get("retryAfter")
        try:
            blocked = retry_after and datetime.fromisoformat(retry_after) > current
        except (ValueError, TypeError):
            blocked = False
        if not blocked:
            eligible_backlog.append((owner, doc))
    eligible_backlog.sort(key=lambda item: (item[1].get("year") or 0, item[1].get("url", "")), reverse=True)
    selected = eligible_backlog[:DOCS_PER_RUN]
    processed = 0
    workers = min(4, max(1, len(selected)))
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
                    metrics = extract_metrics(text, config["metric_rules"], doc.get("year"), final_url, doc.get("title"))
                    ratings = extract_ratings(text, config["rating_patterns"], doc.get("year"), final_url, doc.get("title"))
                    companies[owner]["metrics"].extend(metrics)
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
        companies[symbol]["externalAssessments"] = merge_unique(
            companies[symbol]["externalAssessments"],
            ["provider", "assessmentType", "year", "value", "sourceUrl"],
        )
        companies[symbol]["coverage"] = {
            "documents": len(companies[symbol]["documents"]),
            "processedDocuments": sum(bool(d.get("processedAt")) for d in companies[symbol]["documents"]),
            "metrics": len(companies[symbol]["metrics"]),
            "externalAssessments": len(companies[symbol]["externalAssessments"]),
        }

    payload = {
        "checkedAt": now(),
        "sourceRegistryVersion": config.get("version"),
        "status": "ok" if any(s.get("status") == "ok" for s in source_status) else "retained",
        "methodology": {
            "compositeScore": False,
            "note": "Provider scores/assessments are preserved on their native scales; FinQuery does not manufacture a cross-provider ESG score.",
            "metricConfidence": "medium unless a future structured-source adapter marks the metric high-confidence.",
        },
        "companies": companies,
        "externalDocuments": sorted(external_docs.values(), key=lambda d: (d.get("year") or 0, d.get("title") or ""), reverse=True),
        "sources": source_status,
        "run": {
            "documentsProcessed": processed,
            "backlogBeforeRun": len(backlog),
            "backlogRemaining": max(0, len(backlog) - processed),
            "eligibleBacklog": len(eligible_backlog),
            "maxDocumentsPerRun": DOCS_PER_RUN,
            "documentWorkers": workers,
        },
    }
    write(output / "company-esg.json", payload)
    write(output / "esg-status.json", {
        "checkedAt": payload["checkedAt"], "status": payload["status"],
        "banks": len(companies),
        "sourcesOk": sum(s.get("status") == "ok" for s in source_status),
        "sourcesTotal": len(source_status),
        "documents": sum(v["coverage"]["documents"] for v in companies.values()),
        "metrics": sum(v["coverage"]["metrics"] for v in companies.values()),
        "externalAssessments": sum(v["coverage"]["externalAssessments"] for v in companies.values()),
        "documentsProcessedThisRun": processed,
        "backlogRemaining": payload["run"]["backlogRemaining"],
    })
    print(
        f"Corporate ESG: {len(companies)} banks; "
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
