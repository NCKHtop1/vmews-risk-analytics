"""Guard against accepting a stale Pages deployment with matching code SHA."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PagesRevisionGateTests(unittest.TestCase):
    def test_pages_waits_for_all_four_revisions(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        for key in ("EXPECTED_CODE_SHA", "EXPECTED_FINANCIAL_SHA", "EXPECTED_INSIGHT_SHA", "EXPECTED_MARKET_SHA"):
            self.assertIn(key, workflow)
        self.assertIn("found.get(key)!=value", workflow)
        self.assertIn("raise SystemExit(1 if missing else 0)", workflow)
        self.assertIn("if python - <<'PY'", workflow)
        self.assertIn("Pages revision quartet check", workflow)
        self.assertIn('test "$ready" = 1', workflow)
        self.assertIn("marketData", workflow)


if __name__ == "__main__":
    unittest.main()
