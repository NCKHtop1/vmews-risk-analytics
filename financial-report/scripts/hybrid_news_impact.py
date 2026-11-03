"""FinQuery Hybrid News Impact V2: source-aware, non-predictive shadow research.

A headline is NOT an established business exposure. An issuer mention is NOT
an affected issuer. A historical association is NOT a causal effect.
No function here is allowed to authorize notifications.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import math
import re

import news_impact_taxonomy as tax

SCHEMA = "FINQUERY_HYBRID_NEWS_IMPACT_SHADOW_V2"
EXPOSURE_SCHEMA = "FINQUERY_ECONOMIC_EXPOSURES_V2"
VERSION = "2.0.0-research"
MATERIAL_CHANNELS = {x[2] for v in tax.EXPOSURES.values() for x in v}
ALLOWED_FAMILIES = set(tax.EXPOSURES)
REQUIRED_REGISTRY_FIELDS = (
    "issuerSymbol", "eventFamily", "mechanism", "sourceType",
    "sourceUrl", "sourcePublishedAt", "periodEnd",
    "validFrom", "validUntil", "shareOfBusiness", "reviewStatus",
)
METRIC_ROWS = {
    "net_sales", "interest_expense", "interest_income",
    "unrealized_foreign_exchange_gain_loss",
    "effect_of_foreign_exchange_differences",
}

def parse_utc(value):
    try:
        stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None

def uri_is_source(value):
    try:
        url = urlsplit(str(value or ""))
        return url.scheme == "https" and bool(url.netloc and "." in url.netloc)
    except ValueError:
        return False

def source_fact_asof(fact, event_at, known_symbols):
    """Accept only explicitly reviewed, quantified source facts available as of event.

    This is a *business fact* integrity check, never proof of impact.
    """
    if not isinstance(fact, dict) or any(k not in fact for k in REQUIRED_REGISTRY_FIELDS):
        return None
    symbol = str(fact["issuerSymbol"]).upper()
    if not re.fullmatch(r"[A-Z]{3}", symbol) or symbol not in known_symbols:
        return None
    if fact["reviewStatus"] != "REVIEWED_SOURCE_FACT" or fact["sourceType"] != "ISSUER_FILING":
        return None
    if fact["eventFamily"] not in ALLOWED_FAMILIES or fact["mechanism"] not in MATERIAL_CHANNELS:
        return None
    if fact["mechanism"] not in {r[2] for r in tax.EXPOSURES[fact["eventFamily"]]}:
        return None
    if not uri_is_source(fact["sourceUrl"]):
        return None
    pub = parse_utc(fact["sourcePublishedAt"])
    start = parse_utc(fact["validFrom"])
    expiry = parse_utc(fact["validUntil"])
    report_end = parse_utc(fact["periodEnd"])
    if not all((pub, start, expiry, report_end, event_at)):
        return None
    if not (report_end <= pub <= event_at and start <= event_at <= expiry):
        return None
    # Do not reuse an old exposure mix indefinitely, and avoid forward-looking facts.
    if (event_at - pub).days > 540 or (expiry - start).days > 730:
        return None
    share = fact["shareOfBusiness"]
    if isinstance(share, bool) or not isinstance(share, (int, float)):
        return None
    if not math.isfinite(share) or not 0 <= share <= 1:
        return None
    if fact.get("measurementBasis") not in ("REVENUE_SHARE", "INPUT_COST_SHARE", "FX_DEBT_SHARE", "BUSINESS_ASSET_SHARE"):
        return None
    if fact.get("entityRole") not in ("LISTED_ISSUER", "CONSOLIDATED_GROUP"):
        return None
    # A business fact is conditional on jurisdiction and business segment.
    # An unscoped tariff story may not map to any ticker.
    return {
        "issuerSymbol":symbol, "eventFamily":fact["eventFamily"],
        "mechanism":fact["mechanism"], "shareOfBusiness":share,
        "measurementBasis":fact["measurementBasis"], "sourceUrl":fact["sourceUrl"],
        "sourcePublishedAt":pub.isoformat(), "periodEnd":report_end.isoformat(),
        "jurisdiction":str(fact.get("jurisdiction") or "").upper(),
    }

def load_registry(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != EXPOSURE_SCHEMA or not isinstance(payload.get("facts"), list):
        raise ValueError("Economic exposure registry schema is not valid")
    return payload["facts"]

def audit_financial_coverage(finance_dir, companies):
    """Inventory existing report line items; do not infer exporting or currency debt."""
    folder = Path(finance_dir)
    covered = []
    indicators = Counter()
    for sym in sorted(companies):
        path = folder / (sym + ".json")
        if not path.is_file():
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("symbol") != sym:
            continue
        found = set()
        for section in d.get("sections") or []:
            if section.get("id") not in ("income_statement", "cash_flow"):
                continue
            for row in section.get("rows") or []:
                name = row.get("id")
                # Only documented source line items count towards *coverage*.
                # Their mere existence says nothing about sensitivity/sign.
                values = row.get("values") or {}
                if name in METRIC_ROWS and any(
                    isinstance(x, (int,float)) and not isinstance(x, bool)
                    and math.isfinite(x) for x in values.values()):
                    found.add(name)
        if found:
            covered.append(sym)
            indicators.update(found)
    return {
        "listedCompanyReferenceCount":len(companies),
        "financialStatementCoverageCount":len(covered),
        "metricCoverage":dict(sorted(indicators.items())),
        "sourceReportPublicationTimesCertified":False,
        "segmentRevenueCoverageCertified":0,
        "foreignDebtBreakdownCoverageCertified":0,
        "supplyChainCoverageCertified":0,
        "note":"General financial statement lines are research context, not PIT exposure shares.",
    }

def _story_key(row):
    if row.get("storyId"):
        return str(row["storyId"])
    base = tax.canonical_article_url(row.get("canonicalUrl") or row.get("url"))
    if not base:
        base = "|".join((str(row.get("title") or ""),str(row.get("publishedAt") or "")[:13]))
    return "research_" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:18]

def _direct_mentions(row, known):
    result = set()
    for mention in row.get("entityMentions") or []:
        if not isinstance(mention, dict):
            continue
        symbol = str(mention.get("symbol") or "").upper()
        try:
            confidence = float(mention.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if symbol in known and confidence >= 0.95:
            result.add(symbol)
    return sorted(result)

def _mechanism_facts(family, event, facts):
    # Jurisdictionless trade stories are never attributed to specific firms.
    places = {str(x).upper() for x in (event.get("affectedJurisdictions") or []) if x}
    eligible = []
    for fact in facts:
        if fact["eventFamily"] != family:
            continue
        if family == "TARIFF_TRADE" and (not places or fact.get("jurisdiction") not in places):
            continue
        eligible.append(fact)
    return eligible

def analyze_snapshot(items, companies, finance_dir, registry_path, collected_at):
    """Build auditable research candidates, not user-visible impact alerts.

    Past ticker/sector evidence is intentionally NOT imported from sentiment.
    Unlike a model-score feature, no threshold silently promotes an issuer.
    """
    observed = parse_utc(collected_at)
    if observed is None:
        raise ValueError("collected_at must be a UTC-aware timestamp")
    known = {str(c.get("symbol") or "").upper() for c in companies if c.get("symbol")}
    facts = load_registry(registry_path)
    valid_facts = []
    invalid_facts = 0
    for f in facts:
        x = source_fact_asof(f, observed, known)
        if x is None:
            invalid_facts += 1
        else:
            valid_facts.append(x)

    # Do not repeatedly count syndicated copies of one event.
    representative = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = _story_key(item)
        if key not in representative:
            representative[key] = item
    events = []
    counts = Counter()
    early = 0
    candidate_mentions = 0
    with_business_fact = 0
    for key, row in representative.items():
        family = tax.event_family(row)
        counts[family] += 1
        mention = _direct_mentions(row, known)
        candidate_mentions += bool(mention)
        receipt = (parse_utc(row.get("collectorFirstSeenAt"))
                   if row.get("collectorFirstSeenBasis") == "COLLECTOR_RECEIPT" else None)
        if not receipt or receipt > observed:
            early += 1
            receipt = None
        # Re-check each disclosure at the news collector's actual receipt time:
        # a valid fact today may have been unpublished when the story arrived.
        facts_at_event = ([x for f in facts if (x := source_fact_asof(f, receipt, known))]
                          if receipt else [])
        if invalid_facts:
            facts_at_event = []
        matched = _mechanism_facts(family, row, facts_at_event)
        # Only a direct issuer mention can become a firm-specific research
        # candidate; macro mechanism alone never creates ticker exposure.
        firm_facts = [f for f in matched if f["issuerSymbol"] in mention]
        with_business_fact += bool(firm_facts)
        if family != "UNCLASSIFIED":
            events.append({
                "storyId":key, "family":family,
                "collectorFirstSeenAt":receipt.isoformat() if receipt else None,
                "sourceTimeCertified":bool(receipt),
                "directIssuerMentions":mention,
                "candidateEconomicMechanisms":[x[2] for x in tax.EXPOSURES.get(family, ())],
                "pointInTimeBusinessFactsFound":len(firm_facts),
                "candidateStatus":"RESEARCH_ONLY",
                "causalityStatus":"NOT_ESTABLISHED",
                "validatedAffectedSectors":[],
                "validatedAffectedTickers":[],
                "notificationEligible":False,
            })
    coverage = audit_financial_coverage(finance_dir, known)
    if invalid_facts:
        # Any invalid manually reviewed fact quarantines the entire registry,
        # not just one entry: prevents partial selective labels.
        valid_facts = []
        for event in events:
            event["pointInTimeBusinessFactsFound"] = 0
        with_business_fact = 0
    return {
        "schema":SCHEMA, "version":VERSION,
        "status":"SHADOW_ONLY", "checkedAt":observed.isoformat(),
        "models":{
            "eventIntelligence":"deterministic_semantic_v1 + NEWS-EXPOSURE-RESEARCH-1",
            "llmStatus":"OFF_UNTIL_INDEPENDENT_SCHEMA_AND_ENTITY_QA",
            "economicExposure":"audited_PIT_issuer_disclosure_registry_v2",
            "quantValidation":"V12 retrospective event study + prospective PIT gate pending",
        },
        "counts":{
            "deduplicatedStories":len(representative),
            "classifiedEventStories":len(events),
            "directIssuerMentionStories":candidate_mentions,
            "storiesWithEligibleBusinessFacts":with_business_fact,
            "storiesWithoutCertifiedCollectorTime":early,
            "reviewedSourceFacts":len(valid_facts),
            "invalidSourceFacts":invalid_facts,
            "verifiedImpactRelations":0,
            "eligibleNotifications":0,
        },
        "eventFamilies":dict(sorted(counts.items())),
        "financialCoverage":coverage,
        "researchCandidates":events[:500],
        "publicationPolicy":{
            "forecastModel":False, "historicalImpactCertified":False,
            "verifiedTickerAlerts":False, "verifiedSectorAlerts":False,
            "requiresNewIndependentPITStudy":True,
            "noAlertFromSentimentOrNewsPriority":True,
            "killSwitch":"LOCKED_OFF",
        },
    }
