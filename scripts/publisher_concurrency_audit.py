#!/usr/bin/env python3
"""Audit GitHub Actions workflows that can publish repository data.

A workflow with ``contents: write`` and an executable ``git push`` can advance
``main`` even when the command is a bare ``git push`` or uses a dynamic ref such
as ``HEAD:$GITHUB_REF_NAME``.  Every such publisher must therefore join the same
non-cancelling repository-wide publication lock.  This prevents independent
scheduled/manual publishers from racing between commit/rebase/push.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCK_GROUP = "vmews-main-data-publisher"


def _active_lines(text: str) -> str:
    """Return workflow text with full-line YAML/shell comments removed."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def is_direct_repo_writer(text: str) -> bool:
    active = _active_lines(text)
    has_write_permission = bool(
        re.search(r"(?m)^\s*contents:\s*write\s*$", active)
    )
    # Deliberately catch all executable push forms, including:
    #   git push
    #   git push origin HEAD:main
    #   git push origin "HEAD:$GITHUB_REF_NAME"
    #   if git push ...; then
    has_push = bool(re.search(r"(?m)(?:^|[;&|]\s*|\bif\s+)git\s+push\b", active))
    return has_write_permission and has_push


def concurrency_contract(text: str) -> tuple[bool, list[str]]:
    active = _active_lines(text)
    problems: list[str] = []
    shared_group = bool(
        re.search(
            rf"(?m)^\s*group:\s*[^\n]*{re.escape(LOCK_GROUP)}[^\n]*$",
            active,
        )
    )
    if not shared_group:
        problems.append(f"missing shared concurrency group {LOCK_GROUP!r}")

    cancel_values = re.findall(
        r"(?m)^\s*cancel-in-progress:\s*(true|false)\s*$", active, re.IGNORECASE
    )
    if not cancel_values or any(value.lower() != "false" for value in cancel_values):
        problems.append("cancel-in-progress must be false for every publisher lock")
    return not problems, problems


def audit() -> tuple[list[str], dict[str, list[str]]]:
    writers: list[str] = []
    failures: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if not is_direct_repo_writer(text):
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
    print(f"Direct repository publishers: {len(writers)}")
    for path in writers:
        state = "PASS" if path not in failures else "FAIL"
        print(f"[{state}] {path}")
        for problem in failures.get(path, []):
            print(f"  - {problem}")

    if failures and not args.report_only:
        print(
            f"FAIL: {len(failures)} publisher workflow(s) can race. "
            f"All repository publishers must use group {LOCK_GROUP!r} "
            "with cancel-in-progress: false."
        )
        return 1
    print(
        "PASS: repository-wide publisher concurrency contract satisfied."
        if not failures
        else "REPORT ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
