"""Timestamped TradingView fallback must never invent current-session quotes."""
import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('market_tv_fallback', ROOT / 'scripts' / 'refresh_market.py')
market = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)


class FakeFrame:
    def __init__(self, items):
        self.items = items

    def iterrows(self):
        return enumerate(self.items)


class TradingViewFallbackTests(unittest.TestCase):
    def test_per_symbol_timestamp_and_reference_are_preserved(self):
        observed = datetime(2026, 10, 8, 4, 30, tzinfo=timezone.utc)
        row = {
            'name': 'FPT', 'exchange': 'HOSE', 'close': 60600,
            'change': 1.507537688442211, 'volume': 4847522,
            'open': 59500, 'high': 61500, 'low': 58900,
            'update_time': observed.timestamp(), 'update_mode': 'delayed_streaming_900',
        }
        rows = market.normalize_tradingview_board(FakeFrame([row]), ['FPT'], observed.isoformat())
        self.assertEqual(rows['FPT']['sourceTime'], observed.isoformat())
        self.assertAlmostEqual(rows['FPT']['reference'], 59700, delta=1)
        self.assertEqual(rows['FPT']['sourceMode'], 'delayed_streaming_900')
        self.assertEqual(rows['FPT']['unit'], 'VND')

    def test_old_and_future_provider_timestamp_are_rejected(self):
        current = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)
        def row(symbol, offset):
            return {
                'name': symbol, 'exchange': 'HOSE', 'close': 10000,
                'change': 0.5, 'volume': 1000,
                'update_time': (current + timedelta(minutes=offset)).timestamp(),
            }
        rows = market.normalize_tradingview_board(
            FakeFrame([row('FPT', -60), row('MBB', 20)]), ['FPT', 'MBB'], current.isoformat()
        )
        fresh, stale = market.current_session_quotes(rows, current=current, max_age_minutes=30)
        self.assertEqual(fresh, {})
        self.assertEqual(set(stale), {'FPT', 'MBB'})

    def test_unknown_exchange_and_missing_timestamp_do_not_publish(self):
        rows = FakeFrame([
            {'name':'FPT', 'exchange':'HNX', 'close':10000, 'change':1, 'volume':500, 'update_time':123},
            {'name':'MBB', 'exchange':'HOSE', 'close':20000, 'change':1, 'volume':100, 'update_time':None},
        ])
        with self.assertRaises(ValueError):
            market.normalize_tradingview_board(rows, ['FPT','MBB'], '2026-10-08T05:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
