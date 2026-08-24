"""Decision-time institutional, fund and financial context for VMEWS V17.

The historical forecasting model is fitted only on point-in-time rows.  Fresh
disclosures collected after the latest exchange close may nevertheless be known
before the next session opens.  This module applies those observations as a
separately labelled, volatility-bounded decision-time prior; it never inserts a
new disclosure into an old training row or claims an unavailable fund backtest.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
FUND_PATH = DATA / "fund-holdings-history-v16.json"
FINANCIAL_PATH = DATA / "current-context-v12.json"
OVERLAY_FACTORS = ("FUND", "FLOW", "FUNDAMENTAL", "EVENT", "RUMOR")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=VN_TZ) if parsed.tzinfo is None else parsed.astimezone(VN_TZ)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _business_days_between(previous: str | None, current: str) -> int:
    start = _date(previous)
    end = _date(current)
    if start is None or end is None or start >= end:
        return 0 if start is not None else 99
    return sum(
        (start + timedelta(days=offset)).weekday() < 5
        for offset in range(1, (end - start).days + 1)
    )


def _percentile(value: float, values: list[float]) -> float:
    if not values:
        return 0.5
    below = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return float((below + 0.5 * equal) / len(values))


def decision_news_contexts(
    events: Any,
    market_as_of: str,
    decision_at: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Expose verified after-close headlines known before the next decision."""
    decision = _timestamp(decision_at)
    market_day = _date(market_as_of)
    if decision is None or market_day is None:
        return {}, {"status": "UNAVAILABLE", "symbols": 0, "articles": 0}
    next_session = market_day + timedelta(days=1)
    while next_session.weekday() >= 5:
        next_session += timedelta(days=1)

    records = events if isinstance(events, list) else events.to_dict("records")
    grouped: dict[str, list[dict[str, Any]]] = {}
    rejected_future = 0
    for row in records:
        if not isinstance(row, dict):
            continue
        published = _timestamp(row.get("publishedAt"))
        available = _date(row.get("date"))
        symbol = str(row.get("symbol") or "").upper()
        if not symbol or published is None or available is None:
            continue
        if published > decision:
            rejected_future += 1
            continue
        if not market_day < available <= next_session:
            continue
        grouped.setdefault(symbol, []).append(row)

    output: dict[str, dict[str, Any]] = {}
    for symbol, rows in grouped.items():
        weighted_sum = 0.0
        weights = 0.0
        ordered = sorted(rows, key=lambda item: str(item.get("publishedAt") or ""), reverse=True)
        for row in ordered:
            importance = .25 + .75 * max(0.0, min(1.0, _number(row.get("materiality"), .35)))
            trust = .30 + .70 * max(0.0, min(1.0, _number(row.get("credibility"), .60)))
            novelty = .40 + .60 * max(0.0, min(1.0, _number(row.get("novelty"), 1.0)))
            weight = importance * trust * novelty
            weighted_sum += max(-1.0, min(1.0, _number(row.get("sentiment")))) * weight
            weights += weight
        weighted_sentiment = weighted_sum / weights if weights else 0.0
        signal_score = math.tanh(weighted_sentiment * min(2.0, 1.0 + .12 * len(ordered)))
        confidence = float(np.clip((.36 + .09 * min(len(ordered), 5)) * min(1.0, weights), .15, .82))
        output[symbol] = {
            "available": True,
            "effectiveSession": next_session.isoformat(),
            "decisionAt": decision.isoformat(timespec="seconds"),
            "count": len(ordered),
            "positive": sum(_number(row.get("sentiment")) > .05 for row in ordered),
            "negative": sum(_number(row.get("sentiment")) < -.05 for row in ordered),
            "weightedSentiment": weighted_sentiment,
            "signalScore": float(signal_score),
            "confidence": confidence,
            "inferenceEligible": True,
            "scenarioEligible": abs(signal_score) > 1e-12,
            "usedByForecast": False,
            "items": [
                {
                    "title": str(row.get("title") or ""),
                    "link": str(row.get("link") or ""),
                    "publishedAt": str(row.get("publishedAt") or ""),
                    "availableDate": str(_date(row.get("date"))),
                    "publisher": str(row.get("publisher") or ""),
                    "event": str(row.get("eventType") or ""),
                    "label": str(row.get("label") or "NEU"),
                    "sentimentScore": _number(row.get("sentiment")),
                    "materiality": _number(row.get("materiality")),
                    "sourceCredibility": _number(row.get("credibility")),
                    "sourceClass": str(row.get("sourceType") or ""),
                    "decisionTimeEligible": True,
                }
                for row in ordered[:12]
            ],
        }
    return output, {
        "status": "CONTEXT_SCENARIO_ONLY" if output else "UNAVAILABLE",
        "symbols": len(output),
        "articles": sum(item["count"] for item in output.values()),
        "nextSession": next_session.isoformat(),
        "decisionAt": decision.isoformat(timespec="seconds"),
        "futurePublicationsRejected": rejected_future,
        "historicalBackfillRows": 0,
    }


