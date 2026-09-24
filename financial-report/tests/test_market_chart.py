"""Verify actual OHLC/volume aggregation and trading-session range selection."""
import json
from pathlib import Path
import subprocess
import unittest

class MarketChartTests(unittest.TestCase):
    def test_aggregate_ohlc_volume_and_selected_range(self):
        path=Path(__file__).resolve().parents[1]/'frontend/market.js'
        js=path.read_text().split('/* MARKET_MATH_START */')[1].split('/* MARKET_MATH_END */')[0]
        bars=[dict(time='2026-09-18',open=20,high=22,low=19,close=21,volume=100),
              dict(time='2026-09-21',open=21,high=23,low=20,close=22,volume=200),
              dict(time='2026-09-22',open=22,high=24,low=21,close=23,volume=300)]
        script=js+'\nconst b='+json.dumps(bars)+''';
const w=groupBars(b,'week'),m=groupBars(b,'month');
console.log(JSON.stringify({w,m,one:rangeCount(w,b,1),all:rangeCount(w,b,0),daily:groupBars(b)}));
'''
        r=json.loads(subprocess.check_output(['node','-e',script],text=True))
        self.assertEqual(len(r['w']),2)
        self.assertEqual(r['w'][1]['open'],21)
        self.assertEqual(r['w'][1]['close'],23)
        self.assertEqual(r['w'][1]['volume'],500)
        self.assertEqual(r['m'][0]['high'],24)
        self.assertEqual(r['m'][0]['low'],19)
        self.assertEqual(r['m'][0]['volume'],600)
        self.assertEqual(r['one'],1)
        self.assertEqual(r['all'],2)
        self.assertEqual(len(r['daily']),3)
