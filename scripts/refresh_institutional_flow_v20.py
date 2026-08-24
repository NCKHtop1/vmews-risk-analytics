"""Incrementally refresh genuine EOD foreign/proprietary transactions.

The historical archive is never replaced with an empty provider response and
observations from an unfinished/future trading session are never published.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as clock, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import backfill_flow_v11 as provider
from backfill_flow_v12 import audit_symbol, parse_payload

ROOT = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()
DATA = ROOT / "data"
VN_TZ = timezone(timedelta(hours=7))
FLOW_READY_AFTER = clock(
    int(os.environ.get("V20_FLOW_READY_HOUR", "17")),
    int(os.environ.get("V20_FLOW_READY_MINUTE", "0")),
)
FLOW_FIELDS = {
    "foreign": ("foreignBuyValue", "foreignSellValue", "foreignNetValue"),
    "proprietary": ("propBuyValue", "propSellValue", "propNetValue"),
}


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    """Write a generated JSON artifact atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def completed_session(now: datetime | None = None) -> date:
    local = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    session = local.date()
    # Institutional EOD files are not assumed complete at the closing bell.
    if local.timetz().replace(tzinfo=None) < FLOW_READY_AFTER:
        session -= timedelta(days=1)
    while session.weekday() >= 5:
        session -= timedelta(days=1)
    return session


def _genuine(row: dict[str, Any], kind: str) -> bool:
    return any(abs(float(row.get(field) or 0)) > 1e-9 for field in FLOW_FIELDS[kind])


def fetch_window(symbol: str, kind: str, start: date, end: date) -> list[dict[str, Any]]:
    endpoint = "GDKhoiNgoai.ashx" if kind == "foreign" else "GDTuDoanh.ashx"
    parsed_kind = "foreign" if kind == "foreign" else "prop"
    collected: list[dict[str, Any]] = []
    for page in range(1, 4):
        query = urlencode({
            "Symbol": symbol,
            "StartDate": start.strftime("%m/%d/%Y"),
            "EndDate": end.strftime("%m/%d/%Y"),
            "PageIndex": page,
            "PageSize": 100,
        })
        error: Exception | None = None
        payload: dict[str, Any] | None = None
        for attempt in range(2):
            try:
                # The production runner can spend several seconds establishing
                # an approved outbound route.  A nine-second socket deadline
                # misclassified that setup delay as an empty market response.
                raw, _ = provider.get(
                    provider.BASE + endpoint + "?" + query,
                    timeout=float(os.environ.get("V20_FLOW_TIMEOUT", "55")),
                )
                payload = json.loads(raw.decode("utf-8", errors="replace"))
                if not isinstance(payload, dict):
                    raise ValueError("flow provider returned a non-object response")
                break
            except (OSError, ValueError, TimeoutError) as failure:
                error = failure
                if attempt == 0:
                    time.sleep(.15)
        if payload is None:
            raise RuntimeError(f"{symbol}/{kind}: {type(error).__name__}: {error}")
        rows, metadata = parse_payload(payload, parsed_kind)
        collected.extend(row for row in rows if _genuine(row, kind))
        pages = int(metadata.get("TotalPage") or metadata.get("totalPage") or 0)
        if not rows or (pages and page >= pages) or (not pages and len(rows) < 100):
            break
    # CafeF's proprietary JSON route currently returns a successful envelope
    # without transaction rows.  Its independently auditable XLSX export still
    # contains genuine up-to-date observations in the original billion-VND unit.
    if kind == "proprietary" and not collected:
        exported: list[dict[str, Any]] | None = None
        export_error: Exception | None = None
        for attempt in range(2):
            try:
                exported = provider.export_rows(symbol, "prop")
                break
            except (OSError, ValueError, TimeoutError) as failure:
                export_error = failure
                if attempt == 0:
                    time.sleep(.2)
        if exported is None:
            raise RuntimeError(
                f"{symbol}/proprietary export: {type(export_error).__name__}: {export_error}"
            )
        collected = [
            {key: row[key] for key in ("date", *FLOW_FIELDS[kind]) if key in row}
            for row in exported
            if _genuine(row, kind)
        ]
    earliest, latest = start.isoformat(), end.isoformat()
    return sorted(
        {row["date"]: row for row in collected if earliest <= str(row.get("date")) <= latest}.values(),
        key=lambda row: row["date"],
    )