def typed_flow_summary(
    rows: list[dict[str, Any]],
    kind: str,
    market_as_of: str,
) -> dict[str, Any]:
    """Expose real archived flows while preserving source units and staleness."""
    prefix = "foreign" if kind == "foreign" else "prop"
    net_key, buy_key, sell_key = (
        f"{prefix}NetValue",
        f"{prefix}BuyValue",
        f"{prefix}SellValue",
    )
    observations = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("date") or "")[:10] <= market_as_of
        # An empty provider envelope or an all-zero placeholder is missing
        # evidence, not a real institutional observation.
        and any(abs(_number(row.get(key))) > 1e-12 for key in (net_key, buy_key, sell_key))
    ]
    observations.sort(key=lambda row: str(row.get("date") or ""))
    if not observations:
        return {
            "available": False,
            "latestDate": None,
            "ageSessions": 99,
            "stale": True,
            "unit": "VND",
        }

    scale = 1.0 if prefix == "foreign" else 1_000_000_000.0
    latest = observations[-1]
    latest_date = str(latest.get("date") or "")[:10]
    age = _business_days_between(latest_date, market_as_of)
    recent5 = observations[-5:]
    recent20 = observations[-20:]
    return {
        "available": True,
        "latestDate": latest_date,
        "ageSessions": age,
        "stale": age > 3,
        "net1": _number(latest.get(net_key)) * scale,
        "buy1": _number(latest.get(buy_key)) * scale,
        "sell1": _number(latest.get(sell_key)) * scale,
        "net5": sum(_number(row.get(net_key)) for row in recent5) * scale,
        "net20": sum(_number(row.get(net_key)) for row in recent20) * scale,
        "gross5": sum(
            abs(_number(row.get(buy_key))) + abs(_number(row.get(sell_key)))
            for row in recent5
        ) * scale,
        "observations": len(observations),
        "unit": "VND",
        "sourceUnit": "VND" if prefix == "foreign" else "billion_VND",
        "sourceScaleToVND": scale,
    }


