import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('universe_builder', ROOT / 'scripts/build_hose_universe.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def bars(price, volume, count=80, start=1):
    out=[]
    for i in range(count):
        day=f"2026-09-{min(29, start + i):02d}" if i >= count-20 else f"2026-08-{(i % 28)+1:02d}"
        out.append({'date':day,'close':price,'volume':volume,'open':price,'high':price,'low':price})
    # make dates unique and ordered for the last 20 observations
    for i,row in enumerate(out):
        row['date']=f"2026-{7 + (i//28):02d}-{(i%28)+1:02d}"
    out[-1]['date']='2026-09-29'
    return out


class UniverseBuilderTests(unittest.TestCase):
    def test_core_liquid_and_discovery_tiers_are_separate(self):
        core=[
            {'symbol':'AAA','name':'Core A','exchange':'HOSE'},
            {'symbol':'BBB','name':'Core B','exchange':'HOSE'},
        ]
        histories={
            'AAA':bars(50000,500000),
            'BBB':bars(30000,500000),
            'CCC':bars(40000,1000000),   # 40bn/day -> liquid
            'DDD':bars(10000,200000),    # 2bn/day -> discovery
        }
        dashboard={'asOf':'2026-09-29','symbols':{},'charts':{}}
        result=u.build_universe(core,{'AAA','BBB','CCC','DDD'},histories,dashboard)
        self.assertEqual(result['symbols']['AAA']['tier'],'CORE')
        self.assertEqual(result['symbols']['CCC']['tier'],'LIQUID')
        self.assertEqual(result['symbols']['DDD']['tier'],'DISCOVERY')
        self.assertTrue(result['symbols']['CCC']['liveMarketEligible'])
        self.assertFalse(result['symbols']['DDD']['liveMarketEligible'])
        self.assertIn('DDD',result['scannerSymbols'])
        self.assertNotIn('DDD',result['forecastEligibleSymbols'])

    def test_liquid_gate_requires_activity_history_and_turnover(self):
        core=[{'symbol':'AAA','name':'Core A','exchange':'HOSE'}]
        good=bars(50000,1000000)
        inactive=bars(50000,1000000)
        for row in inactive[-5:]:
            row['volume']=0
        short=bars(50000,1000000,count=40)
        result=u.build_universe(
            core,
            {'AAA','CCC','DDD','EEE'},
            {'AAA':good,'CCC':good,'DDD':inactive,'EEE':short},
            {'asOf':'2026-09-29','symbols':{},'charts':{}},
        )
        self.assertEqual(result['symbols']['CCC']['tier'],'LIQUID')
        self.assertEqual(result['symbols']['DDD']['tier'],'DISCOVERY')
        self.assertEqual(result['symbols']['EEE']['tier'],'DISCOVERY')

    def test_liquid_extra_cap_is_deterministic(self):
        old=u.MAX_LIQUID_EXTRA
        try:
            u.MAX_LIQUID_EXTRA=2
            core=[{'symbol':'AAA','name':'Core A','exchange':'HOSE'}]
            histories={'AAA':bars(50000,500000)}
            for symbol,volume in [('CCC',1200000),('DDD',1100000),('EEE',1000000)]:
                histories[symbol]=bars(50000,volume)
            result=u.build_universe(core,set(histories),histories,{'asOf':'2026-09-29','symbols':{},'charts':{}})
        finally:
            u.MAX_LIQUID_EXTRA=old
        liquid=[s for s,row in result['symbols'].items() if row['tier']=='LIQUID']
        self.assertEqual(liquid,['CCC','DDD'])
        self.assertEqual(result['counts']['liquid'],2)

    def test_fresher_market_history_overrides_stale_forecast_chart(self):
        core=[{'symbol':'AAA','name':'Core A','exchange':'HOSE'}]
        current=bars(50000,1000000)
        current[-1]['date']='2026-10-07'
        stale_chart=bars(50000,1000000)
        stale_chart[-1]['date']='2026-09-29'
        result=u.build_universe(
            core,
            {'AAA','CCC'},
            {'AAA':current,'CCC':current},
            {'asOf':'2026-09-29','symbols':{},'charts':{'AAA':stale_chart,'CCC':stale_chart}},
        )
        self.assertEqual(result['asOf'],'2026-10-07')
        self.assertEqual(result['symbols']['CCC']['latestDate'],'2026-10-07')
        self.assertEqual(result['symbols']['CCC']['tier'],'LIQUID')
        self.assertTrue(result['symbols']['CCC']['forecastEligible'])

    def test_policy_is_fail_closed_for_stale_non_core_symbol(self):
        core=[{'symbol':'AAA','name':'Core A','exchange':'HOSE'}]
        rows=bars(50000,1000000)
        rows[-1]['date']='2026-09-28'
        result=u.build_universe(core,{'AAA','CCC'},{'AAA':bars(50000,500000),'CCC':rows},{'asOf':'2026-09-29','symbols':{},'charts':{}})
        self.assertEqual(result['symbols']['CCC']['tier'],'DISCOVERY')
        self.assertFalse(result['symbols']['CCC']['forecastEligible'])


if __name__ == '__main__':
    unittest.main()
