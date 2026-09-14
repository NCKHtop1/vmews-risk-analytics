#!/usr/bin/env python3
"""Forward-compatible immutable CDN model-version contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MODEL_VERSION_RE = re.compile(r"^VMEWS-MARKET-FORECAST-(\d+)\.0\.0$")


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_versions(*, market: dict, dashboard: dict, current: dict | None = None, min_major: int = 41) -> str:
    versions = {
        "market": market.get("version"),
        "dashboard": dashboard.get("modelVersion"),
    }
    if current is not None:
        versions["current"] = current.get("modelVersion")

    missing = [name for name, value in versions.items() if not isinstance(value, str) or not value]
    if missing:
        raise AssertionError(f"missing model version on published surfaces: {missing}")

    unique = set(versions.values())
    if len(unique) != 1:
        raise AssertionError(f"model version parity failed: {versions}")

    version = next(iter(unique))
    match = MODEL_VERSION_RE.fullmatch(version)
    if not match:
        raise AssertionError(f"malformed model version: {version}")
    major = int(match.group(1))
    if major < min_major:
        raise AssertionError(f"model version regressed below V{min_major}: {version}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", required=True)
    parser.add_argument("--dashboard", required=True)
    parser.add_argument("--current")
    parser.add_argument("--min-major", type=int, default=41)
    args = parser.parse_args()

    version = validate_versions(
        market=_load(args.market),
        dashboard=_load(args.dashboard),
        current=_load(args.current) if args.current else None,
        min_major=args.min_major,
    )
    print(f"CDN model-version contract PASS: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
