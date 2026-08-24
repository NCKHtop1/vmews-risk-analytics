"""Fail-closed release audit for every published HOSE forecast and evidence feed."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_v13_market_model import session_limit, tick_size  # noqa: E402
from forecast_v14_signal_audit import security_match  # noqa: E402
from refresh_institutional_flow_v20 import completed_session  # noqa: E402


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _business_age(observed: str | None, as_of: str) -> int:
    if not observed:
        return 99
    cursor = date.fromisoformat(observed[:10])
    end = date.fromisoformat(as_of[:10])
    age = 0
    while cursor < end:
        cursor += timedelta(days=1)
        age += cursor.weekday() < 5
    return age


def _genuine_flow(row: dict[str, Any], kind: str) -> bool:
    prefix = "foreign" if kind == "foreign" else "prop"
    return any(abs(float(row.get(f"{prefix}{field}Value") or 0)) > 1e-9 for field in ("Buy", "Sell", "Net"))


def _headline_items(payload: dict[str, Any]) -> Iterable[tuple[str, str, str, bool]]:
    """Yield source, assigned ticker, title and whether identity should be explicit."""
    for symbol, rows in (payload.get("research") or {}).items():
        for row in rows if isinstance(rows, list) else []:
            yield "research-news", symbol, str(row.get("title") or ""), True
    for symbol, rows in (payload.get("broadResearch") or {}).items():
        for row in rows if isinstance(rows, list) else []:
            yield "research-news-v10", symbol, str(row.get("title") or ""), True
    for symbol, rows in (payload.get("fireant") or {}).items():
        for row in rows if isinstance(rows, list) else []:
            yield "fireant", symbol, str(row.get("title") or ""), True
    for symbol, value in (payload.get("community") or {}).items():
        if not isinstance(value, dict):
            continue
        for key in ("claims", "watchlist"):
            for row in value.get(key) or []:
                yield f"community-{key}", symbol, str(row.get("title") or ""), True
    for symbol, snapshot in (payload.get("dashboard") or {}).items():
        evidence = snapshot.get("evidence") or {}
        for key in ("recent", "decisionRecent", "communityWatchlist"):
            for row in evidence.get(key) or []:
                yield f"dashboard-{key}", symbol, str(row.get("title") or ""), False
        for row in (snapshot.get("decisionNews") or {}).get("items") or []:
            yield "dashboard-decisionNews", symbol, str(row.get("title") or ""), False


def run_audit() -> dict[str, Any]:
    dashboard = _json(DATA / "forecast-dashboard-v12.json")
    current = _json(DATA / "forecast-current-v12.json")
    market = _json(DATA / "forecast-market-v13.json")
    flow = _json(DATA / "flow-v12.json")
    flow_audit = _json(DATA / "flow-audit-v12.json")
    research = _json(DATA / "research-news.json")
    broad_research = _json(DATA / "research-news-v10.json")
    fireant = _json(DATA / "fireant-intelligence-v18.json")
    community = _json(DATA / "community-intelligence-live-v19.json")

    blockers: list[str] = []
    warnings: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            blockers.append(message)

    symbols = set((dashboard.get("symbols") or {}))
    current_symbols = set((current.get("symbols") or {}))
    flow_symbols = set((flow.get("symbols") or {}))
    as_of = str(dashboard.get("asOf") or "")[:10]
    require(len(symbols) >= 400, f"published universe collapsed to {len(symbols)} symbols")
    require(symbols == current_symbols, "dashboard/current symbol universes differ")
    require(symbols == flow_symbols, f"flow universe differs: missing={sorted(symbols-flow_symbols)[:20]} extra={sorted(flow_symbols-symbols)[:20]}")
    require(as_of == str(market.get("asOf") or "")[:10], "dashboard and market as-of dates differ")
    require(as_of == str((market.get("sources") or {}).get("marketScanAsOf") or "")[:10], "market scan and forecast dates differ")

    expected_version = "VMEWS-MARKET-FORECAST-20.1.0"
    require(market.get("version") == expected_version, "market artifact is not V20.1")
    require(dashboard.get("modelVersion") == expected_version, "dashboard model version differs from market")
    require(current.get("modelVersion") == expected_version, "current model version differs from market")
    require((market.get("model") or {}).get("promotion", {}).get("status") == "PASS", "sealed price promotion is not PASS")
    governance = (market.get("model") or {}).get("governance") or {}
    require(governance.get("centralForecastUsesUnvalidatedPrior") is False, "unvalidated live context can alter the central forecast")
    require(governance.get("livePriorIndependentlyBacktested") is False, "live context audit semantics are inconsistent")
    price_cross_source = (market.get("sources") or {}).get("priceCrossSource") or {}
    require(price_cross_source.get("status") == "PASS", "same-session current-price cross-source gate is not PASS")
    require(
        float(price_cross_source.get("coverage") or 0) >= float(price_cross_source.get("requiredCoverage") or 1),
        "current-price cross-source coverage is below its required minimum",
    )
    require(int(price_cross_source.get("mismatchCount") or 0) == 0, "current-price sources disagree beyond exchange-aware tolerance")

    quote_count = 0
    neutral_points = 0
    market_sources: Counter[str] = Counter()
    stale_price_symbols: list[str] = []
    stale_flow_prior_violations: list[str] = []
    chart_mismatches: list[str] = []
    quote_failures: list[str] = []

    model_horizons = (market.get("model") or {}).get("horizons") or {}
    for symbol in sorted(symbols):
        snapshot = dashboard["symbols"][symbol]
        current_snapshot = current["symbols"][symbol]
        if snapshot != current_snapshot:
            blockers.append(f"{symbol}: dashboard/current snapshots differ")
        close = snapshot.get("close")
        exchange = str(snapshot.get("exchange") or "HOSE")
        market_sources[str(snapshot.get("marketDataSource") or "UNKNOWN")] += 1
        if snapshot.get("dataFreshness") != "CURRENT" or str(snapshot.get("date") or "")[:10] != as_of:
            stale_price_symbols.append(symbol)
        chart = (dashboard.get("charts") or {}).get(symbol) or []
        if not chart or chart[-1].get("date") != snapshot.get("date") or chart[-1].get("rawClose") != close:
            chart_mismatches.append(symbol)
        if not _finite(close) or float(close) <= 0:
            quote_failures.append(f"{symbol}: invalid close")
            continue
        horizons = snapshot.get("horizons") or {}
        if set(horizons) != {"1", "2", "3", "4", "5"}:
            quote_failures.append(f"{symbol}: incomplete horizons")
            continue
        for key, forecast in horizons.items():
            quote_count += 1
            horizon = int(key)
            point = forecast.get("expectedPrice")
            low = forecast.get("q20Price")
            high = forecast.get("q80Price")
            bear = forecast.get("bearScenarioPrice")
            bull = forecast.get("bullScenarioPrice")
            numeric = (point, low, high, bear, bull, forecast.get("expectedReturn"), forecast.get("expectedAbsReturn"))
            if not all(_finite(value) for value in numeric):
                quote_failures.append(f"{symbol}/T+{key}: non-finite quote")
                continue
            floor, ceiling = session_limit(float(close), horizon, exchange)
            grid_values = (point, low, high, bear, bull)
            if any(float(value) % tick_size(float(value), exchange) != 0 for value in grid_values):
                quote_failures.append(f"{symbol}/T+{key}: off-tick price")
            if not (float(low) <= float(point) <= float(high)):
                quote_failures.append(f"{symbol}/T+{key}: q20/point/q80 ordering")
            if not (floor <= float(low) <= ceiling and floor <= float(high) <= ceiling):
                quote_failures.append(f"{symbol}/T+{key}: interval outside session limits")
            if not (floor <= float(bear) <= float(close) <= float(bull) <= ceiling):
                quote_failures.append(f"{symbol}/T+{key}: scenario ordering or limit")
            if float(bear) == float(bull):
                quote_failures.append(f"{symbol}/T+{key}: flat scenarios")
            if not math.isclose(math.log(float(point) / float(close)), float(forecast["expectedReturn"]), abs_tol=1e-11):
                quote_failures.append(f"{symbol}/T+{key}: return/price mismatch")
            contributions = forecast.get("expertContributions") or {}
            if not math.isclose(sum(float(value) for value in contributions.values()), float(forecast["expectedReturn"]), abs_tol=1e-11):
                quote_failures.append(f"{symbol}/T+{key}: contribution sum mismatch")
            scenario_components = ((forecast.get("liveEvidence") or {}).get("components") or {})
            if forecast.get("liveAdjustmentAppliedToCentralForecast") is not False:
                quote_failures.append(f"{symbol}/T+{key}: live context can replace the central forecast")
            if not math.isclose(float(forecast.get("liveAdjustmentReturn") or 0), 0.0, abs_tol=1e-15):
                quote_failures.append(f"{symbol}/T+{key}: nonzero live adjustment on central forecast")
            if not math.isclose(
                sum(float(value) for value in scenario_components.values()),
                float(forecast.get("scenarioAdjustmentReturn") or 0),
                abs_tol=1e-11,
            ):
                quote_failures.append(f"{symbol}/T+{key}: context scenario attribution mismatch")
            if float(forecast["expectedAbsReturn"]) <= 0 or not forecast.get("magnitudeValidated"):
                quote_failures.append(f"{symbol}/T+{key}: unsigned magnitude unavailable")
            if forecast.get("crossSectionalRankUniverse") != len(symbols) or not (0 < float(forecast.get("crossSectionalRankPercentile") or 0) <= 1):
                quote_failures.append(f"{symbol}/T+{key}: invalid cross-sectional rank")
            model_horizon = model_horizons.get(key) or {}
            direction_pass = model_horizon.get("directionStatus") == "PASS"
            point_pass = model_horizon.get("pointDirectionStatus") == "PASS"
            cost_pass = ((model_horizon.get("sealedAudit") or {}).get("costAwareLongAudit") or {}).get("status") == "PASS"
            if bool(forecast.get("directionValidated")) != direction_pass:
                quote_failures.append(f"{symbol}/T+{key}: probability gate mismatch")
            if bool(forecast.get("pointDirectionValidated")) != point_pass:
                quote_failures.append(f"{symbol}/T+{key}: sign gate mismatch")
            if bool(forecast.get("conditionalValueValidated")) != cost_pass:
                quote_failures.append(f"{symbol}/T+{key}: after-cost gate mismatch")
            if not (0 <= float(forecast.get("probUp") or 0) <= 1):
                quote_failures.append(f"{symbol}/T+{key}: invalid latent probability")
            neutral_points += int(float(point) == float(close))
            typed = snapshot.get("flow") or {}
            stale_typed = all((typed.get(kind) or {}).get("stale", True) for kind in ("foreign", "proprietary"))
            live_flow = float((((forecast.get("liveEvidence") or {}).get("components") or {}).get("FLOW") or 0))
            if stale_typed and abs(live_flow) > 1e-12:
                stale_flow_prior_violations.append(f"{symbol}/T+{key}")

    require(not stale_price_symbols, f"stale price symbols: {stale_price_symbols[:20]}")
    require(not chart_mismatches, f"chart/quote mismatches: {chart_mismatches[:20]}")
    require(quote_count == len(symbols) * 5, f"audited {quote_count} quotes, expected {len(symbols)*5}")
    require(neutral_points / max(1, quote_count) <= .05, f"too many flat point forecasts: {neutral_points}/{quote_count}")
    require(not quote_failures, f"forecast contract failures ({len(quote_failures)}): {quote_failures[:20]}")
    require(not stale_flow_prior_violations, f"stale flow still drives live prior: {stale_flow_prior_violations[:20]}")

    # Re-audit the source archive rather than trusting its summary.
    latest_completed = completed_session().isoformat()
    flow_row_count = 0
    future_flow_rows: list[str] = []
    duplicate_flow_dates: list[str] = []
    invalid_flow_values: list[str] = []
    source_latest = {"foreign": [], "proprietary": []}
    for symbol, rows in sorted((flow.get("symbols") or {}).items()):
        dates = [str(row.get("date") or "")[:10] for row in rows]
        flow_row_count += len(rows)
        if dates != sorted(set(dates)):
            duplicate_flow_dates.append(symbol)
        for row in rows:
            observed = str(row.get("date") or "")[:10]
            if observed > latest_completed:
                future_flow_rows.append(f"{symbol}:{observed}")
            for key, value in row.items():
                if key.endswith("Value") and not _finite(value):
                    invalid_flow_values.append(f"{symbol}:{observed}:{key}")
        for kind in source_latest:
            latest = next((str(row["date"])[:10] for row in reversed(rows) if _genuine_flow(row, kind)), None)
            if latest:
                source_latest[kind].append(latest)
        snapshot_flow = (dashboard["symbols"][symbol].get("flow") or {})
        for kind in source_latest:
            typed = snapshot_flow.get(kind) or {}
            latest = next((str(row["date"])[:10] for row in reversed(rows) if _genuine_flow(row, kind) and str(row["date"])[:10] <= as_of), None)
            require(typed.get("latestDate") == latest, f"{symbol}/{kind}: typed/archive latest date mismatch")
            expected_age = _business_age(latest, as_of)
            require(int(typed.get("ageSessions", 99)) == expected_age, f"{symbol}/{kind}: incorrect age")
            require(bool(typed.get("stale")) == (expected_age > 3), f"{symbol}/{kind}: stale flag mismatch")
            if expected_age > 3:
                available_key = "foreignAvailable" if kind == "foreign" else "propAvailable"
                require(int(snapshot_flow.get(available_key) or 0) == 0, f"{symbol}/{kind}: stale feature was not masked")

    require(not future_flow_rows, f"future/unfinished flow rows: {future_flow_rows[:20]}")
    require(not duplicate_flow_dates, f"duplicate/unsorted flow dates: {duplicate_flow_dates[:20]}")
    require(not invalid_flow_values, f"invalid flow values: {invalid_flow_values[:20]}")
    summary = flow_audit.get("summary") or {}
    require(int(summary.get("refreshRequestedSymbols") or 0) == len(symbols), "flow refresh did not request the full published universe")
    require(int(summary.get("refreshRequestedKinds") or 0) == len(symbols) * 2, "flow refresh did not attempt both sources for every symbol")
    require(float(summary.get("refreshSuccessCoverage") or 0) == 1.0, "one or more institutional-flow requests failed")
    require(int(summary.get("rejectedFetchShards") or 0) == 0, "one or more isolated flow shards were absent or corrupt")

    headline_payload = {
        "research": research.get("symbols") or {},
        "broadResearch": broad_research.get("symbols") or {},
        "fireant": fireant.get("symbols") or {},
        "community": community.get("symbols") or {},
        "dashboard": dashboard.get("symbols") or {},
    }
    headline_count = 0
    issuer_mismatches: list[str] = []
    weak_identity: list[str] = []
    by_source: Counter[str] = Counter()
    for source, symbol, title, explicit in _headline_items(headline_payload):
        if not title:
            continue
        headline_count += 1
        by_source[source] += 1
        if not security_match(symbol, title, symbols, require_explicit=False):
            issuer_mismatches.append(f"{source}/{symbol}: {title[:140]}")
        elif explicit and not security_match(symbol, title, symbols, require_explicit=True):
            weak_identity.append(f"{source}/{symbol}: {title[:140]}")
    require(not issuer_mismatches, f"issuer-mixed headlines ({len(issuer_mismatches)}): {issuer_mismatches[:20]}")
    if weak_identity:
        warnings.append(f"{len(weak_identity)} raw headlines lack an explicit ticker/known alias and remain non-authoritative")

    # The browser may accept an optional user key, but checked-in UI must never
    # contain an actual provider secret; production failover remains server-side.
    frontend_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (
            ROOT / "forecast-final.html",
            ROOT / "forecast-final-v12.js",
            ROOT / "solution-ai-v17.js",
        )
    )
    leaked = re.findall(r"(?:AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,})", frontend_text)
    backend_text = (ROOT / "api" / "solution-ai.js").read_text(encoding="utf-8")
    require(not leaked, "provider secret pattern found in public frontend")
    require("Object.assign(horizon,adjustment)" not in frontend_text.replace(" ", ""), "live browser overlay can overwrite sealed forecast fields")
    forbidden_placeholder_wording = "không điền" + " giả"
    require(forbidden_placeholder_wording not in frontend_text.casefold(), "internal data-engineering wording leaked into the interface")
    require("appliedToCentralForecast:false" in frontend_text.replace(" ", ""), "browser scenario overlay lacks an immutable-central-forecast marker")
    for provider_name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY"):
        require(provider_name in backend_text, f"AI server failover is missing {provider_name}")
    require("failoverAvailable" in backend_text and "unavailableProviders" in backend_text, "AI health/failover disclosure is incomplete")

    horizon_metrics: dict[str, Any] = {}
    for key in map(str, range(1, 6)):
        horizon = model_horizons.get(key) or {}
        sealed = horizon.get("sealedAudit") or {}
        walk = horizon.get("walkForwardAudit") or {}
        cost = sealed.get("costAwareLongAudit") or {}
        require(horizon.get("priceStatus") == "PASS", f"T+{key} price gate is not PASS")
        require(float(sealed.get("executableMAESkill") or 0) > 0, f"T+{key} has no executable MAE skill")
        require(float(sealed.get("magnitudeMAESkill") or 0) > 0, f"T+{key} has no magnitude skill")
        require(int(walk.get("positiveExecutableMAEFolds") or 0) >= 2, f"T+{key} lacks walk-forward price stability")
        require(int(walk.get("positiveMagnitudeFolds") or 0) >= 2, f"T+{key} lacks walk-forward magnitude stability")
        require(not cost.get("selectionFitOnHoldout"), f"T+{key} after-cost selection used holdout")
        horizon_metrics[key] = {
            "executableMAESkill": sealed.get("executableMAESkill"),
            "magnitudeMAESkill": sealed.get("magnitudeMAESkill"),
            "directionalAccuracy": sealed.get("directionalAccuracy"),
            "directionStatus": horizon.get("directionStatus"),
            "pointDirectionStatus": horizon.get("pointDirectionStatus"),
            "afterCostStatus": cost.get("status"),
            "meanNetRealizedReturn": cost.get("meanNetRealizedReturn"),
            "positiveChronologicalFolds": cost.get("positiveChronologicalFolds"),
        }

    report = {
        "version": "VMEWS-RELEASE-AUDIT-20.1.0",
        "asOf": as_of,
        "status": "PASS" if not blockers else "FAIL",
        "scope": {
            "symbols": len(symbols),
            "forecasts": quote_count,
            "flowRows": flow_row_count,
            "headlines": headline_count,
            "headlineSources": dict(sorted(by_source.items())),
        },
        "price": {
            "marketSources": dict(sorted(market_sources.items())),
            "staleSymbols": len(stale_price_symbols),
            "chartMismatches": len(chart_mismatches),
            "flatPointForecasts": neutral_points,
            "crossSource": price_cross_source,
        },
        "flow": {
            "completedSession": latest_completed,
            "requestSuccessCoverage": summary.get("refreshSuccessCoverage"),
            "foreignLatest": max(source_latest["foreign"], default=None),
            "proprietaryLatest": max(source_latest["proprietary"], default=None),
            "foreignCurrentSymbols": summary.get("foreignFreshSymbols"),
            "proprietaryCurrentSymbols": summary.get("proprietaryFreshSymbols"),
            "staleDecisionPriorViolations": len(stale_flow_prior_violations),
        },
        "news": {
            "issuerMismatches": len(issuer_mismatches),
            "weakExplicitIdentity": len(weak_identity),
        },
        "ai": {
            "publicSecretsFound": len(leaked),
            "serverProviderChain": ["Gemini", "OpenAI", "Groq", "xAI", "OpenRouter"],
        },
        "horizons": horizon_metrics,
        "blockers": blockers,
        "warnings": warnings,
        "limitations": [
            "Central forecasts estimate conditional expected return; expected absolute move and bear/bull scenarios are separate unsigned quantities.",
            "A direction probability is displayed only for horizons whose sealed Brier-skill gate passes.",
            "After-cost evidence is a fixed long-only diagnostic, not a portfolio backtest; REVIEW horizons remain watch-only.",
            "Decision-time fund, flow, accounting, event and community inputs are context scenarios only; they do not alter the sealed central forecast until independently backtested.",
            "Missing institutional-flow rows remain unavailable; genuine stale observations stay visible but cannot drive the current context scenario.",
            "AI provider failover improves availability but cannot guarantee an external provider quota or the truth of an unverified source.",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA / "release-audit-v20.json")
    options = parser.parse_args()
    report = run_audit()
    options.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"releaseAudit": {
        "status": report["status"],
        **report["scope"],
        "blockers": len(report["blockers"]),
        "warnings": len(report["warnings"]),
    }}, ensure_ascii=False), flush=True)
    if report["status"] != "PASS":
        for blocker in report["blockers"]:
            print(f"BLOCKER: {blocker}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
