"""Remove cross-issuer contamination from every current intelligence artifact."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forecast_v14_signal_audit import security_match


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FILES = (
    "research-news.json",
    "research-news-v10.json",
    "fireant-intelligence-v18.json",
    "community-intelligence-live-v19.json",
)


def _clean_rows(symbol: str, rows: Any, universe: set[str]) -> tuple[Any, list[str]]:
    if not isinstance(rows, list):
        return rows, []
    clean: list[Any] = []
    rejected: list[str] = []
    for row in rows:
        title = str((row or {}).get("title") or "") if isinstance(row, dict) else ""
        # These are current scraped/provider artifacts, not a manually curated
        # historical event table.  If the ticker or a known issuer name is not
        # explicit, abstain instead of trusting the search query assignment.
        if title and not security_match(symbol, title, universe, require_explicit=True):
            rejected.append(title)
            continue
        clean.append(row)
    return clean, rejected


def sanitize_payload(payload: dict[str, Any], universe: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    symbols = payload.get("symbols") or {}
    rejected: dict[str, list[str]] = {}
    checked = 0
    kept = 0
    for symbol, value in list(symbols.items()):
        symbol = str(symbol).upper()
        if isinstance(value, list):
            checked += len(value)
            symbols[symbol], removed = _clean_rows(symbol, value, universe)
            kept += len(symbols[symbol])
            if removed:
                rejected[symbol] = removed
        elif isinstance(value, dict):
            for key in ("claims", "watchlist"):
                rows = value.get(key)
                if not isinstance(rows, list):
                    continue
                checked += len(rows)
                value[key], removed = _clean_rows(symbol, rows, universe)
                kept += len(value[key])
                if removed:
                    rejected.setdefault(symbol, []).extend(removed)
    payload["symbols"] = symbols
    return payload, {
        "checked": checked,
        "kept": kept,
        "rejected": sum(len(rows) for rows in rejected.values()),
        "rejectedBySymbol": rejected,
    }


def main() -> None:
    dashboard = json.loads((DATA / "forecast-dashboard-v12.json").read_text(encoding="utf-8"))
    universe = set((dashboard.get("symbols") or {}))
    audits: dict[str, Any] = {}
    for filename in FILES:
        path = DATA / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        cleaned, audit = sanitize_payload(payload, universe)
        path.write_text(
            json.dumps(
                cleaned,
                ensure_ascii=False,
                indent=2 if filename == "research-news.json" else None,
                separators=None if filename == "research-news.json" else (",", ":"),
                allow_nan=False,
            ) + ("\n" if filename == "research-news.json" else ""),
            encoding="utf-8",
        )
        audits[filename] = audit
    report = {
        "version": "VMEWS-INTELLIGENCE-SANITIZATION-20.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "universeSymbols": len(universe),
        "status": "PASS",
        "artifacts": audits,
        "rejected": sum(item["rejected"] for item in audits.values()),
        "policy": "Leading/explicit competing issuer identity is rejected across all current artifacts; legitimate multi-issuer headlines remain eligible for each named ticker.",
    }
    (DATA / "intelligence-sanitization-v20.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"intelligenceSanitization": {
        "status": report["status"], "artifacts": len(audits), "rejected": report["rejected"]
    }}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
