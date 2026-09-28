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
    s = ascii_fold(text)
    if "sustainability" in s or "phat trien ben vung" in s or re.search(r"\besg\b", s):
        return "sustainability_report"
    if "climate" in s or "tcfd" in s or "ifrs s2" in s:
        return "climate_disclosure"
    if "green bond" in s or "sustainable finance" in s or "second party opinion" in s or "spo" in s:
        return "sustainable_finance_assessment"
    if "annual report" in s or "bao cao thuong nien" in s:
        return "annual_report"
    if "vnsi" in s:
        return "vnsi"
    if "susba" in s or "sustainable banking assessment" in s:
        return "susba"
    return "esg_other"


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
        if looks_pdf(url) or relevant(combined, keywords):
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
    if looks_pdf(final_url, ctype):
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
    return strip_html(raw)[:MAX_TEXT_CHARS], final_url, "html"


def parse_number(raw):
    s = str(raw).strip().replace(" ", "")
    # Keep only a single numeric token.
    s = re.sub(r"[^\d,.\-+]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        # Last separator is usually decimal; other separator is thousands.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.rsplit(",", 1)[-1]) <= 2:
        s = s.replace(",", ".")
    elif s.count(",") >= 1:
        s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


VALUE_RE = re.compile(
    r"(?P<value>[-+]?\d[\d.,]*(?:\s?\d{3})?)\s*"
    r"(?P<unit>%|tCO2e|tCO₂e|CO2e|CO₂e|kWh|MWh|GWh|m3|m³|kg|tấn|tons?|"
    r"hours?|giờ|triệu đồng|tỷ đồng|nghìn tỷ đồng|million VND|billion VND|VND)?",
    re.I,
)


def infer_unit(snippet, matched_unit, rule):
    if matched_unit:
        return matched_unit.strip()
    s = ascii_fold(snippet)
    if "vnd" in s and "billion" in s:
        return "billion VND"
    if "vnd" in s and "million" in s:
        return "million VND"
    for token, unit in [
        ("nghin ty", "nghìn tỷ đồng"), ("ty dong", "tỷ đồng"), ("trieu dong", "triệu đồng"),
        ("tco2e", "tCO2e"), ("%", "%"), ("kwh", "kWh"), ("mwh", "MWh"), ("m3", "m3"),
        ("hours", "hours"), ("gio", "hours"),
    ]:
        if token in s:
            return unit
    return rule.get("unit_hint")


def metric_value_match(text, report_year=None):
    matches = list(VALUE_RE.finditer(text))
    for match in matches[:10]:
        value = parse_number(match.group("value"))
        raw_digits = re.sub(r"\D", "", match.group("value"))
        # Skip a nearby reporting/calendar year; otherwise phrases such as
        # "training hours in 2024 1,681,691" become the false value 2024.
        if value is not None and len(raw_digits) == 4 and 1990 <= value <= 2039:
            if report_year is None or int(value) == int(report_year) or len(matches) > 1:
                continue
        return match
    return None


def extract_metrics(text, rules, year, source_url, source_title):
    results = []
    lower = text.lower()
    for rule in rules:
        best = None
        for alias in rule["aliases"]:
            start = 0
            alias_l = alias.lower()
            while True:
                idx = lower.find(alias_l, start)
                if idx < 0:
                    break
                window_start, window_end = max(0, idx - 110), min(len(text), idx + len(alias) + 180)
                snippet = clean_text(text[window_start:window_end])
                local = text[idx:window_end]
                m = metric_value_match(local[len(alias):], year)
                if not m:
                    # Sometimes the value is immediately before the label.
                    before = text[window_start:idx]
                    matches = [x for x in VALUE_RE.finditer(before)
                               if not (len(re.sub(r"\D", "", x.group("value"))) == 4
                                       and 1990 <= (parse_number(x.group("value")) or 0) <= 2039)]
                    m = matches[-1] if matches else None
                if m:
                    raw_value = m.group("value")
                    value = parse_number(raw_value)
                    unit = infer_unit(snippet, m.groupdict().get("unit"), rule)
                    score = 2 + (1 if unit and unit != rule.get("unit_hint") else 0)
                    candidate = {
                        "metricId": rule["id"], "pillar": rule["pillar"], "label": rule["label"],
                        "year": year, "value": value, "rawValue": raw_value, "unit": unit,
                        "sourceUrl": source_url, "sourceTitle": source_title,
                        "snippet": snippet[:360], "confidence": "medium", "_score": score,
                    }
                    if best is None or candidate["_score"] > best["_score"]:
                        best = candidate
                start = idx + len(alias_l)
        if best:
            best.pop("_score", None)
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
