from __future__ import annotations

import unittest

from publisher_concurrency_audit import (
    LOCK_GROUP,
    concurrency_contract,
    is_direct_main_writer,
    push_can_advance_main,
    push_commands,
    workflow_can_run_main,
)


class PublisherDetectionTest(unittest.TestCase):
    def test_explicit_main_ref_is_always_a_main_writer(self) -> None:
        text = """
permissions:
  contents: write
jobs:
  x:
    steps:
      - run: git push origin HEAD:main
"""
        self.assertTrue(is_direct_main_writer(text))

    def test_bare_push_from_scheduled_workflow_can_advance_main(self) -> None:
        text = """
on:
  schedule:
    - cron: '0 0 * * *'
permissions:
  contents: write
jobs:
  x:
    steps:
      - run: git push
"""
        self.assertTrue(workflow_can_run_main(text))
        self.assertTrue(is_direct_main_writer(text))

    def test_dynamic_ref_push_from_main_capable_workflow_is_detected(self) -> None:
        text = """
on:
  push:
    branches: [main, release]
permissions:
  contents: write
jobs:
  x:
    steps:
      - run: |
          if git push origin "HEAD:$GITHUB_REF_NAME"; then exit 0; fi
"""
        commands = push_commands(text)
        self.assertEqual(len(commands), 1)
        self.assertTrue(push_can_advance_main(commands[0], text))

    def test_fixed_non_main_ref_is_not_a_main_writer(self) -> None:
        text = """
on:
  workflow_dispatch:
permissions:
  contents: write
jobs:
  x:
    steps:
      - run: git push origin HEAD:forecast-v12-hardening
"""
        self.assertTrue(workflow_can_run_main(text))
        self.assertFalse(is_direct_main_writer(text))

    def test_echoed_git_push_is_not_treated_as_execution(self) -> None:
        text = """
on:
  schedule:
    - cron: '0 0 * * *'
permissions:
  contents: write
jobs:
  x:
    steps:
      - run: echo "git push origin HEAD:main"
"""
        self.assertEqual(push_commands(text), [])
        self.assertFalse(is_direct_main_writer(text))

    def test_shared_non_cancelling_lock_passes_contract(self) -> None:
        text = f"""
concurrency:
  group: {LOCK_GROUP}-${{{{ github.ref_name }}}}
  cancel-in-progress: false
"""
        ok, problems = concurrency_contract(text)
        self.assertTrue(ok, problems)

    def test_cancel_true_fails_contract(self) -> None:
        text = f"""
concurrency:
  group: {LOCK_GROUP}-main
  cancel-in-progress: true
"""
        ok, problems = concurrency_contract(text)
        self.assertFalse(ok)
        self.assertTrue(any("cancel-in-progress" in item for item in problems))


if __name__ == "__main__":
    unittest.main()
