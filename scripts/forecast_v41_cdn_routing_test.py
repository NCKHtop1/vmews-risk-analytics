#!/usr/bin/env python3
"""Regression guard for V41 post-publisher exact-SHA CDN routing."""
from pathlib import Path
import unittest

WORKFLOW = Path('.github/workflows/forecast-v41-cdn-browser-smoke.yml')


class V41CdnRoutingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')

    def test_routes_from_current_v20_publisher(self):
        text = self.text
        self.assertIn('workflow_run:', text)
        self.assertIn('Forecast V20.1 immutable-price audit and market intelligence', text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)

    def test_workflow_run_checks_out_published_main(self):
        text = self.text
        self.assertIn("github.event_name == 'workflow_run' && 'main'", text)
        self.assertIn('id: published', text)
        self.assertIn('git rev-parse HEAD', text)
        self.assertGreaterEqual(text.count('${{ steps.published.outputs.sha }}'), 2)

    def test_current_publisher_data_path_still_triggers_direct_push(self):
        self.assertIn("'data/forecast-dashboard-v12.json'", self.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