def _valid_fund_snapshots(path: Path, decision: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    valid: list[dict[str, Any]] = []
    for snapshot in history.get("snapshots", []):
        if not isinstance(snapshot, dict) or snapshot.get("weightUnit") != "FRACTION_OF_NAV":
            continue
        collected = _timestamp(snapshot.get("generatedAt"))
        available = _date(snapshot.get("asOf"))
        if available is None or available > decision.date():
            continue
        # Old synthetic fixtures may contain only an availability date; real
        # snapshots include a collection timestamp and must pass that cutoff.
        if collected is not None and collected > decision:
            continue
        valid.append(snapshot)
    return sorted(valid, key=lambda item: (str(item.get("asOf")), str(item.get("generatedAt"))))


def fund_decision_contexts(
    universe: set[str],
    market_as_of: str,
    decision_at: str,
    *,
    path: Path = FUND_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Score disclosed fund ownership available at the actual decision time."""
    decision = _timestamp(decision_at)
    if decision is None:
        raise ValueError("decision_at must contain a valid decision timestamp")
    snapshots = _valid_fund_snapshots(path, decision)
    if not snapshots:
        return {}, {
            "status": "UNAVAILABLE",
            "snapshotCount": 0,
            "inferenceEligible": False,
            "decisionAt": decision.isoformat(timespec="seconds"),
        }

    latest = snapshots[-1]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in latest.get("holdings", []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        weight = _number(row.get("weight"), -1.0)
        report = _date(row.get("reportDate"))
        if symbol not in universe or not 0 <= weight <= 1:
            continue
        if report is not None and report > decision.date():
            continue
        grouped.setdefault(symbol, []).append(row)

    counts = [float(len(rows)) for rows in grouped.values()]
    average_weights = [
        float(np.mean([_number(row.get("weight")) for row in rows]))
        for rows in grouped.values()
    ]
    contexts: dict[str, dict[str, Any]] = {}
    previous_by_symbol: dict[str, float] = {}
    if len(snapshots) > 1:
        for row in snapshots[-2].get("holdings", []):
            if isinstance(row, dict):
                symbol = str(row.get("symbol") or "").upper()
                previous_by_symbol[symbol] = previous_by_symbol.get(symbol, 0.0) + _number(row.get("weight"))

    for symbol, holdings in grouped.items():
        weights = np.asarray([_number(item.get("weight")) for item in holdings], dtype=float)
        total_weight = float(weights.sum())
        average_weight = float(weights.mean()) if len(weights) else 0.0
        nav = np.asarray([_number(item.get("navMomentum20")) for item in holdings], dtype=float)
        nav_volatility = np.asarray([_number(item.get("navVolatility20")) for item in holdings], dtype=float)
        weighted_nav = float(np.average(nav, weights=weights)) if total_weight > 0 else 0.0
        weighted_nav_vol = float(np.average(nav_volatility, weights=weights)) if total_weight > 0 else 0.0
        report_dates = sorted(
            report.isoformat()
            for item in holdings
            if (report := _date(item.get("reportDate"))) is not None
        )
        newest_report = report_dates[-1] if report_dates else None
        report_age = (decision.date() - _date(newest_report)).days if newest_report else 60
        breadth = 2.0 * _percentile(float(len(holdings)), counts) - 1.0
        allocation = 2.0 * _percentile(average_weight, average_weights) - 1.0
        nav_scale = max(0.028, weighted_nav_vol * math.sqrt(20.0) * 1.35)
        nav_signal = math.tanh(weighted_nav / nav_scale)
        weight_change = total_weight - previous_by_symbol.get(symbol, total_weight)
        rotation = math.tanh(weight_change / max(0.035, total_weight * 0.12)) if len(snapshots) > 1 else 0.0
        score = float(np.clip(.41 * nav_signal + .28 * breadth + .18 * allocation + .13 * rotation, -1.0, 1.0))
        breadth_confidence = min(1.0, math.log1p(len(holdings)) / math.log1p(max(counts, default=1.0)))
        history_confidence = min(1.0, .56 + .08 * min(len(snapshots), 4))
        freshness = max(.32, min(1.0, math.exp(-max(0, report_age - 7) / 75.0)))
        confidence = float(np.clip((.38 + .62 * breadth_confidence) * history_confidence * freshness, .12, .96))
        sorted_holdings = sorted(holdings, key=lambda item: _number(item.get("weight")), reverse=True)

        contexts[symbol] = {
            "available": True,
            "asOf": str(latest.get("asOf")),
            "collectedAt": str(latest.get("generatedAt") or ""),
            "forecastAsOf": market_as_of,
            "decisionAt": decision.isoformat(timespec="seconds"),
            "fundCount": len(holdings),
            "reportedWeight": total_weight,
            "averageReportedWeight": average_weight,
            "largestReportedWeight": float(weights.max(initial=0.0)),
            "reportedWeightChange": float(weight_change),
            "weightedNavMomentum20": weighted_nav,
            "weightedNavVolatility20": weighted_nav_vol,
            "latestReportDate": newest_report,
            "reportAgeDays": report_age,
            "snapshotAgeDays": max(0, (decision.date() - _date(latest.get("asOf"))).days),
            "historyDepth": len(snapshots),
            "availableForForecast": True,
            "collectedAfterForecast": str(latest.get("asOf")) > market_as_of,
            "modelEligible": len(snapshots) >= 4,
            "fitEligible": len(snapshots) >= 4,
            "inferenceEligible": True,
            "scenarioEligible": True,
            "usedByForecast": False,
            "signalScore": score,
            "confidence": confidence,
            "signalComponents": {
                "fundBreadth": breadth,
                "averageAllocation": allocation,
                "navMomentum": nav_signal,
                "allocationChange": rotation,
            },
            "holdings": [
                {
                    "fundId": item.get("fundId"),
                    "fundCode": str(item.get("fundCode") or ""),
                    "fundName": str(item.get("fundName") or item.get("fundCode") or ""),
                    "weight": _number(item.get("weight")),
                    "reportDate": item.get("reportDate"),
                    "navMomentum20": _number(item.get("navMomentum20")),
                }
                for item in sorted_holdings
            ],
            "source": "FMARKET",
            "policy": "DECISION_TIMESTAMP_CONTEXT_SCENARIO; NO_HISTORICAL_BACKFILL; NOT_APPLIED_TO_CENTRAL_FORECAST",
        }

    return contexts, {
        "status": "CONTEXT_SCENARIO_ONLY" if contexts else "UNAVAILABLE",
        "snapshotCount": len(snapshots),
        "asOf": latest.get("asOf"),
        "collectedAt": latest.get("generatedAt"),
        "funds": latest.get("fundsWithMappedHoldings"),
        "holdingRows": latest.get("holdingRows"),
        "symbols": len(contexts),
        "inferenceEligible": bool(contexts),
        "fitEligible": len(snapshots) >= 4,
        "decisionAt": decision.isoformat(timespec="seconds"),
        "postCloseSymbols": sum(context["collectedAfterForecast"] for context in contexts.values()),
        "historicalBackfillRows": 0,
        "livePriorOutOfSampleValidated": False,
    }


def financial_decision_contexts(
    universe: set[str],
    decision_at: str,
    *,
    path: Path = FINANCIAL_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    decision = _timestamp(decision_at)
    if decision is None or not path.exists():
        return {}, {"status": "UNAVAILABLE", "symbols": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}, {"status": "UNAVAILABLE", "symbols": 0}
    observed = _timestamp(payload.get("generatedAt"))
    if observed is None or observed > decision:
        return {}, {"status": "UNAVAILABLE", "symbols": 0, "futureSnapshotRejected": True}

    output: dict[str, dict[str, Any]] = {}
    for symbol, row in (payload.get("symbols") or {}).items():
        symbol = str(symbol).upper()
        source = (row or {}).get("fundamental") or {}
        if symbol not in universe or source.get("status") != "PASS":
            continue
        ratios = source.get("ratios") or {}
        profit = _number(source.get("profitQoQ"))
        revenue = _number(source.get("revenueQoQ"))
        roe_raw = _number((ratios.get("roe") or {}).get("value"))
        roa_raw = _number((ratios.get("roa") or {}).get("value"))
        roe = roe_raw / 100.0 if abs(roe_raw) > 1 else roe_raw
        roa = roa_raw / 100.0 if abs(roa_raw) > 1 else roa_raw
        pe = _number((ratios.get("pe") or {}).get("value"))
        pb = _number((ratios.get("pb") or {}).get("value"))
        growth = math.tanh(profit / .24)
        sales = math.tanh(revenue / .28)
        quality = math.tanh((roe - .038) / .05) * .72 + math.tanh((roa - .015) / .035) * .28
        value = math.tanh((14.0 - pe) / 12.0) if pe > 0 else 0.0
        if pb > 0:
            value = .65 * value + .35 * math.tanh((2.3 - pb) / 2.5)
        score = float(np.clip(.42 * growth + .17 * sales + .27 * quality + .14 * value, -1.0, 1.0))
        age = max(0, (decision.date() - observed.date()).days)
        confidence = float(np.clip(.73 * math.exp(-max(0, age - 14) / 110.0), .32, .73))
        output[symbol] = {
            **source,
            "available": True,
            "observedAt": observed.isoformat(timespec="seconds"),
            "observationAgeDays": age,
            "inferenceEligible": True,
            "scenarioEligible": True,
            "usedByForecast": False,
            "signalScore": score,
            "confidence": confidence,
            "signalComponents": {
                "profitGrowth": growth,
                "revenueGrowth": sales,
                "profitability": float(quality),
                "valuation": float(value),
            },
            "policy": "OBSERVED_CURRENT_FINANCIAL_SCENARIO; NO_UNTIMESTAMPED_HISTORICAL_FEATURE; NOT_APPLIED_TO_CENTRAL_FORECAST",
        }
    return output, {
        "status": "CONTEXT_SCENARIO_ONLY" if output else "UNAVAILABLE",
        "symbols": len(output),
        "observedAt": observed.isoformat(timespec="seconds"),
        "historicalBackfillRows": 0,
        "livePriorOutOfSampleValidated": False,
    }


def flow_decision_signal(flow: dict[str, Any]) -> tuple[float, float]:
    scores: list[tuple[float, float]] = []
    for kind, weight in (("foreign", .67), ("proprietary", .33)):
        details = flow.get(kind) or {}
        # Keep a stale genuine observation visible for provenance, but never
        # turn it into a current decision prior after the three-session mask.
        if (
            not details.get("available")
            or details.get("stale")
            or int(_number(details.get("ageSessions"), 99.0)) > 3
        ):
            continue
        gross = max(abs(_number(details.get("gross5"))), abs(_number(details.get("net5"))), 1.0)
        imbalance = math.tanh(_number(details.get("net5")) / gross * 2.4)
        decay = math.exp(-max(0, int(_number(details.get("ageSessions"), 99.0))) / 4.0)
        scores.append((weight * imbalance, weight * decay))
    if not scores:
        return 0.0, 0.0
    total_weight = sum(weight for _, weight in scores)
    if total_weight <= 0:
        return 0.0, 0.0
    score = sum(score for score, _ in scores) / sum(
        .67 if kind == "foreign" else .33
        for kind in ("foreign", "proprietary")
        if (
            (flow.get(kind) or {}).get("available")
            and not (flow.get(kind) or {}).get("stale")
            and int(_number((flow.get(kind) or {}).get("ageSessions"), 99.0)) <= 3
        )
    )
    return float(np.clip(score, -1.0, 1.0)), float(np.clip(total_weight, 0.0, 1.0))


def decision_prior(
    fund: dict[str, Any] | None,
    flow: dict[str, Any] | None,
    financial: dict[str, Any] | None,
    daily_volatility: float,
    horizon: int,
    *,
    news: dict[str, Any] | None = None,
    rumor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a bounded context scenario that never changes the central quote."""
    horizon_volatility = max(.004, _number(daily_volatility, .004)) * math.sqrt(max(1, horizon))
    components = {name: 0.0 for name in OVERLAY_FACTORS}
    if fund and fund.get("inferenceEligible"):
        components["FUND"] = (
            horizon_volatility
            * (.075 + .015 * min(horizon, 5))
            * _number(fund.get("signalScore"))
            * _number(fund.get("confidence"))
        )
    if flow:
        score, confidence = flow_decision_signal(flow)
        components["FLOW"] = (
            horizon_volatility
            * (.045 + .006 * min(horizon, 5))
            * score
            * confidence
        )
    if financial and financial.get("inferenceEligible"):
        components["FUNDAMENTAL"] = (
            horizon_volatility
            * (.042 + .008 * min(horizon, 5))
            * _number(financial.get("signalScore"))
            * _number(financial.get("confidence"))
        )
    if news and news.get("inferenceEligible"):
        components["EVENT"] = (
            horizon_volatility
            * (.062 + .009 * min(horizon, 5))
            * _number(news.get("signalScore"))
            * _number(news.get("confidence"))
        )
    # Only newly observed, independently corroborated material claims can
    # affect the live decision.  Claims already present before the last close
    # are part of fitted NEWS_COLUMNS and must not be counted a second time.
    if rumor and rumor.get("inferenceEligible"):
        components["RUMOR"] = (
            horizon_volatility
            * (.025 + .005 * min(horizon, 5))
            * _number(rumor.get("signalScore"))
            * _number(rumor.get("confidence"))
        )
    maximum = min(.012, horizon_volatility * .22)
    raw = sum(components.values())
    if abs(raw) > maximum and abs(raw) > 0:
        scale = maximum / abs(raw)
        components = {name: value * scale for name, value in components.items()}
    total = float(sum(components.values()))
    return {
        "status": "ACTIVE" if any(abs(value) > 1e-12 for value in components.values()) else "UNAVAILABLE",
        "components": components,
        "totalReturn": total,
        "maximumAbsoluteReturn": float(maximum),
        "horizonVolatility": float(horizon_volatility),
        "independentlyBacktested": False,
        "centralForecastEligible": False,
        "policy": "DECISION_TIME_CONTEXT_SCENARIO; VOLATILITY_BOUNDED; NO_HISTORICAL_BACKFILL; NOT_APPLIED_TO_CENTRAL_FORECAST",
    }
