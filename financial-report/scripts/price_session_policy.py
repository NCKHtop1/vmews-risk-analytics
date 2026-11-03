"""Time-window policy for the FinQuery price publisher (Asia/Ho_Chi_Minh).

A scheduled GitHub Actions run can start late. An 11:40-12:55 startup must
publish a verified morning catch-up and ARRANGE the afternoon handoff instead
of exiting green without a successor.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def session_policy(now: datetime, event: str) -> dict[str, str]:
    local = now.astimezone(VN)
    minutes = local.hour * 60 + local.minute
    weekday = local.weekday() < 5

    policy = {"run": "false", "oneshot": "1", "bridge_afternoon": "false"}
    if weekday and 8 * 60 + 55 <= minutes <= 11 * 60 + 40:
        policy.update(run="true", oneshot="0", bridge_afternoon="true")
    elif weekday and 11 * 60 + 40 < minutes < 12 * 60 + 55:
        # The old workflow silently exited here (e.g. 11:42 on 2026-11-03).
        # Catch up once using lunch-age safeguards, then queue afternoon job.
        policy.update(run="true", oneshot="1", bridge_afternoon="true")
    elif weekday and 12 * 60 + 55 <= minutes <= 15 * 60 + 5:
        policy.update(run="true", oneshot="0", bridge_afternoon="false")
    elif event in {"workflow_dispatch"}:
        # Preserve the existing authorized manual out-of-hours one-shot.
        policy.update(run="true", oneshot="1", bridge_afternoon="false")
    elif event == "push" and weekday and 11 * 60 + 40 < minutes < 12 * 60 + 55:
        policy.update(run="true", oneshot="1", bridge_afternoon="true")
    return policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--event", default=os.environ.get("EVENT_NAME", ""))
    args = parser.parse_args()
    now = datetime.now(tz=VN)
    result = session_policy(now, args.event)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            for key, value in result.items():
                f.write(f"{key}={value}\n")
    print(f"FinQuery session {now:%Y-%m-%d %H:%M %Z}: {result}")


if __name__ == "__main__":
    main()
