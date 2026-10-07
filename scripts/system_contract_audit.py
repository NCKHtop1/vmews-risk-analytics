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


def audit_market(report: Audit, market_dir: Path, now):
    required = [
        "universe.json", "quotes.json", "intraday-status.json", "technical-signals.json",
        "strategy-indicators.json", "risk-monitor.json", "news-latest.json", "macro.json",
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

    news = docs.get("news-latest.json") or {}
    report.check(news.get("status") == "ok" and 0 < len(news.get("items") or []) <= 150, "MARKET_NEWS_CONTENT", (news.get("status"), len(news.get("items") or [])))
    nstamp = parse_ts(news.get("checkedAt") or news.get("generatedAt"))
    report.check(nstamp is not None and -5 <= (now - nstamp).total_seconds() / 60 <= 45, "MARKET_NEWS_FRESHNESS", news.get("checkedAt"))

    macro = docs.get("macro.json") or {}
    mstamp = parse_ts(macro.get("checkedAt") or macro.get("generatedAt"))
    report.check(macro.get("status") == "ok" and mstamp is not None, "MARKET_MACRO_STATUS", macro.get("status"))
    if mstamp and qstamp:
        report.check(mstamp.astimezone(VN_TZ).date() >= qstamp.astimezone(VN_TZ).date(), "MARKET_MACRO_SESSION", (mstamp, qstamp))

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
    parser.add_argument("--solution-live", required=True)
    parser.add_argument("--solution-core-dir", required=True)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--report-json")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    audit = Audit()
    core = audit_market(audit, Path(args.market_dir), now)
    audit_financial(audit, Path(args.financial_dir), core)
    audit_insights(audit, Path(args.insights_dir), now)
    audit_forecast_monitor(audit, Path(args.repo_root), now)
    audit_solution_live(audit, Path(args.solution_live), now)
    audit_solution_core(audit, Path(args.solution_core_dir), now)
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
