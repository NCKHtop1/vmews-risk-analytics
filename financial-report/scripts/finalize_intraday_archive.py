#!/usr/bin/env python3
"""Finalize the completed HOSE session into the append-only FinQuery 5-minute archive.

This step never fetches a provider. It resamples the already-published 1-minute
bars only after the close and appends them to each symbol's existing 5-minute
archive. A session is publishable only when the archive covers at least 90% of
the live market universe and matches the quote session date.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from refresh_market import (  # noqa:E402
    _write_intraday_5m_archive,
    intraday_archive_summary,
    read,
    source_day,
    write,
    now,
)

VN = timezone(timedelta(hours=7))


def bar_day(value: object) -> str | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(VN).date().isoformat()
    except (ValueError, TypeError):
        return None


def finalize(root: Path) -> dict:
    universe = read(root / "universe.json", {})
    symbols = [str(x).upper() for x in (universe.get("liveMarketSymbols") or []) if str(x).strip()]
    if not symbols:
        symbols = sorted(
            str(symbol).upper()
            for symbol, row in (universe.get("symbols") or {}).items()
            if (row or {}).get("liveMarketEligible")
        )
    if not symbols:
        raise RuntimeError("live market universe missing")

    quotes = read(root / "quotes.json", {})
    quote_stamp = quotes.get("latestSourceTime") or quotes.get("sourceTime")
    target_day = source_day(quote_stamp)
    if not target_day:
        raise RuntimeError("quote session date missing")

    required = max(1, math.ceil(len(symbols) * .90))
    existing = intraday_archive_summary(root, symbols)
    if (
        existing.get("archive5mLatestDay") == target_day
        and int(existing.get("archive5mLatestDayCoverage") or 0) >= required
    ):
        return {
            "session": target_day,
            "written": 0,
            "liveUniverse": len(symbols),
            "latestCoverage": int(existing.get("archive5mLatestDayCoverage") or 0),
            "required": required,
            "skipped": [],
            "alreadyFinalized": True,
        }

    written = 0
    skipped = []
    for symbol in symbols:
        minute = read(root / "intraday" / f"{symbol}.json", {})
        bars = [
            bar for bar in (minute.get("bars") or [])
            if isinstance(bar, dict) and bar_day(bar.get("time")) == target_day
        ]
        if not bars:
            skipped.append(symbol)
            continue
        _write_intraday_5m_archive(root, symbol, bars)
        written += 1

    summary = intraday_archive_summary(root, symbols)
    latest_day = summary.get("archive5mLatestDay")
    latest_coverage = int(summary.get("archive5mLatestDayCoverage") or 0)
    if latest_day != target_day:
        raise RuntimeError(f"5m archive session mismatch: {latest_day} != {target_day}")
    if latest_coverage < required:
        raise RuntimeError(
            f"5m archive coverage {latest_coverage}/{len(symbols)} below required {required}"
        )

    status_path = root / "intraday-status.json"
    status = read(status_path, {})
    status.update(summary)
    status.update({
        "archiveFinalizedAt": now(),
        "archiveFinalizedSession": target_day,
        "archiveFinalizedSymbols": written,
        "archiveFinalizedRequired": required,
        "archiveFinalizedSkipped": skipped[:20],
    })
    write(status_path, status)
    return {
        "session": target_day,
        "written": written,
        "liveUniverse": len(symbols),
        "latestCoverage": latest_coverage,
        "required": required,
        "skipped": skipped[:20],
    }


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/market-intraday/market")
    print(json.dumps(finalize(root), ensure_ascii=False))


if __name__ == "__main__":
    main()
