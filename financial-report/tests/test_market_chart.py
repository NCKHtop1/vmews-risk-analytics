"""Run numerical regression tests for the production chart math."""
from pathlib import Path
import subprocess
import unittest
class MarketChartTests(unittest.TestCase):
    def test_chart_math(self):
        subprocess.run(['node','--test',*[str(p) for p in Path(__file__).parent.glob('chart_*.test.cjs')]],check=True)
