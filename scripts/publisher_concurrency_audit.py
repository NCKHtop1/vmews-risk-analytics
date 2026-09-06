#!/usr/bin/env python3
"""Audit GitHub Actions workflows that can write generated data to main.

Any workflow that both has contents: write and contains a git push to main must
join the same non-cancelling concurrency group.  Different per-workflow groups
allow two validated publishers to race between commit/rebase/push, which can
produce false-red CI or let an older generated artifact overwrite a newer one.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCK_GROUP = "vmews-main-data-publisher"


def is_direct_main_writer(text: str) -> bool:
    has_write_permission = bool(re.search(r"(?m)^\s*contents:\s*write\s*$", text))
    has_push = bool(
        re.search(r"git\s+push[^\n]*(?:HEAD:main|origin\s+main|refs/heads/main)", text)
    )
    return has_write_permission and has_push


def concurrency_contract(text: str) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if LOCK_GROUP not in text:
        problems.append(f"missing shared concurrency group {LOCK_GROUP!r}")
    if not re.search(r"(?m)^\s*cancel-in-progress:\s*false\s*$", text):
        problems.append("cancel-in-progress must be false for a publisher")
    return not problems, problems


def audit() -> tuple[list[str], dict[str, list[str]]]:
    writers: list[str] = []
    failures: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if not is_direct_main_writer(text):
            continue
        rel = path.relative_to(ROOT).as_posix()
        writers.append(rel)
        ok, problems = concurrency_contract(text)
        if not ok:
            failures[rel] = problems
    return writers, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    writers, failures = audit()
    print(f"Direct main publishers: {len(writers)}")
    for path in writers:
        state = "PASS" if path not in failures else "FAIL"
        print(f"[{state}] {path}")
        for problem in failures.get(path, []):
            print(f"  - {problem}")

    if failures and not args.report_only:
        print(
            f"FAIL: {len(failures)} publisher workflow(s) can race. "
            f"All direct main publishers must use group {LOCK_GROUP!r} with cancel-in-progress: false."
        )
        return 1
    print("PASS: repository-wide publisher concurrency contract satisfied." if not failures else "REPORT ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
