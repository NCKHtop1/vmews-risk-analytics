#!/usr/bin/env python3
"""Restore the immutable V11 historical evidence seed without marketplace actions.

The seed is pinned to an exact GitHub Actions artifact and exact per-file SHA256.
Retries are transport-only; any content mismatch is a hard failure.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

REPO = "NCKHtop1/vmews-risk-analytics"
ARTIFACT_ID = 9215419805
RUN_ID = 31790884093
EXPECTED = {
    "sentiment-v11.json": (11643333, "d94a4ca26ffd70d292e7fa0bea143baa877ec335ac6055b3a86c0ab24e319eed"),
    "market-scan.json": (817525, "3b4a10c99044ccf84762f58537eaaf29aae60e9011d84d43a621b2db436c7352"),
}

def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def download(url: str, token: str, dest: pathlib.Path) -> None:
    last = None
    for attempt in range(1, 7):
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vmews-v12-seed-restore",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r, dest.open("wb") as out:
                shutil.copyfileobj(r, out)
            if dest.stat().st_size <= 0:
                raise RuntimeError("empty artifact download")
            return
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            retry = exc.headers.get("Retry-After")
            delay = float(retry) if retry and retry.isdigit() else min(45.0, 4.0 * attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            delay = min(45.0, 4.0 * attempt)
        if attempt < 6:
            time.sleep(delay)
    raise RuntimeError(f"seed artifact download failed after bounded retries: {last}")

def main() -> None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    outdir = pathlib.Path("data/v12-seed")
    outdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v12-seed-") as td:
        root = pathlib.Path(td)
        archive = root / "seed.zip"
        download(f"https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip", token, archive)
        extracted = root / "unzipped"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        evidence = {}
        for name, (expected_bytes, expected_hash) in EXPECTED.items():
            matches = sorted(extracted.rglob(name))
            if len(matches) != 1:
                raise RuntimeError(f"expected exactly one {name}, found {len(matches)}")
            src = matches[0]
            actual_bytes = src.stat().st_size
            actual_hash = sha256(src)
            if actual_bytes != expected_bytes or actual_hash != expected_hash:
                raise RuntimeError(f"immutable seed mismatch {name}: bytes={actual_bytes}, sha256={actual_hash}")
            dst = outdir / name
            shutil.copyfile(src, dst)
            # Parse once so corrupt-but-hash-impossible errors are explicit in logs.
            with dst.open(encoding="utf-8") as f:
                parsed = json.load(f)
            evidence[name] = {"bytes": actual_bytes, "sha256": actual_hash, "version": parsed.get("version")}
    provenance = {
        "status": "PASS",
        "policy": "EXACT_GITHUB_ARTIFACT_AND_PER_FILE_SHA256; TRANSPORT_RETRY_ONLY",
        "repository": REPO,
        "runId": RUN_ID,
        "artifactId": ARTIFACT_ID,
        "files": evidence,
    }
    pathlib.Path("data/v12-seed-provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2))

if __name__ == "__main__":
    main()
