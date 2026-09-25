"""Run numerical regression tests for the production chart math."""
from pathlib import Path
import subprocess
import unittest
class MarketChartTests(unittest.TestCase):
    def test_chart_math(self):
        subprocess.run(['node','--test',str(Path(__file__).with_name('chart_math.test.cjs'))],check=True)
