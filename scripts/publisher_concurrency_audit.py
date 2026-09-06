#!/usr/bin/env python3
"""Audit GitHub Actions workflows that can directly advance ``main``.

The production race is caused by independent workflows committing generated
artifacts and then pushing them to ``main``.  The audit intentionally catches
explicit ``HEAD:main`` pushes plus bare/dynamic pushes from workflows that may
run on ``main``.  It does not flag a workflow whose push target is a fixed,
non-main release branch.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCK_GROUP = "vmews-main-data-publisher"


def _active_lines(text: str) -> str:
    """Drop full-line YAML/shell comments before scanning commands."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def workflow_can_run_main(text: str) -> bool:
    active = _active_lines(text)
    # Scheduled workflows always execute from the default branch. A manual
    # dispatch may also select main, so both are main-capable.
    if re.search(r"(?m)^\s*(?:schedule|workflow_dispatch):\s*$", active):
        return True
    if re.search(r"branches:\s*\[[^\]]*\bmain\b[^\]]*\]", active):
        return True
    if re.search(r"(?m)^\s*-\s*main\s*$", active):
        return True
    return False


def push_commands(text: str) -> list[str]:
    active = _active_lines(text)
    commands: list[str] = []
    for line in active.splitlines():
        if not re.search(r"\bgit\s+push\b", line):
            continue
        # Ignore diagnostic strings such as: echo "git push ..."
        before = re.split(r"\bgit\s+push\b", line, maxsplit=1)[0]
        if re.search(r"\b(?:echo|printf)\b[^;&|]*$", before):
            continue
        match = re.search(r"\bgit\s+push\b[^;&|]*", line)
        if match:
            commands.append(match.group(0).strip())
    return commands


def push_can_advance_main(command: str, workflow_text: str) -> bool:
    normalized = command.replace('"', "").replace("'", "")
    if re.search(r"(?:HEAD:|refs/heads/)main\b", normalized):
        return True
    if re.search(r"\borigin\s+main\b", normalized):
        return True

    main_capable = workflow_can_run_main(workflow_text)
    if not main_capable:
        return False

    # Dynamic current-ref pushes can resolve to main.
    if "GITHUB_REF_NAME" in normalized or "github.ref_name" in normalized:
        return True

    # A fixed non-main refspec is not a main writer.
    refspecs = re.findall(r"HEAD:([A-Za-z0-9._/-]+)", normalized)
    if refspecs:
        return any(ref == "main" for ref in refspecs)

    # Bare push (or `git push origin`) updates the checked-out branch; if the
    # workflow can run on main, it is a production publisher.
    tail = re.sub(r"^git\s+push\b", "", normalized).strip()
    tail = re.sub(r"\s+2>.*$", "", tail).strip()
    if not tail or tail == "origin":
        return True
    return False


def is_direct_main_writer(text: str) -> bool:
    active = _active_lines(text)
    has_write_permission = bool(
        re.search(r"(?m)^\s*contents:\s*write\s*$", active)
    )
    if not has_write_permission:
        return False
    return any(push_can_advance_main(command, text) for command in push_commands(text))


def concurrency_contract(text: str) -> tuple[bool, list[str]]:
    active = _active_lines(text)
    problems: list[str] = []
    if not re.search(
        rf"(?m)^\s*group:\s*[^\n]*{re.escape(LOCK_GROUP)}[^\n]*$", active
    ):
        problems.append(f"missing shared concurrency group {LOCK_GROUP!r}")

    cancel_values = re.findall(
        r"(?m)^\s*cancel-in-progress:\s*(true|false)\s*$", active, re.IGNORECASE
    )
    if not cancel_values or any(value.lower() != "false" for value in cancel_values):
        problems.append("cancel-in-progress must be false for every main publisher lock")
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
            f"FAIL: {len(failures)} main publisher workflow(s) can race. "
            f"All direct main publishers must use group {LOCK_GROUP!r} "
            "with cancel-in-progress: false."
        )
        return 1
    print(
        "PASS: repository-wide main publisher concurrency contract satisfied."
        if not failures
        else "REPORT ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
