"""Keep validated EOD Discovery technical evidence during live quote refresh."""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'scripts'))
spec=importlib.util.spec_from_file_location('market_scanner_coverage',ROOT / 'scripts' / 'refresh_market.py')
market=importlib.util.module_from_spec(spec)
spec.loader.exec_module(market)


class PriceScannerCoverageTests(unittest.TestCase):
    def test_public_universe_minimization_does_not_drop_validated_discovery(self):
        full={
            'version':'FINQUERY-HOSE-UNIVERSE-1.0',
            'asOf':'2026-10-07',
            'scannerSymbols':['FPT','AAA'],
            'liveMarketSymbols':['FPT'],
            'symbols':{
                'FPT':{'scannerEligible':True,'tier':'CORE'},
                'AAA':{'scannerEligible':True,'tier':'DISCOVERY'},
            },
            'discoveryTechnical':{
                'AAA':{'barDate':'2026-10-07','matched':True,'priority':42,'bias':'mixed'},
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            out=pathlib.Path(folder)
            market.sync_market_universe(out,full)
            public=market.read(out/'universe.json',{})
            self.assertNotIn('discoveryTechnical',public)
            previous=market.technical_scan_symbol
            try:
                market.technical_scan_symbol=lambda symbol,bars,quote,prior: {
                    'symbol':symbol,'barDate':'2026-10-08','matched':False,'priority':0,
                    'sourceTime':quote.get('sourceTime'),
                }
                matches=market.build_technical_scanner(
                    out,[{'symbol':'FPT','tier':'CORE'}],
                    {'FPT':{'symbol':'FPT','sourceTime':'2026-10-08T04:30:00+00:00'}},
                    universe=full,
                )
            finally:
                market.technical_scan_symbol=previous
            scanner=market.read(out/'technical-signals.json',{})
            self.assertEqual(scanner['universe'],2)
            self.assertEqual(scanner['coverage'],2)
            self.assertEqual(scanner['liveCoverage'],1)
            self.assertEqual(scanner['discoveryCoverage'],1)
            self.assertEqual(scanner['symbols']['AAA']['cadence'],'EOD')
            self.assertEqual(scanner['symbols']['FPT']['cadence'],'LIVE_15M')
            self.assertEqual(len(matches),1)

    def test_discovery_not_trusted_without_scanner_membership(self):
        with tempfile.TemporaryDirectory() as folder:
            out=pathlib.Path(folder)
            full={
                'scannerSymbols':['FPT','AAA'],
                'symbols':{'AAA':{'scannerEligible':False}},
                'discoveryTechnical':{'AAA':{'matched':True,'priority':99}},
            }
            result=market.build_technical_scanner(out,[],{},universe=full)
            scanner=market.read(out/'technical-signals.json',{})
            self.assertEqual(scanner['universe'],2)
            self.assertEqual(scanner['coverage'],0)
            self.assertEqual(scanner['status'],'retained')
            self.assertEqual(result,[])


if __name__=='__main__':
    unittest.main()
