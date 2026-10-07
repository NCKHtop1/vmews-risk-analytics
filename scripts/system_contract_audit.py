#!/usr/bin/env python3
"""Repository-wide FinQuery production data contract audit.

This audit intentionally recomputes key health invariants instead of trusting
publisher status fields. It is designed to run against checked-out production
branches in GitHub Actions.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vn_exchange_calendar import VN_TZ, is_trading_day, latest_completed_session  # noqa: E402


def parse_ts(value):
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=dt.tzinfo or VN_TZ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Audit:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.results = []
        self.checks = 0

    def _record(self, status, code, detail):
        self.results.append({
            "status": status,
            "code": code,
            "category": str(code).split("_", 1)[0],
            "detail": str(detail),
        })

    def check(self, condition, code, detail):
        self.checks += 1
        ok = bool(condition)
        self._record("PASS" if ok else "FAIL", code, detail)
        if not ok:
            self.errors.append({"code": code, "detail": str(detail)})
        return ok

    def warn(self, condition, code, detail):
        self.checks += 1
        ok = bool(condition)
        self._record("PASS" if ok else "WARN", code, detail)
        if not ok:
            self.warnings.append({"code": code, "detail": str(detail)})
        return ok

    def future_safe(self, value, now, code):
        stamp = parse_ts(value)
        return self.check(stamp is not None and stamp <= now + timedelta(minutes=5), code, value)


def risk_eligible_symbols(quotes, strategy, source_day):
    rows = []
    ss = strategy.get("symbols") or {}
    for symbol, q in (quotes.get("quotes") or {}).items():
        s = ss.get(symbol) or {}
        if q.get("status") == "retained":
            continue
        if not finite(q.get("price")) or float(q.get("price") or 0) <= 0 or not finite(q.get("changePct")):
            continue
        if s.get("cadence") != "LIVE_15M" or str(s.get("barDate") or "") != source_day:
            continue
        rows.append(symbol)
    return sorted(rows)


def compute_intraday_session(market_dir: Path, quotes, source_day, max_lag=20.0):
    expected, fresh, lagged = [], [], []
    for symbol, q in (quotes.get("quotes") or {}).items():
        if q.get("status") == "retained":
            continue
        qstamp = parse_ts(q.get("sourceTime") or q.get("collectedAt"))
        if qstamp is None or qstamp.astimezone(VN_TZ).date().isoformat() != source_day:
            continue
        expected.append(symbol)
        path = market_dir / "intraday" / f"{symbol}.json"
        if not path.exists():
            lagged.append((symbol, "missing"))
            continue
        try:
            row = load_json(path)
        except Exception:
            lagged.append((symbol, "invalid_json"))
            continue
        last = row.get("lastBar")
        if not last:
            bars = row.get("bars") or []
            last = bars[-1].get("time") if bars and isinstance(bars[-1], dict) else None
        bstamp = parse_ts(last)
        if bstamp is None or bstamp.astimezone(VN_TZ).date().isoformat() != source_day:
            lagged.append((symbol, "wrong_session"))
            continue
        lag = max(0.0, (qstamp - bstamp).total_seconds() / 60)
        if lag <= max_lag:
            fresh.append(symbol)
        else:
            lagged.append((symbol, round(lag, 1)))
    return {"expected": expected, "fresh": fresh, "lagged": lagged}


def audit_market_bar_files(report: Audit, market_dir: Path, universe, now, quote_day):
    symbols = universe.get("symbols") or {}
    live_symbols = sorted(
        symbol for symbol, meta in symbols.items()
        if (meta or {}).get("liveMarketEligible")
    )
    # Only Core/Liquid live names are file-backed by market/history. Discovery
    # scanner rows are intentionally EOD snapshots embedded in technical-signals
    # and are covered by scanner/universe contracts elsewhere in this audit.
    history_symbols = live_symbols

    def valid_ohlc(bar):
        try:
            o=float(bar.get("open")); h=float(bar.get("high")); l=float(bar.get("low")); c=float(bar.get("close"))
            v=float(bar.get("volume") or 0)
        except (TypeError, ValueError):
            return False
        return all(math.isfinite(x) for x in (o,h,l,c,v)) and min(o,h,l,c)>0 and v>=0 and h+1e-9>=max(o,c) and l-1e-9<=min(o,c)

    history_valid=0
    for symbol in history_symbols:
        path=market_dir/"history"/f"{symbol}.json"
        if not report.check(path.exists(), "MARKET_HISTORY_FILE", symbol):
            continue
        try:
            data=load_json(path)
        except Exception as exc:
            report.check(False, "MARKET_HISTORY_JSON", f"{symbol}: {exc}")
            continue
        bars=data.get("bars") or []
        times=[str(row.get("time") or "")[:10] for row in bars if isinstance(row,dict)]
        meta=symbols.get(symbol) or {}
        report.check(data.get("symbol")==symbol and data.get("unit")=="VND", "MARKET_HISTORY_IDENTITY", symbol)
        report.check(bool(bars) and int(data.get("barCount") or 0)==len(bars), "MARKET_HISTORY_COUNT", f"{symbol}:{data.get('barCount')}/{len(bars)}")
        report.check(times==sorted(set(times)), "MARKET_HISTORY_ORDER", symbol)
        report.check(all(valid_ohlc(row) for row in bars), "MARKET_HISTORY_OHLC", symbol)
        report.check(all(datetime.fromisoformat(day).weekday()<5 for day in times if day), "MARKET_HISTORY_WEEKEND", symbol)
        report.check(not times or times[-1]<=quote_day, "MARKET_HISTORY_FUTURE", f"{symbol}:{times[-1] if times else None}>{quote_day}")
        expected_latest=str(meta.get("latestDate") or "")[:10]
        if expected_latest:
            actual_latest=times[-1] if times else ""
            report.check(bool(times) and actual_latest==expected_latest, "MARKET_HISTORY_UNIVERSE_ALIGNMENT", f"{symbol}:{actual_latest or None}/{expected_latest}")
            expected_fresh=bool(actual_latest and actual_latest==quote_day)
            if "fresh" in meta:
                report.check(bool(meta.get("fresh"))==expected_fresh, "MARKET_UNIVERSE_FRESH_FLAG", f"{symbol}:{meta.get('fresh')}/{expected_fresh}")
            if "forecastEligible" in meta:
                expected_forecast=bool(meta.get("tier") in {"CORE","LIQUID"} and meta.get("dataSufficient") and expected_fresh)
                report.check(bool(meta.get("forecastEligible"))==expected_forecast, "MARKET_UNIVERSE_FORECAST_FLAG", f"{symbol}:{meta.get('forecastEligible')}/{expected_forecast}")
        report.check(str(data.get("lastBar") or "")[:10]==(times[-1] if times else ""), "MARKET_HISTORY_LASTBAR", symbol)
        if bars and all(valid_ohlc(row) for row in bars) and times==sorted(set(times)):
            history_valid+=1
    report.check(history_valid==len(history_symbols), "MARKET_HISTORY_DEEP_COVERAGE", f"{history_valid}/{len(history_symbols)}")

    intraday_valid=0
    for symbol in live_symbols:
        path=market_dir/"intraday"/f"{symbol}.json"
        if not report.check(path.exists(), "MARKET_INTRADAY_FILE", symbol):
            continue
        try:
            data=load_json(path)
        except Exception as exc:
            report.check(False, "MARKET_INTRADAY_JSON", f"{symbol}: {exc}")
            continue
        bars=data.get("bars") or []
        parsed=[]
        parse_ok=True
        for row in bars:
            try:
                parsed.append(datetime.fromisoformat(str(row.get("time") or "").replace("Z","+00:00")).astimezone(VN_TZ))
            except Exception:
                parse_ok=False
                break
        report.check(data.get("symbol")==symbol and data.get("unit")=="VND", "MARKET_INTRADAY_IDENTITY", symbol)
        report.check(bool(bars) and int(data.get("barCount") or 0)==len(bars), "MARKET_INTRADAY_COUNT", f"{symbol}:{data.get('barCount')}/{len(bars)}")
        report.check(parse_ok and parsed==sorted(parsed) and len(parsed)==len(set(parsed)), "MARKET_INTRADAY_ORDER", symbol)
        report.check(all(valid_ohlc(row) for row in bars), "MARKET_INTRADAY_OHLC", symbol)
        report.check(
            parse_ok and all(stamp.astimezone(timezone.utc)<=now+timedelta(minutes=5) for stamp in parsed),
            "MARKET_INTRADAY_FUTURE", symbol
        )
        report.check(parse_ok and all(stamp.weekday()<5 for stamp in parsed), "MARKET_INTRADAY_WEEKEND", symbol)
        session_times_ok=True
        if parse_ok:
            for stamp in parsed:
                minute=stamp.hour*60+stamp.minute
                if not ((9*60)<=minute<=(11*60+30) or (13*60)<=minute<=(15*60)):
                    session_times_ok=False
                    break
        report.check(session_times_ok, "MARKET_INTRADAY_SESSION_TIME", symbol)
        last_iso=str(data.get("lastBar") or "")
        if parsed:
            expected_last=parsed[-1].astimezone(timezone.utc)
            actual_last=parse_ts(last_iso)
            report.check(actual_last is not None and abs((actual_last-expected_last).total_seconds())<1, "MARKET_INTRADAY_LASTBAR", symbol)
        else:
            report.check(False, "MARKET_INTRADAY_LASTBAR", symbol)
        if bars and parse_ok and all(valid_ohlc(row) for row in bars):
            intraday_valid+=1
    report.check(intraday_valid==len(live_symbols), "MARKET_INTRADAY_DEEP_COVERAGE", f"{intraday_valid}/{len(live_symbols)}")


def solution_live_freshness(data, now):
    now = now.astimezone(timezone.utc)
    local = now.astimezone(VN_TZ)
    mins = local.hour * 60 + local.minute
    weekday = is_trading_day(local.date(), require_certified=True)
    active = weekday and ((8 * 60 + 55) <= mins <= (11 * 60 + 40) or (12 * 60 + 55) <= mins <= (15 * 60 + 10))
    generated = parse_ts(data.get("generatedAt"))
    source = parse_ts(data.get("sourceTime"))
    coverage = int(data.get("coverage") or 0)
    expected = int(data.get("expected") or 0)
    if (
        data.get("scope") != "solution-ai"
        or data.get("status") != "ok"
        or coverage < 500
        or expected != coverage
        or generated is None
        or source is None
        or generated > now + timedelta(minutes=5)
        or source > now + timedelta(minutes=5)
        or source > generated + timedelta(minutes=5)
    ):
        return False, "BASE", "schema/status/timestamp contract failed"
    generated_age = (now - generated).total_seconds() / 60
    source_age = (now - source).total_seconds() / 60
    source_day = source.astimezone(VN_TZ).date()
    if active:
        ok = generated_age <= 10 and source_age <= 25 and source_day == local.date()
        return ok, "LIVE", f"generatedAge={generated_age:.1f} sourceAge={source_age:.1f} sourceDay={source_day}"
    if weekday and mins >= 11 * 60 + 40:
        ok = source_day == local.date()
        return ok, "SAME_DAY_SESSION", f"sourceDay={source_day} expected={local.date()}"
    ok = source_age <= 96 * 60
    return ok, "LAST_COMPLETED_SESSION", f"sourceAge={source_age:.1f}"



def audit_intraday_archive_status(report: Audit, status, live_symbols, qday, now, qstamp):
    """Require the append-only 5m replay archive after the current HOSE session is safely complete."""
    if qstamp is None:
        return
    local = now.astimezone(VN_TZ)
    mins = local.hour * 60 + local.minute
    quote_local = qstamp.astimezone(VN_TZ)
    post_close = (
        is_trading_day(local.date(), require_certified=True)
        and mins >= 15 * 60 + 20
        and quote_local.date() == local.date()
    )
    if not post_close:
        return
    required = math.ceil(len(live_symbols) * .90) if live_symbols else 0
    latest = str(status.get("archive5mLatestDay") or "")
    coverage = int(status.get("archive5mLatestDayCoverage") or 0)
    report.check(latest == qday, "MARKET_INTRADAY_ARCHIVE_SESSION", f"{latest}/{qday}")
    report.check(coverage >= required, "MARKET_INTRADAY_ARCHIVE_COVERAGE", f"{coverage}/{len(live_symbols)} required={required}")
    report.check(str(status.get("archiveFinalizedSession") or "") == qday, "MARKET_INTRADAY_ARCHIVE_FINALIZED", status.get("archiveFinalizedSession"))


def audit_macro_semantics(report: Audit, macro):
    """Fail closed when canonical macro evidence is missing or the aggregate GDP/PMI series is unsafe."""
    datasets = macro.get("datasets") or {}
    for key in ("gdp_growth", "pmi", "money_supply", "fdi"):
        dataset = datasets.get(key) or {}
        report.check(
            dataset.get("status") in {"ok", "cached"} and bool(dataset.get("rows")),
            "MARKET_MACRO_CANONICAL_DATASET",
            f"{key}:{dataset.get('status')} rows={len(dataset.get('rows') or [])}",
        )

    gdp = datasets.get("gdp_growth") or {}
    columns = gdp.get("columns") or []
    label_key = columns[0] if columns else None
    numeric_columns = gdp.get("numericColumns") or columns[1:]
    aggregate_rows = []
    for row in gdp.get("rows") or []:
        label = str(row.get(label_key) if label_key else next(iter(row.values()), "")).casefold()
        if "gdp" not in label:
            continue
        values = [
            float(row[column])
            for column in numeric_columns
            if finite(row.get(column))
        ]
        aggregate_rows.append(values)
    aggregate_safe = bool(aggregate_rows) and all(
        values and all(abs(value) <= 20 for value in values)
        for values in aggregate_rows
    )
    report.check(aggregate_safe, "MARKET_MACRO_GDP_AGGREGATE", f"aggregateRows={len(aggregate_rows)}")

    pmi = datasets.get("pmi") or {}
    report.check(
        pmi.get("qualityStatus") == "ok",
        "MARKET_MACRO_PMI_QUALITY",
        f"quality={pmi.get('qualityStatus')} warnings={len(pmi.get('qualityWarnings') or [])}",
    )
    overview = datasets.get("macro_overview") or {}
    if overview.get("qualityStatus") == "warning":
        report.check(
            bool(overview.get("qualityWarnings")),
            "MARKET_MACRO_WARNING_EVIDENCE",
            f"warnings={len(overview.get('qualityWarnings') or [])}",
        )

def audit_market(report: Audit, market_dir: Path, now):
    required = [
        "universe.json", "quotes.json", "intraday-status.json", "technical-signals.json",
        "strategy-indicators.json", "risk-monitor.json", "news-latest.json", "news-company-latest.json", "macro.json",
        "esg-status.json", "watch-today.json",
    ]
    docs = {}
    for name in required:
        p = market_dir / name
        if not report.check(p.exists(), "MARKET_FILE_MISSING", name):
            continue
        try:
            docs[name] = load_json(p)
        except Exception as exc:
            report.check(False, "MARKET_JSON_INVALID", f"{name}: {exc}")
    if "universe.json" not in docs or "quotes.json" not in docs:
        return set()

    universe, quotes = docs["universe.json"], docs["quotes.json"]
    counts = universe.get("counts") or {}
    symbols = universe.get("symbols") or {}
    live_symbols = set(universe.get("liveMarketSymbols") or [k for k, v in symbols.items() if v.get("liveMarketEligible")])
    core_symbols = {k for k, v in symbols.items() if v.get("coreMember") or v.get("tier") == "CORE"}
    expected = int(quotes.get("expected") or 0)
    quote_rows = quotes.get("quotes") or {}
    non_retained = {
        s for s, q in quote_rows.items()
        if q.get("status") != "retained" and finite(q.get("price")) and float(q.get("price") or 0) > 0
    }
    report.check(expected == int(counts.get("liveMarket") or 0) == len(live_symbols), "MARKET_UNIVERSE_EXPECTED", (expected, counts.get("liveMarket"), len(live_symbols)))
    report.check(set(quote_rows) == live_symbols, "MARKET_QUOTE_SYMBOL_SET", f"quotes={len(quote_rows)} live={len(live_symbols)}")
    report.check(int(quotes.get("coverage") or 0) == len(non_retained), "MARKET_QUOTE_COVERAGE_EXACT", (quotes.get("coverage"), len(non_retained)))
    report.check(len(non_retained) >= math.ceil(max(1, expected) * .90), "MARKET_QUOTE_COVERAGE_LOW", f"{len(non_retained)}/{expected}")

    qstamp = parse_ts(quotes.get("latestSourceTime") or quotes.get("checkedAt"))
    report.check(qstamp is not None, "MARKET_QUOTE_TIMESTAMP", quotes.get("latestSourceTime"))
    if qstamp:
        report.check(qstamp <= now + timedelta(minutes=5), "MARKET_QUOTE_FUTURE", qstamp)
        qday = qstamp.astimezone(VN_TZ).date().isoformat()
        local = now.astimezone(VN_TZ)
        mins = local.hour * 60 + local.minute
        if is_trading_day(local.date(), require_certified=True) and mins >= 9 * 60 + 5:
            report.check(qstamp.astimezone(VN_TZ).date() == local.date(), "MARKET_QUOTE_WRONG_SESSION", qstamp)
    else:
        qday = str(universe.get("asOf") or "")

    audit_market_bar_files(report, market_dir, universe, now, qday)

    scanner = docs.get("technical-signals.json") or {}
    strategy = docs.get("strategy-indicators.json") or {}
    risk = docs.get("risk-monitor.json") or {}
    source = quotes.get("latestSourceTime")
    report.check(str(scanner.get("sourceTime") or "") == str(source or ""), "MARKET_SCANNER_ALIGNMENT", (scanner.get("sourceTime"), source))
    report.check(str(strategy.get("sourceTime") or "") == str(source or ""), "MARKET_STRATEGY_ALIGNMENT", (strategy.get("sourceTime"), source))
    report.check(str(risk.get("sourceTime") or "") == str(source or ""), "MARKET_RISK_ALIGNMENT", (risk.get("sourceTime"), source))
    report.check(int(scanner.get("universe") or 0) == int(counts.get("scannerEligible") or 0), "MARKET_SCANNER_UNIVERSE", (scanner.get("universe"), counts.get("scannerEligible")))
    report.check(int(scanner.get("coverage") or 0) >= math.ceil(max(1, int(scanner.get("universe") or 0)) * .90), "MARKET_SCANNER_COVERAGE", scanner.get("coverage"))
    report.check(int(strategy.get("coverage") or 0) >= math.ceil(max(1, int(scanner.get("universe") or 0)) * .90), "MARKET_STRATEGY_COVERAGE", strategy.get("coverage"))

    eligible = risk_eligible_symbols(quotes, strategy, qday)
    rcov = int((risk.get("coverage") or {}).get("quotes") or 0)
    report.check(bool(risk.get("inputSignature")), "MARKET_RISK_SIGNATURE", risk.get("version"))
    report.check(rcov == len(eligible), "MARKET_RISK_COVERAGE_EXACT", f"risk={rcov} eligible={len(eligible)}")
    report.check(0 <= float((risk.get("overall") or {}).get("score", -1)) <= 100, "MARKET_RISK_SCORE_RANGE", (risk.get("overall") or {}).get("score"))
    groups = risk.get("breadthGroups") or {}
    group_count = sum(len(groups.get(k) or []) for k in ("advancing", "declining", "unchanged"))
    report.check(group_count == rcov, "MARKET_RISK_BREADTH_TOTAL", (group_count, rcov))

    status = docs.get("intraday-status.json") or {}
    session = compute_intraday_session(market_dir, quotes, qday, 20)
    req = math.ceil(len(session["expected"]) * .90) if session["expected"] else 0
    report.check(len(session["fresh"]) >= req, "MARKET_INTRADAY_BAR_COVERAGE", f"fresh={len(session['fresh'])}/{len(session['expected'])} required={req} lagged={session['lagged'][:12]}")
    report.check(status.get("sessionExpected") is not None and status.get("sessionFresh") is not None, "MARKET_INTRADAY_STATUS_FIELDS", status)
    report.check(bool(status.get("sessionQuoteSourceTime")), "MARKET_INTRADAY_QUOTE_GENERATION_MISSING", status.get("checkedAt"))
    if status.get("sessionExpected") is not None:
        status_expected=int(status.get("sessionExpected") or 0)
        status_fresh=int(status.get("sessionFresh") or 0)
        status_required=int(status.get("sessionRequired") or (math.ceil(status_expected*.90) if status_expected else 0))
        report.check(status_expected == 0 or status_fresh >= status_required, "MARKET_INTRADAY_STATUS_COVERAGE", (status_fresh,status_expected,status_required))
        status_source=parse_ts(status.get("sessionQuoteSourceTime"))
        report.check(status_source is not None and status_source <= now + timedelta(minutes=5), "MARKET_INTRADAY_QUOTE_GENERATION_INVALID", status.get("sessionQuoteSourceTime"))
        if status_source and qstamp:
            report.check(status_source.astimezone(VN_TZ).date() == qstamp.astimezone(VN_TZ).date(), "MARKET_INTRADAY_QUOTE_SESSION_MISMATCH", (status.get("sessionQuoteSourceTime"), quotes.get("latestSourceTime")))
            report.check(status_source <= qstamp + timedelta(minutes=5), "MARKET_INTRADAY_QUOTE_GENERATION_FUTURE", (status.get("sessionQuoteSourceTime"), quotes.get("latestSourceTime")))
            if str(status.get("sessionQuoteSourceTime") or "") == str(quotes.get("latestSourceTime") or ""):
                report.check(status_expected == len(session["expected"]), "MARKET_INTRADAY_EXPECTED_EXACT", (status_expected, len(session["expected"])))
                report.check(status_fresh == len(session["fresh"]), "MARKET_INTRADAY_FRESH_EXACT", (status_fresh, len(session["fresh"])))
            else:
                report.warn(abs(status_expected-len(session["expected"])) <= 5 and abs(status_fresh-len(session["fresh"])) <= 5, "MARKET_INTRADAY_GENERATION_SKEW", f"status={status_fresh}/{status_expected} current={len(session['fresh'])}/{len(session['expected'])} statusSource={status.get('sessionQuoteSourceTime')} currentSource={quotes.get('latestSourceTime')}")

    audit_intraday_archive_status(report, status, live_symbols, qday, now, qstamp)

    news = docs.get("news-latest.json") or {}
    news_items = news.get("items") or []
    health = news.get("sourceHealth") or {}
    report.check(
        news.get("status") == "ok"
        and news.get("selection") == "balanced_vietnam_global_sbv_impact"
        and 0 < len(news_items) <= 300,
        "MARKET_NEWS_CONTENT",
        (news.get("status"), news.get("selection"), len(news_items)),
    )
    report.check(int(health.get("healthy") or 0) >= 3 and int(health.get("healthy") or 0) + int(health.get("empty") or 0) + int(health.get("error") or 0) == int(health.get("total") or 0), "MARKET_NEWS_SOURCE_HEALTH", health)
    nstamp = parse_ts(news.get("checkedAt") or news.get("generatedAt"))
    report.check(nstamp is not None and -5 <= (now - nstamp).total_seconds() / 60 <= 45, "MARKET_NEWS_FRESHNESS", news.get("checkedAt"))

    company_news = docs.get("news-company-latest.json") or {}
    company_counts = company_news.get("companyCounts") or {}
    report.check(
        company_news.get("status") == "ok"
        and company_news.get("selection") == "per_symbol_latest"
        and int(company_news.get("perSymbolLimit") or 0) == 15
        and int(company_news.get("companyCoverage") or 0) == len(company_counts)
        and len(company_counts) > 0
        and bool(company_news.get("items")),
        "MARKET_COMPANY_NEWS_CONTENT",
        {
            "status": company_news.get("status"),
            "selection": company_news.get("selection"),
            "coverage": company_news.get("companyCoverage"),
            "countKeys": len(company_counts),
            "items": len(company_news.get("items") or []),
        },
    )
    report.check(str(company_news.get("checkedAt") or "") == str(news.get("checkedAt") or ""), "MARKET_COMPANY_NEWS_ALIGNMENT", (company_news.get("checkedAt"), news.get("checkedAt")))

    macro = docs.get("macro.json") or {}
    mstamp = parse_ts(macro.get("checkedAt") or macro.get("generatedAt"))
    report.check(macro.get("status") == "ok" and mstamp is not None, "MARKET_MACRO_STATUS", macro.get("status"))
    if mstamp and qstamp:
        report.check(mstamp.astimezone(VN_TZ).date() >= qstamp.astimezone(VN_TZ).date(), "MARKET_MACRO_SESSION", (mstamp, qstamp))
    audit_macro_semantics(report, macro)

    esg = docs.get("esg-status.json") or {}
    report.check(esg.get("status") == "ok", "MARKET_ESG_STATUS", esg.get("status"))
    report.check(int(esg.get("companies") or 0) == len(core_symbols), "MARKET_ESG_CORE_COVERAGE", (esg.get("companies"), len(core_symbols)))
    report.check(int(esg.get("companiesWithMetrics") or 0) > 0, "MARKET_ESG_METRICS_EMPTY", esg.get("companiesWithMetrics"))

    watch = docs.get("watch-today.json") or {}
    report.check(watch.get("status") == "ok" and bool(watch.get("items") or watch.get("symbols")), "MARKET_WATCH_EMPTY", watch.get("status"))
    report.check(str(watch.get("sourceTime") or "") == str(source or ""), "MARKET_WATCH_ALIGNMENT", (watch.get("sourceTime"), source))
    return core_symbols


def audit_financial(report: Audit, financial_dir: Path, core_symbols):
    p = financial_dir / "manifest.json"
    if not report.check(p.exists(), "FINANCIAL_MANIFEST_MISSING", p):
        return
    try:
        data = load_json(p)
    except Exception as exc:
        report.check(False, "FINANCIAL_MANIFEST_INVALID", exc)
        return
    coverage = data.get("coverage") or {}
    companies = data.get("companies") or []
    symbols = [str(x.get("symbol") or "") for x in companies]
    report.check(data.get("schemaVersion") == 2, "FINANCIAL_SCHEMA", data.get("schemaVersion"))
    report.check(data.get("universe") == "VN100", "FINANCIAL_UNIVERSE", data.get("universe"))
    report.check(all(int(coverage.get(k) or 0) == 100 for k in ("members", "annual", "quarterly")), "FINANCIAL_COVERAGE", coverage)
    report.check(len(symbols) == len(set(symbols)) == 100, "FINANCIAL_SYMBOL_UNIQUENESS", len(symbols))
    if core_symbols:
        report.check(set(symbols) == set(core_symbols), "FINANCIAL_CORE_ALIGNMENT", f"onlyFinancial={sorted(set(symbols)-core_symbols)[:10]} onlyCore={sorted(core_symbols-set(symbols))[:10]}")
    for company in companies:
        years = company.get("years") or []
        quarters = company.get("quarters") or []
        report.check(all(str(y).isdigit() and int(y) <= datetime.now(VN_TZ).year for y in years), "FINANCIAL_FUTURE_YEAR", company.get("symbol"))
        report.check(all(str(q)[:4].isdigit() and int(str(q)[:4]) <= datetime.now(VN_TZ).year for q in quarters), "FINANCIAL_FUTURE_QUARTER", company.get("symbol"))


def audit_insights(report: Audit, insights_dir: Path, now):
    for name in ("insights-status.json", "event-status.json"):
        p = insights_dir / name
        if not report.check(p.exists(), "INSIGHTS_STATUS_MISSING", name):
            continue
        data = load_json(p)
        stamp = parse_ts(data.get("checkedAt"))
        report.check(stamp is not None and -5 <= (now - stamp).total_seconds() / 3600 <= 48, "INSIGHTS_STATUS_FRESHNESS", (name, data.get("checkedAt")))
        total = int(data.get("sourcesTotal") or 0)
        reachable = int(data.get("sourcesReachable") or 0)
        report.check(total > 0 and reachable / total >= .75, "INSIGHTS_SOURCE_REACHABILITY", (name, reachable, total))
        if name == "insights-status.json":
            report.check(int(data.get("symbolsCovered") or 0) >= 90, "INSIGHTS_SYMBOL_COVERAGE", data.get("symbolsCovered"))
            report.check(int(data.get("storedReports") or 0) > 0, "INSIGHTS_REPORTS_EMPTY", data.get("storedReports"))
        else:
            report.check(int(data.get("storedEvents") or 0) > 0, "EVENTS_EMPTY", data.get("storedEvents"))


def audit_forecast_monitor(report: Audit, repo_root: Path, now):
    base = repo_root / "data"
    manifest = load_json(base / "forecast-live-v10" / "manifest.json")
    integrity = load_json(base / "forecast-live-v10" / "integrity.json")
    live_integrity = load_json(base / "live-track" / "integrity.json")
    report.check(manifest.get("latest") == integrity.get("asOf"), "FORECAST_ARCHIVE_ALIGNMENT", (manifest.get("latest"), integrity.get("asOf")))
    report.check(integrity.get("status") == "PASS", "FORECAST_ARCHIVE_INTEGRITY", integrity.get("status"))
    report.check(live_integrity.get("status") == "PASS", "FORECAST_LIVE_TRACK_INTEGRITY", live_integrity.get("status"))
    report.future_safe(integrity.get("generatedAt"), now, "FORECAST_INTEGRITY_FUTURE")
    report.future_safe(live_integrity.get("generatedAt"), now, "FORECAST_LIVE_TRACK_FUTURE")
    report.check(int(manifest.get("count") or 0) >= 20, "FORECAST_ARCHIVE_DEPTH", manifest.get("count"))


def production_prefers_solution_core(repo_root: Path):
    """Return True only when the deployed Pages loader prefers the dedicated core branch."""
    try:
        text = (repo_root / "forecast-final-v12.js").read_text(encoding="utf-8")
    except Exception:
        return False
    required = (
        "solution-ai-core-data/data",
        "SOLUTION_CORE_FILES.has(name)",
        "[SOLUTION_CORE_ROOT,ROOT]",
        "window.__SOLUTION_AI_CORE_ROOT__=SOLUTION_CORE_ROOT",
    )
    return all(token in text for token in required)


def production_uses_finquery_main_core(repo_root: Path):
    """Return True when FinQuery Forecast is independent of SoluTION data branches."""
    try:
        text = (repo_root / "forecast-final-v12.js").read_text(encoding="utf-8")
    except Exception:
        return False
    required = (
        "const roots=[ROOT]",
        "financial-market-data/market/quotes.json",
        'scope:"finquery-market"',
    )
    forbidden = (
        "solution-ai-core-data/data",
        "solution-ai-live-data/solution-ai/live.json",
        "[SOLUTION_CORE_ROOT,ROOT]",
    )
    return all(token in text for token in required) and not any(token in text for token in forbidden)


def solution_core_is_authoritative(core_dir: Path, now):
    """Check the minimum freshness/proof needed before main may be treated as fallback-only."""
    try:
        dashboard = load_json(core_dir / "forecast-dashboard-v12.json")
        market = load_json(core_dir / "forecast-market-v13.json")
        release = load_json(core_dir / "release-audit-v20.json")
    except Exception:
        return False
    expected = latest_completed_session(now.astimezone(VN_TZ)).isoformat()
    sources = market.get("sources") or {}
    bridge = sources.get("postCloseBridge") or {}
    price_audit = sources.get("priceCrossSource") or {}
    published = len(dashboard.get("symbols") or {})
    validation = int(bridge.get("validationUniverseSymbols") or published or 0)
    return bool(
        str(dashboard.get("asOf") or "") == expected
        and release.get("status") == "PASS"
        and not (release.get("blockers") or [])
        and str(release.get("asOf") or "") == expected
        and str(sources.get("marketScanAsOf") or "") == expected
        and str(sources.get("priceSessionAsOf") or "") == expected
        and bridge.get("status") in {"PASS", "NOT_APPLICABLE_ALREADY_CURRENT"}
        and str(bridge.get("sessionDate") or "") == expected
        and price_audit.get("status") == "PASS"
        and float(price_audit.get("coverage") or 0) >= float(price_audit.get("requiredCoverage") or 1)
        and int(price_audit.get("mismatchCount") or 0) == 0
        and published >= math.ceil(max(1, validation) * .90)
    )


def audit_main_forecast(report: Audit, repo_root: Path, now, authoritative_core_ready=False):
    """Audit the main-branch forecast as production source or safe fallback.

    Pages deliberately prefers solution-ai-core-data for validated forecast core
    files. When that dedicated core is current and independently proven, an older
    main snapshot is a fallback condition, not a production freshness failure.
    The fallback must still remain structurally valid and the V21 overlay must
    abstain rather than rank against a stale core.
    """
    data = repo_root / "data"
    names = {
        "dashboard": "forecast-dashboard-v12.json",
        "current": "forecast-current-v12.json",
        "market": "forecast-market-v13.json",
        "release": "release-audit-v20.json",
        "session": "forecast-session-v21.json",
    }
    docs = {}
    for key, name in names.items():
        path = data / name
        if not report.check(path.exists(), "FORECAST_MAIN_FILE", name):
            continue
        try:
            docs[key] = load_json(path)
        except Exception as exc:
            report.check(False, "FORECAST_MAIN_JSON", f"{name}: {exc}")
    if not all(key in docs for key in ("dashboard", "current", "market", "release")):
        return

    dashboard = docs["dashboard"]
    current = docs["current"]
    market = docs["market"]
    release = docs["release"]
    expected = latest_completed_session(now.astimezone(VN_TZ)).isoformat()

    dates = {
        "dashboard": str(dashboard.get("asOf") or ""),
        "current": str(current.get("asOf") or ""),
        "market": str(market.get("asOf") or ""),
        "release": str(release.get("asOf") or ""),
    }
    main_current = all(value == expected for value in dates.values())
    freshness_check = report.warn if authoritative_core_ready else report.check
    freshness_check(main_current, "FORECAST_MAIN_SESSION", f"{dates} expected={expected}")
    report.check(release.get("status") == "PASS" and not (release.get("blockers") or []), "FORECAST_MAIN_RELEASE", {"status": release.get("status"), "blockers": release.get("blockers")})

    dash_symbols = set((dashboard.get("symbols") or {}).keys())
    current_symbols = set((current.get("symbols") or {}).keys())
    release_symbols = int((release.get("scope") or {}).get("symbols") or 0)
    report.check(bool(dash_symbols) and dash_symbols == current_symbols, "FORECAST_MAIN_SYMBOL_ALIGNMENT", f"dashboard={len(dash_symbols)} current={len(current_symbols)}")
    report.check(len(dash_symbols) == release_symbols, "FORECAST_MAIN_RELEASE_SCOPE", f"published={len(dash_symbols)} release={release_symbols}")

    versions = (market.get("version"), dashboard.get("modelVersion"), current.get("modelVersion"))
    report.check(bool(versions[0]) and len(set(versions)) == 1, "FORECAST_MAIN_VERSION_ALIGNMENT", versions)

    sources = market.get("sources") or {}
    freshness_check(str(sources.get("marketScanAsOf") or "") == expected, "FORECAST_MAIN_MARKET_SCAN", sources.get("marketScanAsOf"))
    freshness_check(str(sources.get("priceSessionAsOf") or "") == expected, "FORECAST_MAIN_PRICE_SESSION", sources.get("priceSessionAsOf"))
    price_audit = sources.get("priceCrossSource") or {}
    report.check(price_audit.get("status") == "PASS", "FORECAST_MAIN_PRICE_CROSS_SOURCE", price_audit.get("status"))
    report.check(float(price_audit.get("coverage") or 0) >= float(price_audit.get("requiredCoverage") or 1), "FORECAST_MAIN_PRICE_COVERAGE", price_audit)
    report.check(int(price_audit.get("mismatchCount") or 0) == 0, "FORECAST_MAIN_PRICE_MISMATCH", price_audit.get("mismatchCount"))

    if "session" not in docs:
        return
    session = docs["session"]
    alignment = session.get("forecastAlignment") or {}
    coverage = session.get("coverage") or {}
    report.check(session.get("status") == "PASS", "FORECAST_V21_STATUS", session.get("status"))
    report.check(float(coverage.get("coverageRatio") or 0) >= .90, "FORECAST_V21_COVERAGE", coverage)
    report.check(float(coverage.get("currentCoverageRatio") or 0) >= .70, "FORECAST_V21_CURRENT_COVERAGE", coverage)
    report.check(float(coverage.get("cutoffFreshCoverageRatio") or 0) >= .70, "FORECAST_V21_CUTOFF_COVERAGE", coverage)
    preferred = int((dashboard.get("promotion") or {}).get("preferredRankingHorizon") or 0)
    report.check(preferred > 0 and int(session.get("rankingHorizon") or 0) == preferred, "FORECAST_V21_HORIZON", (session.get("rankingHorizon"), preferred))

    if authoritative_core_ready and not main_current:
        fallback_safe = (
            str(session.get("coreAsOf") or "") == str(dashboard.get("asOf") or "")
            and alignment.get("status") == "STALE_CORE"
            and alignment.get("rankingEligible") is False
            and session.get("mode") == "PRICE_ONLY_STALE_CORE"
            and session.get("coreForecastUnchanged") is True
            and not (session.get("leaders") or [])
        )
        report.check(
            fallback_safe,
            "FORECAST_V21_FALLBACK_SAFE",
            {
                "coreAsOf": session.get("coreAsOf"),
                "mainAsOf": dashboard.get("asOf"),
                "alignment": alignment,
                "mode": session.get("mode"),
                "leaders": len(session.get("leaders") or []),
            },
        )
        report.warn(
            False,
            "FORECAST_V21_FALLBACK_STALE",
            {
                "mainCoreAsOf": dashboard.get("asOf"),
                "productionCoreExpected": expected,
                "mode": session.get("mode"),
                "rankingEligible": alignment.get("rankingEligible"),
            },
        )
        return

    report.check(str(session.get("coreAsOf") or "") == expected, "FORECAST_V21_CORE_SESSION", (session.get("coreAsOf"), expected))
    report.check(
        alignment.get("status") == "PASS"
        and alignment.get("rankingEligible") is True
        and str(alignment.get("actualCoreAsOf") or "") == expected
        and str(alignment.get("expectedCoreAsOf") or "") == expected,
        "FORECAST_V21_ALIGNMENT",
        alignment,
    )
    report.check(session.get("mode") == "FORECAST_ALIGNED" and session.get("coreForecastUnchanged") is True, "FORECAST_V21_MODE", (session.get("mode"), session.get("coreForecastUnchanged")))
    report.check(len(session.get("leaders") or []) == 10, "FORECAST_V21_LEADERS", len(session.get("leaders") or []))

def audit_solution_live(report: Audit, path: Path, now):
    if not report.check(path.exists(), "SOLUTION_LIVE_MISSING", path):
        return
    data = load_json(path)
    ok, policy, reason = solution_live_freshness(data, now)
    report.check(ok, "SOLUTION_LIVE_FRESHNESS", f"{policy}: {reason}")
    quotes = data.get("quotes") or {}
    report.check(sum(int(v) for v in (data.get("exchangeCounts") or {}).values()) == int(data.get("coverage") or 0), "SOLUTION_LIVE_EXCHANGE_COUNTS", data.get("exchangeCounts"))
    report.check(finite((quotes.get("FPT") or {}).get("price")) and float((quotes.get("FPT") or {}).get("price") or 0) > 0, "SOLUTION_LIVE_FPT", quotes.get("FPT"))


def audit_solution_core(report: Audit, core_dir: Path, now):
    names = ["forecast-dashboard-v12.json", "forecast-market-v13.json", "release-audit-v20.json"]
    if not all(report.check((core_dir / n).exists(), "SOLUTION_CORE_FILE_MISSING", n) for n in names):
        return
    dashboard = load_json(core_dir / names[0])
    market = load_json(core_dir / names[1])
    release = load_json(core_dir / names[2])
    expected = latest_completed_session(now.astimezone(VN_TZ)).isoformat()
    asof = str(dashboard.get("asOf") or "")
    report.check(asof == expected, "SOLUTION_CORE_SESSION", f"asOf={asof} expected={expected}")
    report.check(release.get("status") == "PASS", "SOLUTION_CORE_RELEASE_AUDIT", release.get("status"))
    report.check(str(release.get("asOf") or "") == asof, "SOLUTION_CORE_RELEASE_ALIGNMENT", (release.get("asOf"), asof))
    sources = market.get("sources") or {}
    bridge = sources.get("postCloseBridge") or {}
    bridge_status = bridge.get("status")
    bridge_ok = bridge_status in {"PASS", "NOT_APPLICABLE_ALREADY_CURRENT"}
    report.check(bridge_ok, "SOLUTION_CORE_BRIDGE", bridge)
    report.check(str(bridge.get("sessionDate") or "") == asof, "SOLUTION_CORE_BRIDGE_SESSION", (bridge.get("sessionDate"), asof))
    report.check(str(sources.get("marketScanAsOf") or "") == asof, "SOLUTION_CORE_MARKET_ALIGNMENT", (sources.get("marketScanAsOf"), asof))
    report.check(str(sources.get("priceSessionAsOf") or "") == asof, "SOLUTION_CORE_PRICE_SESSION_ALIGNMENT", (sources.get("priceSessionAsOf"), asof))
    price_audit = sources.get("priceCrossSource") or {}
    report.check(price_audit.get("status") == "PASS", "SOLUTION_CORE_PRICE_CROSS_SOURCE", price_audit.get("status"))
    report.check(float(price_audit.get("coverage") or 0) >= float(price_audit.get("requiredCoverage") or 1), "SOLUTION_CORE_PRICE_COVERAGE", price_audit)
    report.check(int(price_audit.get("mismatchCount") or 0) == 0, "SOLUTION_CORE_PRICE_MISMATCH", price_audit.get("mismatchCount"))
    if bridge_status == "PASS":
        report.check(bridge.get("completedSessionVerified") is True, "SOLUTION_CORE_BRIDGE_COMPLETION", bridge)
        report.check(bridge.get("independentCloseConfirmed") is True, "SOLUTION_CORE_BRIDGE_CONFIRMATION", bridge)
        report.check(float(bridge.get("coverage") or 0) >= float(bridge.get("minimumCoverage") or 1), "SOLUTION_CORE_BRIDGE_PRIMARY_COVERAGE", bridge)
        report.check(float(bridge.get("secondaryCoverage") or 0) >= float(bridge.get("minimumSecondaryCoverage") or 1), "SOLUTION_CORE_BRIDGE_SECONDARY_COVERAGE", bridge)
        report.check(int(bridge.get("mismatchCount") or 0) == 0, "SOLUTION_CORE_BRIDGE_MISMATCH", bridge)
    published = len(dashboard.get("symbols") or {})
    validation = int(bridge.get("validationUniverseSymbols") or published)
    report.check(published >= math.ceil(max(1, validation) * .90), "SOLUTION_CORE_SYMBOL_COVERAGE", (published, validation))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-dir", required=True)
    parser.add_argument("--financial-dir", required=True)
    parser.add_argument("--insights-dir", required=True)
    parser.add_argument("--solution-live")
    parser.add_argument("--solution-core-dir")
    parser.add_argument("--ignore-solution-ai", action="store_true")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--report-json")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    audit = Audit()
    core = audit_market(audit, Path(args.market_dir), now)
    audit_financial(audit, Path(args.financial_dir), core)
    audit_insights(audit, Path(args.insights_dir), now)
    audit_forecast_monitor(audit, Path(args.repo_root), now)
    repo_root = Path(args.repo_root)
    if args.ignore_solution_ai:
        core_route_ok = production_uses_finquery_main_core(repo_root)
        audit.check(core_route_ok, "FORECAST_PRODUCTION_CORE_ROUTE", "FinQuery Forecast must load main/data and FinQuery market quotes without SoluTION data branches")
        audit_main_forecast(audit, repo_root, now, authoritative_core_ready=False)
    else:
        if not args.solution_live or not args.solution_core_dir:
            parser.error("--solution-live and --solution-core-dir are required unless --ignore-solution-ai is set")
        solution_core_dir = Path(args.solution_core_dir)
        core_route_ok = production_prefers_solution_core(repo_root)
        audit.check(core_route_ok, "FORECAST_PRODUCTION_CORE_ROUTE", "Full audit expects dedicated solution-ai-core-data before main fallback")
        authoritative_core_ready = core_route_ok and solution_core_is_authoritative(solution_core_dir, now)
        audit_main_forecast(audit, repo_root, now, authoritative_core_ready=authoritative_core_ready)
        audit_solution_live(audit, Path(args.solution_live), now)
        audit_solution_core(audit, solution_core_dir, now)
    category_summary = {}
    for row in audit.results:
        bucket = category_summary.setdefault(row["category"], {"PASS": 0, "WARN": 0, "FAIL": 0})
        bucket[row["status"]] = bucket.get(row["status"], 0) + 1
    result = {
        "status": "PASS" if not audit.errors else "FAIL",
        "checkedAt": now.isoformat(),
        "checks": audit.checks,
        "passes": sum(row["status"] == "PASS" for row in audit.results),
        "failures": len(audit.errors),
        "warningChecks": len(audit.warnings),
        "categories": category_summary,
        "errors": audit.errors,
        "warnings": audit.warnings,
        "results": audit.results,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if audit.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
