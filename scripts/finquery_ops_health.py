#!/usr/bin/env python3
"""FinQuery production operations health: source-PIT, cadence and anonymous RBAC.

This is a read-only diagnostic. Never edits model outputs or auto-promotes stale
predictions. GitHub Actions owns alert delivery; this module owns the policy.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import datetime, time, timezone
from pathlib import Path

from vn_exchange_calendar import VN_TZ, is_trading_day, latest_completed_session, trading_session_age

ROOT = "https://raw.githubusercontent.com/NCKHtop1/vmews-risk-analytics"
SOURCES = {
    "quotes": f"{ROOT}/financial-market-data/market/quotes.json",
    "risk": f"{ROOT}/financial-market-data/market/risk-monitor.json",
    "strategy": f"{ROOT}/financial-market-data/market/strategy-indicators.json",
    "intraday": f"{ROOT}/financial-market-data/market/intraday-status.json",
    "news": f"{ROOT}/financial-market-data/market/news-latest.json",
    "macro": f"{ROOT}/financial-market-data/market/macro.json",
    "financial": f"{ROOT}/financial-report-data/data/manifest.json",
    "esg": f"{ROOT}/financial-market-data/market/esg-status.json",
    "forecast": f"{ROOT}/main/data/forecast-session-v21.json",
    "live_track": f"{ROOT}/main/data/live-track/track-record.json",
}
SEVERITIES = {"OK": 0, "WARNING": 1, "CRITICAL": 2}


def parse_ts(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def day_of(value):
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def clock(now):
    now = now.astimezone(VN_TZ)
    business_day = is_trading_day(now.date(), require_certified=True)
    hm = now.time().replace(tzinfo=None)
    live = business_day and (time(9, 30) <= hm <= time(11, 40) or time(13, 25) <= hm <= time(15, 0))
    expected = now.date() if business_day and hm >= time(9, 25) else latest_completed_session(now)
    return {"live": live, "expectedQuoteDate": expected.isoformat(),
            "completedSession": latest_completed_session(now).isoformat(),
            "vnTime": now.isoformat(), "tradingDay": business_day}


def evaluate(data, now=None, production=None):
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    ctx = clock(now)
    checks = []

    def add(code, severity, title, evidence=None):
        if severity not in SEVERITIES:
            raise ValueError(severity)
        checks.append({"code": code, "severity": severity, "title": title,
                       "evidence": evidence if evidence is not None else {}})

    def payload(name):
        value = data.get(name)
        if not isinstance(value, dict):
            add("SOURCE_" + name.upper(), "WARNING", f"Không tải được snapshot {name}")
            return {}
        return value

    prod = production or {}
    if not prod.get("ok"):
        add("PRODUCTION_HTTP", "CRITICAL", "FinQuery production health/auth không đạt", prod)
    elif not (prod.get("sessionAnonymous") and prod.get("adminProtected") and prod.get("dashboardProtected")):
        add("AUTH_GUARD", "CRITICAL", "Quyền truy cập hoặc session không được bảo vệ đúng", prod)
    else:
        add("PRODUCTION_HTTP", "OK", "Production, Neon và đường dẫn giới hạn quyền hoạt động")

    quote = payload("quotes")
    price_date = day_of(quote.get("latestSourceTime") or quote.get("sourceTime"))
    exp = day_of(ctx["expectedQuoteDate"])
    quote_cov = int(quote.get("coverage") or 0)
    quote_count = int(quote.get("expected") or 0)
    if quote:
        if quote_count <= 0 or quote_cov < math.ceil(quote_count * .9):
            add("QUOTE_COVERAGE", "CRITICAL", "Độ phủ giá thấp hơn 90%",
                {"coverage": quote_cov, "expected": quote_count})
        else:
            add("QUOTE_COVERAGE", "OK", "Độ phủ giá trên ngưỡng 90%",
                {"coverage": quote_cov, "expected": quote_count})
        if not price_date or (exp and price_date < exp):
            add("QUOTE_SESSION", "CRITICAL", "Giá không đạt phiên giao dịch dự kiến",
                {"observed": str(price_date), "expected": str(exp)})
        else:
            add("QUOTE_SESSION", "OK", "Snapshot giá đúng phiên",
                {"date": str(price_date)})
        age = parse_ts(quote.get("latestSourceTime") or quote.get("sourceTime"))
        if ctx["live"] and age:
            lag = max(0., (now - age).total_seconds() / 60)
            if lag > 55:
                severity = "CRITICAL"
            elif lag > 30:
                severity = "WARNING"
            else:
                severity = "OK"
            add("QUOTE_LAG", severity, "Độ trễ giá trong phiên", {"minutes": round(lag, 1)})
        elif ctx["live"]:
            add("QUOTE_LAG", "CRITICAL", "Thiếu timestamp nguồn giá trong phiên")

    risk = payload("risk")
    if risk and quote:
        risk_date = day_of(risk.get("sourceDate") or risk.get("sourceTime"))
        same = risk_date == price_date
        add("RISK_QUOTE_SYNC", "OK" if same else "CRITICAL",
            "Risk và giá cùng phiên" if same else "Risk và giá khác phiên — chặn tín hiệu kết hợp",
            {"risk": str(risk_date), "quotes": str(price_date)})

    strategy = payload("strategy")
    if strategy and quote:
        live_source = parse_ts(strategy.get("sourceTime"))
        quote_source = parse_ts(quote.get("latestSourceTime"))
        aligned = live_source is not None and quote_source is not None and live_source == quote_source
        add("SCANNER_QUOTE_SYNC", "OK" if aligned else "WARNING",
            "Scanner và giá đồng bộ" if aligned else "Scanner và giá có phiên/timestamp khác nhau",
            {"scannerSource": strategy.get("sourceTime"), "quoteSource": quote.get("latestSourceTime")})
        symbols = strategy.get("symbols") or {}
        discovery = [x for x in symbols.values() if isinstance(x, dict) and x.get("tier") == "DISCOVERY"]
        stale = sum(trading_session_age(x.get("barDate"), ctx["completedSession"]) >= 2 for x in discovery)
        very_stale = sum(trading_session_age(x.get("barDate"), ctx["completedSession"]) >= 10 for x in discovery)
        sev = "WARNING" if stale else "OK"
        add("DISCOVERY_HISTORY", sev, "Độ mới dữ liệu scanner Discovery",
            {"eligible": len(discovery), "staleAtLeast2Sessions": stale,
             "staleAtLeast10Sessions": very_stale})

    overlay = payload("forecast")
    if overlay:
        forecast_day = day_of(overlay.get("coreAsOf"))
        completed = day_of(ctx["completedSession"])
        lag = trading_session_age(forecast_day, completed) if forecast_day else 99
        # The model already abstains while stale. Alert operators, never resume ranking.
        status = (overlay.get("forecastAlignment") or {}).get("status")
        sev = "CRITICAL" if lag >= 2 else "WARNING" if lag or status == "STALE_CORE" else "OK"
        add("FORECAST_CORE", sev, "Độ mới lõi dự báo đã niêm phong",
            {"coreAsOf": str(forecast_day), "expectedCompletedSession": str(completed),
             "lagSessions": lag, "alignment": status, "rankingEligible":
             (overlay.get("forecastAlignment") or {}).get("rankingEligible")})
        if lag and (overlay.get("forecastAlignment") or {}).get("rankingEligible") is True:
            add("FORECAST_FAIL_CLOSED", "CRITICAL", "Lõi stale nhưng vẫn cho phép ranking")
        else:
            add("FORECAST_FAIL_CLOSED", "OK", "Lõi stale được fail-closed hoặc lõi hiện hành")

    intraday = payload("intraday")
    if intraday:
        ok = int(intraday.get("success") or 0)
        expected = int(intraday.get("expected") or 0)
        ratio = ok / expected if expected else 0
        sev = "CRITICAL" if ratio < .9 else "WARNING" if ratio < .99 else "OK"
        add("INTRADAY_COVERAGE", sev, "Độ phủ nến intraday",
            {"success": ok, "expected": expected, "ratio": round(ratio, 4),
             "errors": len(intraday.get("errors") or [])})
        intraday_date = parse_ts(intraday.get("checkedAt"))
        if ctx["live"] and intraday_date and (now - intraday_date).total_seconds() > 3600 * 2:
            add("INTRADAY_FRESHNESS", "WARNING", "Nến intraday trễ hơn hai giờ trong phiên")

    financial = payload("financial")
    if financial:
        cov = financial.get("coverage") or {}
        annual = int(cov.get("annual") or 0)
        quarter = int(cov.get("quarterly") or 0)
        members = int(cov.get("members") or 0)
        sev = "CRITICAL" if members == 0 or min(annual, quarter) < members * .9 else "OK"
        add("FINANCIAL_COVERAGE", sev, "Độ phủ BCTC năm và quý",
            {"members": members, "annual": annual, "quarterly": quarter})
        age = parse_ts(financial.get("updatedAt"))
        if age:
            hours = max(0., (now - age).total_seconds() / 3600)
            add("FINANCIAL_REFRESH", "WARNING" if hours > 28 else "OK",
                "Tuổi manifest BCTC", {"hours": round(hours, 1)})
        else:
            add("FINANCIAL_REFRESH", "WARNING", "Thiếu thời điểm cập nhật BCTC")

    news = payload("news")
    if news:
        t = parse_ts(news.get("checkedAt") or news.get("lastSuccessAt"))
        age = max(0., (now-t).total_seconds() / 3600) if t else None
        # Publisher RSS has independent cadence; never invent an up-to-the-minute guarantee.
        severity = "WARNING" if age is None or (age > 4 and ctx["live"]) else "OK"
        add("NEWS_FRESHNESS", severity, "Tuổi snapshot tin tức",
            {"hours": round(age, 2) if age is not None else None})

    macro = payload("macro")
    if macro:
        t = parse_ts(macro.get("lastSuccessAt") or macro.get("checkedAt"))
        hours = max(0., (now-t).total_seconds() / 3600) if t else None
        severity = "WARNING" if hours is None or hours > 72 else "OK"
        add("MACRO_FRESHNESS", severity, "Tuổi snapshot VBMA/macro",
            {"hours": round(hours, 1) if hours is not None else None})
        warnings = sum(1 for v in (macro.get("sources") or []) if v.get("qualityStatus") == "warning")
        if warnings:
            add("MACRO_QUALITY", "WARNING", "Có nguồn vĩ mô bị cảnh báo chất lượng",
                {"warningSources": warnings})

    esg = payload("esg")
    if esg:
        companies = int(esg.get("companies") or 0)
        covered = int(esg.get("companiesWithMetrics") or 0)
        add("ESG_COVERAGE", "WARNING" if companies and covered < companies * .9 else "OK",
            "Độ phủ chỉ tiêu ESG đã xác minh",
            {"companiesWithMetrics": covered, "companies": companies})

    track = payload("live_track")
    if track:
        calib = (track.get("calibrationLiveMonitor") or {})
        if calib.get("status") == "UNSTABLE_KEEP_WITHHELD":
            add("MODEL_CALIBRATION", "WARNING",
                "Calibration chưa ổn định; giữ trạng thái withheld",
                {"status": calib.get("status"), "brierSkill": calib.get("brierSkill")})

    overall = max((x["severity"] for x in checks), key=lambda x: SEVERITIES[x], default="WARNING")
    return {"schemaVersion": 1, "checkedAt": now.isoformat(), "overall": overall,
            "operatingSession": ctx, "checks": checks,
            "counts": {k: sum(x["severity"] == k for x in checks) for k in SEVERITIES},
            "readOnly": True, "autoPromoteModel": False}


def http_json(url, timeout=12):
    request = urllib.request.Request(url, headers={
        "User-Agent": "FinQuery-Operations-Monitor/1.0", "Accept": "application/json",
        "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        return json.loads(response.read(2_500_000))


def probe_production(base="https://finquery.info.vn"):
    result = {"ok": False, "sessionAnonymous": False, "adminProtected": False,
              "dashboardProtected": False}
    request = urllib.request.Request(base + "/healthz",
        headers={"User-Agent": "FinQuery-Operations-Monitor/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read(200_000))
            result["ok"] = (response.status == 200 and data.get("ok") is True
                            and data.get("authConfigured") is True
                            and data.get("databaseReachable") is True)
    except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as exc:
        result["error"] = type(exc).__name__
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    client = urllib.request.build_opener(NoRedirect)
    for key, path, accepted in [
        ("sessionAnonymous", "/api/auth/session", {200}),
        ("adminProtected", "/api/admin/users", {401, 403}),
        ("dashboardProtected", "/financial-report/index.html?symbol=MBB&mode=quarter", {302, 303, 307, 308}),
    ]:
        request = urllib.request.Request(base + path,
            headers={"User-Agent": "FinQuery-Operations-Monitor/1.0"})
        try:
            try:
                response = client.open(request, timeout=12)
            except urllib.error.HTTPError as err:
                response = err
            with response:
                status = response.status
                if key == "sessionAnonymous" and status == 200:
                    payload = json.loads(response.read(40_000))
                    result[key] = payload.get("authenticated") is False
                elif key == "dashboardProtected":
                    result[key] = status in accepted and "/login" in (response.headers.get("Location") or "")
                else:
                    result[key] = status in accepted
        except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as exc:
            result[key + "Error"] = type(exc).__name__
    return result


def markdown_report(result):
    lines = [f"# FinQuery Operations — {result['overall']}",
             f"Kiểm tra UTC: {result['checkedAt']}",
             f"Phiên giá dự kiến: {result['operatingSession']['expectedQuoteDate']}",
             "", "| Mức độ | Hạng mục | Bằng chứng |", "|---|---|---|"]
    for row in result["checks"]:
        evidence = json.dumps(row["evidence"], ensure_ascii=False)
        if len(evidence) > 180:
            evidence = evidence[:177] + "..."
        evidence = evidence.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['severity']} | {row['code']} — {row['title']} | {evidence} |")
    lines += ["", "Tự động giám sát chỉ đọc. Tín hiệu stale phải tiếp tục abstain; không tự động thăng cấp mô hình.",
              "Data contract: đúng phiên, độ phủ, thời điểm nguồn và kiểm tra quyền truy cập."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--fixture-dir", type=Path)
    p.add_argument("--now", help="Timezone-aware ISO timestamp for deterministic QA")
    p.add_argument("--output", type=Path, default=Path("finquery-ops-health.json"))
    p.add_argument("--markdown", type=Path, default=Path("finquery-ops-health.md"))
    p.add_argument("--fail-on-critical", action="store_true")
    args = p.parse_args(argv)
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        p.error("--now must have an explicit timezone")
    data = {}
    for name, url in SOURCES.items():
        try:
            if args.fixture_dir:
                data[name] = json.loads((args.fixture_dir / (name + ".json")).read_text())
            else:
                data[name] = http_json(url)
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            data[name] = None
            print(f"::warning::Source {name}: {type(exc).__name__}", file=sys.stderr)
    if args.fixture_dir:
        production = json.loads((args.fixture_dir / "production.json").read_text())
    else:
        production = probe_production()
    result = evaluate(data, now, production)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.markdown.write_text(markdown_report(result))
    print(json.dumps({"overall": result["overall"], "checkedAt": result["checkedAt"],
                      "counts": result["counts"], "critical": [x["code"] for x in result["checks"]
                      if x["severity"] == "CRITICAL"]}, ensure_ascii=False))
    return 2 if args.fail_on_critical and result["overall"] == "CRITICAL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