def fetch_symbol_shard(symbol: str, latest_session: date, days: int = 16) -> dict[str, Any]:
    """Fetch one symbol without allowing a failure to poison another symbol."""
    symbol = symbol.strip().upper()
    start = latest_session - timedelta(days=max(5, days))
    observations: dict[str, list[dict[str, Any]]] = {}
    failures: dict[str, str] = {}
    for kind in FLOW_FIELDS:
        try:
            observations[kind] = fetch_window(symbol, kind, start, latest_session)
        except Exception as failure:
            failures[kind] = f"{type(failure).__name__}: {failure}"[:300]
    return {
        "version": "VMEWS-FLOW-SHARD-20.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "start": start.isoformat(),
        "end": latest_session.isoformat(),
        "observations": observations,
        "failures": failures,
        "attemptedKinds": sorted(FLOW_FIELDS),
    }


def load_fetch_shards(directory: Path, expected_symbols: set[str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate isolated fetch results before a single archive merge."""
    shards: dict[str, Any] = {}
    rejected: dict[str, str] = {}
    for symbol in sorted(expected_symbols):
        path = directory / f"{symbol}.json"
        try:
            shard = json.loads(path.read_text(encoding="utf-8"))
            if str(shard.get("symbol") or "").upper() != symbol:
                raise ValueError("symbol identity mismatch")
            if set(shard.get("attemptedKinds") or []) != set(FLOW_FIELDS):
                raise ValueError("both institutional-flow kinds were not attempted")
            shards[symbol] = shard
        except (OSError, ValueError, TypeError) as failure:
            rejected[symbol] = f"{type(failure).__name__}: {failure}"[:300]
    return shards, rejected


def _published_universe(archive: dict[str, Any]) -> set[str]:
    symbols = set((archive.get("symbols") or {}))
    dashboard_path = DATA / "forecast-dashboard-v12.json"
    if dashboard_path.exists():
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        symbols.update((dashboard.get("symbols") or {}).keys())
    return {str(symbol).upper() for symbol in symbols if symbol}


def merge_observations(
    original: list[dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    latest_session: date,
) -> tuple[list[dict[str, Any]], int]:
    deadline = latest_session.isoformat()
    combined = {
        str(item["date"]): dict(item)
        for item in original
        if isinstance(item, dict) and item.get("date") and str(item["date"]) <= deadline
    }
    added = 0
    for kind, observations in incoming.items():
        allowed = set(FLOW_FIELDS[kind])
        for observation in observations:
            observed = str(observation.get("date") or "")[:10]
            if not observed or observed > deadline or not _genuine(observation, kind):
                continue
            current = combined.setdefault(observed, {"date": observed})
            update = {key: observation[key] for key in allowed if key in observation}
            if any(current.get(key) != value for key, value in update.items()):
                added += 1
                current.update(update)
    return [combined[key] for key in sorted(combined)], added


def _latest(rows: list[dict[str, Any]], kind: str) -> str | None:
    return next((str(row["date"]) for row in reversed(rows) if _genuine(row, kind)), None)


def refresh_archive(
    archive: dict[str, Any],
    latest_session: date,
    *,
    downloader: Callable[[str, str, date, date], list[dict[str, Any]]] = fetch_window,
    workers: int = 12,
    days: int = 16,
    selected_symbols: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    symbols = archive.get("symbols") or {}
    if not isinstance(symbols, dict) or not symbols:
        raise ValueError("Existing audited institutional-flow archive is required")
    start = latest_session - timedelta(days=max(5, days))
    pending: dict[str, dict[str, list[dict[str, Any]]]] = {symbol: {} for symbol in symbols}
    failures: dict[str, str] = {}
    selected = set(symbols) if selected_symbols is None else set(symbols) & {value.upper() for value in selected_symbols}
    if not selected:
        raise ValueError("No requested symbols exist in the institutional-flow archive")
    tasks = [(symbol, kind) for symbol in sorted(selected) for kind in FLOW_FIELDS]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(downloader, symbol, kind, start, latest_session): (symbol, kind) for symbol, kind in tasks}
        for index, future in enumerate(as_completed(futures), 1):
            symbol, kind = futures[future]
            try:
                pending[symbol][kind] = future.result()
            except Exception as failure:
                failures[f"{symbol}:{kind}"] = f"{type(failure).__name__}: {failure}"[:300]
            if index % 80 == 0 or index == len(tasks):
                print(json.dumps({"flowRefresh": index, "total": len(tasks), "failed": len(failures)}, ensure_ascii=False), flush=True)

    revised = dict(archive)
    revised["symbols"] = {}
    audits: dict[str, dict[str, Any]] = {}
    added = 0
    for symbol, previous in symbols.items():
        merged, changed = merge_observations(previous if isinstance(previous, list) else [], pending[symbol], latest_session)
        added += changed
        route = dict((archive.get("sourceAudit") or {}).get(symbol, {}).get("route") or {})
        route["incremental"] = {"method": "RECENT_EOD_JSON_WITH_PROPRIETARY_XLSX_FALLBACK", "start": start.isoformat(), "end": latest_session.isoformat()}
        clean, audits[symbol] = audit_symbol(merged, route)
        revised["symbols"][symbol] = clean

    foreign_dates = [value for rows in revised["symbols"].values() if (value := _latest(rows, "foreign"))]
    prop_dates = [value for rows in revised["symbols"].values() if (value := _latest(rows, "proprietary"))]
    latest_foreign = max(foreign_dates, default=None)
    latest_prop = max(prop_dates, default=None)
    target = latest_session.isoformat()
    foreign_fresh = sum(value == target for value in foreign_dates)
    prop_fresh = sum(value == target for value in prop_dates)
    # Coverage is measured against the published universe.  Dividing only by
    # names which happened to return a row would hide provider omissions.
    universe_count = len(symbols)
    foreign_fresh_coverage = foreign_fresh / max(1, universe_count)
    prop_fresh_coverage = prop_fresh / max(1, universe_count)
    prior_summary = dict(archive.get("summary") or {})
    summary = {
        **prior_summary,
        "todayVN": target,
        "refreshTargetSession": target,
        "refreshWindowStart": start.isoformat(),
        "updatedObservations": added,
        "foreignLatest": latest_foreign,
        "proprietaryLatest": latest_prop,
        "foreignFreshSymbols": foreign_fresh,
        "proprietaryFreshSymbols": prop_fresh,
        "foreignFreshCoverage": foreign_fresh_coverage,
        "proprietaryFreshCoverage": prop_fresh_coverage,
        "foreignMedianNonzeroRows": statistics.median([a["foreignNonzeroRows"] for a in audits.values() if a["foreignNonzeroRows"]]) if foreign_dates else 0,
        "propMedianNonzeroRows": statistics.median([a["propNonzeroRows"] for a in audits.values() if a["propNonzeroRows"]]) if prop_dates else 0,
        "providerRequestFailures": len(failures),
        "refreshRequestedSymbols": len(selected),
        "refreshRequestedKinds": len(tasks),
        "refreshSucceededKinds": len(tasks) - len(failures),
        "refreshSuccessCoverage": (len(tasks) - len(failures)) / max(1, len(tasks)),
        "publishedUniverseSymbols": universe_count,
        "freshnessStatus": "CURRENT" if foreign_fresh_coverage >= .85 else "PARTIAL" if latest_foreign == target else "STALE",
        "proprietaryFreshnessStatus": "CURRENT" if prop_fresh_coverage >= .85 else "PARTIAL" if latest_prop == target else "STALE_OR_UNPUBLISHED",
    }
    timestamp = datetime.now(timezone.utc).isoformat()
    revised.update({
        "generatedAt": timestamp,
        "range": {**(archive.get("range") or {}), "end": target},
        "summary": summary,
        "sourceAudit": audits,
        "failures": failures,
        "incrementalRefresh": {
            "generatedAt": timestamp,
            "targetCompletedSession": target,
            "unfinishedSessionUsed": False,
            "futureRowsUsed": 0,
            "emptyProviderResponsesOverwriteHistory": False,
            "fabricatedZeroRows": 0,
        },
    })
    audit = {
        "version": "VMEWS-FLOW-AUDIT-20.0.0",
        "generatedAt": timestamp,
        "summary": summary,
        "source": revised.get("source"),
        "availabilityPolicy": revised.get("availabilityPolicy"),
        "symbols": audits,
        "failures": failures,
        "incrementalRefresh": revised["incrementalRefresh"],
    }
    return revised, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=int(os.environ.get("V20_FLOW_WORKERS", "12")))
    parser.add_argument("--days", type=int, default=16)
    parser.add_argument("--symbols", default="ALL", help="ALL, VN30, or comma-separated archived tickers")
    parser.add_argument("--fetch-symbol", help="fetch one isolated ticker shard without merging the archive")
    parser.add_argument("--fetch-dir", type=Path, help="directory for isolated per-symbol shards")
    parser.add_argument("--merge-dir", type=Path, help="merge a complete set of isolated shards")
    options = parser.parse_args()
    path = DATA / "flow-v12.json"
    archive = json.loads(path.read_text(encoding="utf-8"))
    universe = _published_universe(archive)
    archive["symbols"] = {
        symbol: (archive.get("symbols") or {}).get(symbol, []) for symbol in sorted(universe)
    }
    if options.fetch_symbol:
        if not options.fetch_dir:
            parser.error("--fetch-symbol requires --fetch-dir")
        symbol = options.fetch_symbol.strip().upper()
        if symbol not in universe:
            parser.error(f"{symbol} is not in the published universe")
        shard = fetch_symbol_shard(symbol, completed_session(), options.days)
        _json_write(options.fetch_dir / f"{symbol}.json", shard)
        print(json.dumps({"institutionalFlowShard": {
            "symbol": symbol,
            "rows": {kind: len(rows) for kind, rows in shard["observations"].items()},
            "failures": shard["failures"],
        }}, ensure_ascii=False), flush=True)
        if shard["failures"]:
            raise SystemExit(1)
        return
    if options.symbols.strip().upper() == "ALL":
        selected = None
    elif options.symbols.strip().upper() == "VN30":
        dashboard = json.loads((DATA / "forecast-dashboard-v12.json").read_text(encoding="utf-8"))
        selected = set((dashboard.get("lists") or {}).get("vn30", {}).get("symbols") or [])
    else:
        selected = {value.strip().upper() for value in options.symbols.split(",") if value.strip()}
    rejected_shards: dict[str, str] = {}
    if options.merge_dir:
        requested = universe if selected is None else selected & universe
        shards, rejected_shards = load_fetch_shards(options.merge_dir, requested)

        def downloader(symbol: str, kind: str, start: date, end: date) -> list[dict[str, Any]]:
            if symbol in rejected_shards:
                raise RuntimeError(rejected_shards[symbol])
            shard = shards[symbol]
            if kind in (shard.get("failures") or {}):
                raise RuntimeError(shard["failures"][kind])
            return list((shard.get("observations") or {}).get(kind) or [])

        refreshed, audit = refresh_archive(
            archive, completed_session(), downloader=downloader, workers=options.workers,
            days=options.days, selected_symbols=requested,
        )
        audit["summary"]["rejectedFetchShards"] = len(rejected_shards)
        audit["fetchShardFailures"] = rejected_shards
        refreshed["summary"] = audit["summary"]
        refreshed["fetchShardFailures"] = rejected_shards
    else:
        refreshed, audit = refresh_archive(
            archive, completed_session(), workers=options.workers, days=options.days,
            selected_symbols=selected,
        )
    _json_write(path, refreshed)
    _json_write(DATA / "flow-audit-v12.json", audit)
    print(json.dumps({"institutionalFlowRefresh": audit["summary"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
