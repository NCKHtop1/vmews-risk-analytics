"""Secure point-in-time adapters for VMEWS Forecast V16.

The browser dashboard never calls provider APIs.  Collection happens in the
scheduled Python job and only small, timestamped research artifacts are served
through the GitHub CDN.  No provider credential is stored in this repository.

The Fmarket adapter is derived from the user-supplied ``fund_data.py`` flow:

* ``/res/products/filter`` discovers active funds;
* ``/res/products/{id}`` supplies the reported holdings;
* ``/res/product/get-nav-history`` supplies NAV history.

Each observation is available to the model no earlier than the date on which
our collector actually observed it.  This conservative rule prevents a newly
downloaded holdings report from being copied backwards into historical rows.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
FMARKET_BASE = "https://api.fmarket.vn"
FUND_HISTORY_PATH = DATA / "fund-holdings-history-v16.json"

FUND_FEATURE_COLUMNS = [
    "fund_holder_count",
    "fund_weight_sum",
    "fund_weight_max",
    "fund_weight_change",
    "fund_nav_momentum20",
    "fund_nav_volatility20",
    "fund_snapshot_age",
    "fund_available",
    "fund_history_depth",
]


class SourceError(RuntimeError):
    """Raised when a source cannot produce a structurally valid snapshot."""


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        output = float(value)
        return output if math.isfinite(output) else default
    except (TypeError, ValueError):
        return default


def _first(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _iso_day(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(VN_TZ).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text) else None


def _normalise_weight(value: Any, *, percentage_points: bool = False) -> float | None:
    output = _number(value)
    if output is None or output < 0:
        return None
    if percentage_points or output > 1.0:
        output /= 100.0
    return float(np.clip(output, 0.0, 1.0))


def _json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    bearer_token: str | None = None,
    timeout: int = 25,
    attempts: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "VMEWS-Forecast-V16/1.0 (+point-in-time research)",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise SourceError(f"non-object response from {url}")
            return result
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, SourceError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise SourceError(f"request failed after {attempts} attempts: {url}: {last_error}")


@dataclass(frozen=True)
class FundHolding:
    fund_id: int
    fund_code: str
    fund_name: str
    symbol: str
    weight: float
    report_date: str | None
    nav_momentum20: float | None
    nav_volatility20: float | None

    def as_dict(self, available_date: str) -> dict[str, Any]:
        return {
            "fundId": self.fund_id,
            "fundCode": self.fund_code,
            "fundName": self.fund_name,
            "symbol": self.symbol,
            "weight": self.weight,
            "reportDate": self.report_date,
            "availableDate": available_date,
            "navMomentum20": self.nav_momentum20,
            "navVolatility20": self.nav_volatility20,
        }


def _fund_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise SourceError("Fmarket fund list has no data.rows array")
    return [row for row in rows if isinstance(row, dict)]


def _is_equity_relevant(row: dict[str, Any]) -> bool:
    asset = row.get("dataFundAssetType") or {}
    name = str(asset.get("name") if isinstance(asset, dict) else asset).casefold()
    return any(token in name for token in ("cổ phiếu", "co phieu", "equity", "cân bằng", "can bang", "balanced"))


def _nav_statistics(product_id: int, token: str | None, as_of: str) -> tuple[float | None, float | None]:
    start = (date.fromisoformat(as_of) - timedelta(days=90)).strftime("%Y%m%d")
    end = date.fromisoformat(as_of).strftime("%Y%m%d")
    response = _json_request(
        f"{FMARKET_BASE}/res/product/get-nav-history",
        payload={"isAllData": 0, "productId": product_id, "fromDate": start, "toDate": end},
        bearer_token=token,
        timeout=12,
        attempts=2,
    )
    rows = response.get("data") or []
    values: list[tuple[str, float]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        nav = _number(_first(row, ("nav", "value", "navValue", "price")))
        day = _iso_day(_first(row, ("navDate", "date", "createdAt", "updateAt")))
        if nav is not None and nav > 0 and day:
            values.append((day, nav))
    values = sorted(dict(values).items())
    if len(values) < 2:
        return None, None
    series = pd.Series([value for _, value in values], dtype=float)
    anchor = series.iloc[-21] if len(series) >= 21 else series.iloc[0]
    momentum = float(series.iloc[-1] / anchor - 1.0)
    volatility = float(np.log(series).diff().dropna().tail(20).std(ddof=0)) if len(series) >= 3 else None
    return momentum, volatility


def collect_fmarket_snapshot(
    universe: set[str],
    *,
    as_of: str | None = None,
    bearer_token: str | None = None,
    max_funds: int | None = None,
) -> dict[str, Any]:
    """Collect a conservative current fund-holdings snapshot from Fmarket."""
    as_of = as_of or datetime.now(VN_TZ).date().isoformat()
    bearer_token = bearer_token or os.environ.get("FMARKET_BEARER_TOKEN") or None
    listing = _json_request(
        f"{FMARKET_BASE}/res/products/filter",
        payload={
            "types": ["NEW_FUND", "TRADING_FUND"],
            "issuerIds": [],
            "sortOrder": "DESC",
            "sortField": "navTo12Months",
            "page": 1,
            "pageSize": 999999,
            "isIpo": False,
            "fundAssetTypes": [],
            "bondRemainPeriods": [],
            "searchField": "",
            "isBuyByReward": False,
            "thirdAppIds": [],
        },
        bearer_token=bearer_token,
    )
    funds = [row for row in _fund_rows(listing) if _is_equity_relevant(row)]
    if max_funds is not None:
        funds = funds[:max_funds]
    def collect_one(row: dict[str, Any]) -> tuple[list[FundHolding], list[dict[str, str]]]:
        local_holdings: list[FundHolding] = []
        local_failures: list[dict[str, str]] = []
        product_id = int(_number(row.get("id"), 0) or 0)
        if product_id <= 0:
            return local_holdings, local_failures
        fund_code = str(_first(row, ("tradeCode", "code", "shortName")) or product_id)
        fund_name = str(_first(row, ("name", "shortName")) or fund_code)
        try:
            detail_response = _json_request(
                f"{FMARKET_BASE}/res/products/{product_id}", bearer_token=bearer_token
            )
            detail = detail_response.get("data") or {}
            if not isinstance(detail, dict):
                raise SourceError("fund detail has no data object")
            try:
                momentum, nav_volatility = _nav_statistics(product_id, bearer_token, as_of)
            except SourceError as exc:
                momentum, nav_volatility = None, None
                local_failures.append({"fund": fund_code, "error": f"NAV unavailable: {str(exc)[:180]}"})
            report = detail.get("fundReport") or {}
            default_report_date = _iso_day(
                _first(report, ("reportTime", "updateAt")) if isinstance(report, dict) else None
            )
            candidates = list(detail.get("productTopHoldingList") or [])
            candidates += list(detail.get("productTopHoldingBondList") or [])
            accepted = 0
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                symbol = str(
                    _first(item, ("stockCode", "ticker", "symbol", "assetCode", "code", "tradeCode")) or ""
                ).upper().strip()
                if symbol not in universe:
                    continue
                percent_weight = _first(
                    item,
                    (
                        "netAssetPercent",
                        "assetPercent",
                        "holdingPercent",
                        "percentage",
                        "percent",
                    ),
                )
                weight = (
                    _normalise_weight(percent_weight, percentage_points=True)
                    if percent_weight is not None
                    else _normalise_weight(_first(item, ("weight", "rate")))
                )
                if weight is None:
                    continue
                report_date = _iso_day(_first(item, ("updateAt", "reportTime", "date"))) or default_report_date
                local_holdings.append(
                    FundHolding(
                        fund_id=product_id,
                        fund_code=fund_code,
                        fund_name=fund_name,
                        symbol=symbol,
                        weight=weight,
                        report_date=report_date,
                        nav_momentum20=momentum,
                        nav_volatility20=nav_volatility,
                    )
                )
                accepted += 1
        except SourceError as exc:
            local_failures.append({"fund": fund_code, "error": str(exc)[:220]})
        return local_holdings, local_failures

    holdings: list[FundHolding] = []
    failures: list[dict[str, str]] = []
    successful_funds = 0
    workers = min(max(1, int(os.environ.get("V16_FUND_WORKERS", "6"))), max(1, len(funds)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(collect_one, row) for row in funds]
        for future in as_completed(futures):
            local_holdings, local_failures = future.result()
            holdings.extend(local_holdings)
            failures.extend(local_failures)
            if local_holdings:
                successful_funds += 1

    if not holdings:
        raise SourceError("Fmarket returned no correctly mapped HOSE holdings")
    return {
        "version": "VMEWS-FUND-HOLDINGS-16.0.0",
        "generatedAt": datetime.now(VN_TZ).isoformat(timespec="seconds"),
        "asOf": as_of,
        "source": "FMARKET",
        "sourceRole": "DISCLOSED_FUND_CONTEXT",
        "weightUnit": "FRACTION_OF_NAV",
        "pointInTimePolicy": "AVAILABLE_FROM_FIRST_VMEWS_COLLECTION_DATE",
        "fundsRequested": len(funds),
        "fundsWithMappedHoldings": successful_funds,
        "holdingRows": len(holdings),
        "symbols": len({row.symbol for row in holdings}),
        "failures": failures,
        "holdings": [row.as_dict(as_of) for row in holdings],
    }


def append_fund_snapshot(snapshot: dict[str, Any], path: Path = FUND_HISTORY_PATH) -> dict[str, Any]:
    history: dict[str, Any] = {
        "version": "VMEWS-FUND-HOLDINGS-HISTORY-16.0.0",
        "pointInTimePolicy": "SNAPSHOT_USABLE_NO_EARLIER_THAN_ITS_COLLECTION_DATE",
        "snapshots": [],
    }
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            history.update(loaded)
    snapshots = {
        str(item.get("asOf")): item
        for item in history.get("snapshots", [])
        if isinstance(item, dict) and item.get("asOf")
    }
    snapshots[str(snapshot["asOf"])] = snapshot
    history["generatedAt"] = datetime.now(VN_TZ).isoformat(timespec="seconds")
    history["snapshots"] = [snapshots[key] for key in sorted(snapshots)]
    history["snapshotCount"] = len(history["snapshots"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return history


def fund_feature_panel(
    panel: pd.DataFrame,
    *,
    path: Path = FUND_HISTORY_PATH,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """As-of join fund snapshots to a symbol/date feature panel."""
    output = pd.DataFrame(index=panel.index, columns=FUND_FEATURE_COLUMNS, dtype=float)
    output.loc[:, :] = 0.0
    if not path.exists():
        return output, {"status": "UNAVAILABLE", "snapshotCount": 0, "modelEligible": False}
    history = json.loads(path.read_text(encoding="utf-8"))
    snapshots = [
        item for item in history.get("snapshots", [])
        if isinstance(item, dict) and item.get("weightUnit") == "FRACTION_OF_NAV"
    ]
    records: list[dict[str, Any]] = []
    for depth, snapshot in enumerate(sorted(snapshots, key=lambda item: str(item.get("asOf"))), start=1):
        available = pd.to_datetime(snapshot.get("asOf"), errors="coerce")
        if pd.isna(available):
            continue
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for holding in snapshot.get("holdings", []):
            if isinstance(holding, dict) and holding.get("symbol"):
                by_symbol.setdefault(str(holding["symbol"]).upper(), []).append(holding)
        for symbol, rows in by_symbol.items():
            weights = np.asarray([_number(row.get("weight"), 0.0) or 0.0 for row in rows], dtype=float)
            nav_momentum = np.asarray([_number(row.get("navMomentum20"), 0.0) or 0.0 for row in rows], dtype=float)
            nav_volatility = np.asarray([_number(row.get("navVolatility20"), 0.0) or 0.0 for row in rows], dtype=float)
            total = float(weights.sum())
            records.append(
                {
                    "symbol": symbol,
                    "availableDate": available,
                    "fund_holder_count": float(len(rows)),
                    "fund_weight_sum": total,
                    "fund_weight_max": float(weights.max(initial=0.0)),
                    "fund_nav_momentum20": float(np.average(nav_momentum, weights=weights)) if total > 0 else 0.0,
                    "fund_nav_volatility20": float(np.average(nav_volatility, weights=weights)) if total > 0 else 0.0,
                    "fund_history_depth": float(depth),
                }
            )
    features = pd.DataFrame(records)
    if features.empty:
        return output, {"status": "EMPTY", "snapshotCount": len(snapshots), "modelEligible": False}
    features.sort_values(["symbol", "availableDate"], inplace=True)
    features["fund_weight_change"] = features.groupby("symbol", observed=True)["fund_weight_sum"].diff().fillna(0.0)
    left = panel[["symbol", "date"]].copy().reset_index(names="_row")
    left.sort_values(["date", "symbol"], inplace=True)
    right = features.sort_values(["availableDate", "symbol"])
    joined = pd.merge_asof(
        left,
        right,
        left_on="date",
        right_on="availableDate",
        by="symbol",
        direction="backward",
        allow_exact_matches=True,
    )
    joined["fund_snapshot_age"] = (joined["date"] - joined["availableDate"]).dt.days.clip(lower=0).fillna(999.0)
    joined["fund_available"] = joined["availableDate"].notna().astype(float)
    joined.set_index("_row", inplace=True)
    for column in FUND_FEATURE_COLUMNS:
        output[column] = pd.to_numeric(joined.reindex(output.index)[column], errors="coerce").fillna(0.0)
    model_eligible = len(snapshots) >= 4 and features["availableDate"].nunique() >= 4
    return output, {
        "status": "PASS" if model_eligible else "CONTEXT_ONLY",
        "snapshotCount": len(snapshots),
        "dates": int(features["availableDate"].nunique()),
        "symbols": int(features["symbol"].nunique()),
        "modelEligible": model_eligible,
        "rule": "At least four independently collected point-in-time snapshots are required before fund holdings may affect a fitted forecast.",
    }


def latest_fund_context(path: Path = FUND_HISTORY_PATH) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return the latest disclosed holdings for UI context, without backfilling."""
    if not path.exists():
        return {}, {"status": "UNAVAILABLE", "snapshotCount": 0}
    history = json.loads(path.read_text(encoding="utf-8"))
    snapshots = [
        item for item in history.get("snapshots", [])
        if isinstance(item, dict) and item.get("weightUnit") == "FRACTION_OF_NAV"
    ]
    if not snapshots:
        return {}, {"status": "EMPTY", "snapshotCount": 0}
    latest = max(snapshots, key=lambda item: str(item.get("asOf")))
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for holding in latest.get("holdings", []):
        if isinstance(holding, dict) and holding.get("symbol"):
            by_symbol.setdefault(str(holding["symbol"]).upper(), []).append(holding)
    contexts: dict[str, dict[str, Any]] = {}
    for symbol, rows in by_symbol.items():
        weights = np.asarray([_number(item.get("weight"), 0.0) or 0.0 for item in rows], dtype=float)
        contexts[symbol] = {
            "available": True,
            "asOf": str(latest.get("asOf")),
            "fundCount": len(rows),
            "reportedWeight": float(weights.sum()),
            "averageReportedWeight": float(weights.mean()) if len(weights) else 0.0,
            "largestReportedWeight": float(weights.max(initial=0.0)),
            "weightedNavMomentum20": float(
                np.average(
                    np.asarray([_number(item.get("navMomentum20"), 0.0) or 0.0 for item in rows]),
                    weights=weights,
                )
            ) if weights.sum() > 0 else 0.0,
            "historyDepth": len(snapshots),
            "modelEligible": len(snapshots) >= 4,
            "source": "FMARKET",
        }
    return contexts, {
        "status": "PASS",
        "snapshotCount": len(snapshots),
        "asOf": latest.get("asOf"),
        "funds": latest.get("fundsWithMappedHoldings"),
        "holdingRows": latest.get("holdingRows"),
        "symbols": len(contexts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect-funds", action="store_true")
    parser.add_argument("--universe", default=str(DATA / "forecast-dashboard-v12.json"))
    parser.add_argument("--output", default=str(FUND_HISTORY_PATH))
    parser.add_argument("--max-funds", type=int)
    arguments = parser.parse_args()
    if not arguments.collect_funds:
        parser.error("choose --collect-funds")
    source = json.loads(Path(arguments.universe).read_text(encoding="utf-8"))
    universe = {str(symbol).upper() for symbol in (source.get("symbols") or {})}
    if len(universe) < 390:
        raise SourceError(f"invalid HOSE universe: {len(universe)} symbols")
    snapshot = collect_fmarket_snapshot(universe, max_funds=arguments.max_funds)
    history = append_fund_snapshot(snapshot, Path(arguments.output))
    print(
        json.dumps(
            {
                "status": "PASS",
                "asOf": snapshot["asOf"],
                "snapshots": history["snapshotCount"],
                "funds": snapshot["fundsWithMappedHoldings"],
                "holdings": snapshot["holdingRows"],
                "symbols": snapshot["symbols"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
