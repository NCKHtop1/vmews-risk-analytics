import importlib.util
import unittest
from datetime import date,timedelta
from pathlib import Path

p=Path(__file__).resolve().parents[2]/"scripts/refresh_vn100_ownership_intelligence.py"
if p.exists():
    spec=importlib.util.spec_from_file_location("ownerpub",p)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
else:
    m=None


@unittest.skipUnless(m is not None, "Standalone publisher omitted by sparse checkout")
class OwnershipPublisherTests(unittest.TestCase):
    def test_vietcap_registration_does_not_become_an_execution(self):
        obj={'id':'sample_event_1','ticker':'FPT','eventCode':'DDIND',
             'eventTitleVi':'Nguyễn Văn Khoa - Đăng kí Mua 428,368 FPT',
             'actionTypeVi':'Mua','publicDate':'2026-06-29T00:00:00'}
        row=m.parse_vci_event('FPT',obj)
        self.assertEqual(row['type'],'registered_buy')
        self.assertEqual(row['quantity'],428368)
        self.assertEqual(row['person'],'Nguyễn Văn Khoa')
        self.assertEqual(row['date'],'2026-06-29')
        self.assertIsNone(m.parse_vci_event('MBB',obj))

    def test_price_reaction_does_not_fill_future_dates(self):
        start=date(2026,7,1)
        bars=[{'date':(start+timedelta(days=i)).isoformat(),'close':100.0+i*0.9,'volume':1200.0} for i in range(55)]
        event={'date':bars[45]['date'],'type':'registered_buy'}
        result=m.reaction(event,bars)
        self.assertEqual(result['anchorDate'],bars[45]['date'])
        self.assertEqual(result['status'],'observed')
        self.assertIsNotNone(result['returnPct']['1'])
        self.assertIsNotNone(result['returnPct']['3'])
        self.assertIsNone(result['returnPct']['10'])
        self.assertIsNone(m.reaction({'date':bars[-1]['date']},bars)['returnPct']['1'])

    def test_kbs_profile_ratios_are_percent_units(self):
        raw={'SB':'FPT','AD':'2025-12-31','Leaders':[{'NM':'Trương Gia Bình','PN':'CTHĐQT'}],
             'Ownership':[{'NM':'CĐ nội bộ','OR':16.05,'SH':273445441,'D':'2025-12-31'}],
             'Shareholders':[{'NM':'SCIC','OR':5.67,'V':96585637,'D':'2025-12-31'}]}
        d=m.profile_sections('FPT',raw)
        self.assertEqual(d['ownership'][0]['percentage'],16.05)
        self.assertEqual(d['shareholders'][0]['percentage'],5.67)
        self.assertEqual(d['leaders'][0]['name'],'Trương Gia Bình')
        self.assertEqual(d['asOf'],'2025-12-31')

    def test_event_result_and_registration_are_different(self):
        self.assertEqual(m.event_type('Nguyễn A - Báo cáo kết quả Đã bán 50,000 FPT','Bán'),'executed_sell')
        self.assertEqual(m.event_type('Nguyễn A - Đăng kí Bán 50,000 FPT','Bán'),'registered_sell')
        self.assertEqual(m.event_type('Thông báo giao dịch quyền mua',''),'reported_registration')

    def test_issuer_events_require_primary_sources(self):
        seed={'symbol':'MBB','title':'Báo cáo kết quả giao dịch',
              'disclosedAt':'2026-10-07T12:00:00+07:00',
              'sourceUrl':'https://www.mbbank.com.vn/chi-tiet/x'}
        self.assertTrue(m.is_source_event(seed,'MBB'))
        self.assertFalse(m.is_source_event({**seed,'sourceUrl':'https://evil.example/x'},'MBB'))
        self.assertFalse(m.is_source_event(seed,'FPT'))

    def test_no_mislabelled_share_count_when_title_does_not_identify_stock(self):
        obj={'id':'e2','ticker':'FPT','eventCode':'DDIND',
             'eventTitleVi':'Công bố mua quyền 12,500 chứng khoán phái sinh',
             'actionTypeVi':'Mua','publicDate':'2026-06-29T00:00:00'}
        self.assertIsNone(m.parse_vci_event('FPT',obj)['quantity'])

    def test_vn100_partial_api_failure_keeps_prior_verified_events(self):
        import json
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            symbols=['ACB','ANV','BAF']
            core=root/'companies.json'
            core.write_text(json.dumps([
                {'symbol':f'X{n:02d}','exchange':'HOSE','name':f'Company {n}'}
                for n in range(100)
            ]),encoding='utf-8')
            expected=json.loads(core.read_text(encoding='utf-8'))
            symbols=[x['symbol'] for x in expected[:3]]
            market=root/'market'
            (market/'history').mkdir(parents=True)
            bars=[{'time':(date.today()-timedelta(days=60-i)).isoformat(),
                   'close':100+i,'volume':1000} for i in range(60)]
            for sym in symbols:
                (market/'history'/f'{sym}.json').write_text(json.dumps({'bars':bars}),encoding='utf-8')
            prior_event={
                'id':'VCI-prior-verified','symbol':symbols[0],
                'person':'Nguyễn A','role':'Người nội bộ','type':'registered_buy',
                'disclosedAt':(date.today()-timedelta(days=20)).isoformat()+'T12:00:00+07:00',
                'date':(date.today()-timedelta(days=20)).isoformat(),
                'title':'Nguyễn A - Đăng kí Mua 500 cổ phiếu',
                'quantity':500,'sourceUrl':'https://iq.vietcap.com.vn/api/iq-insight-service/v1/events?ticker=ACB'
            }
            previous=root/'previous.json'
            previous.write_text(json.dumps({'symbols':{
                symbols[0]:{'events':[prior_event],'lastEventsSuccess':(date.today()-timedelta(days=2)).isoformat()}
            }}),encoding='utf-8')
            def source(sym,fetch_events=True):
                self.assertTrue(fetch_events)
                profile={'SB':sym,'Leaders':[{'NM':'Lãnh đạo thử nghiệm','PN':'CTHĐQT'}],
                         'Shareholders':[],'Ownership':[]}
                return {'symbol':sym,'profile':profile,'profileOk':True,
                        'eventsOk':sym==symbols[1],'events':[] if sym==symbols[1] else None,
                        'errors':[]}
            with mock.patch.object(m,'fetch_company',side_effect=source):
                report=m.build(core,market,root/'result.json',limit=3,previous=previous)
            self.assertEqual(report['universe']['processed'],3)
            self.assertEqual(report['universe']['profileFresh'],3)
            self.assertEqual(report['universe']['eventSourceAvailable'],2)
            self.assertEqual(report['universe']['events'],1)
            self.assertEqual(report['symbols'][symbols[0]]['sourceStatus']['events'],'retained')
            self.assertEqual(report['symbols'][symbols[1]]['sourceStatus']['events'],'ok')
            self.assertEqual(report['symbols'][symbols[2]]['sourceStatus']['events'],'unavailable')
            self.assertEqual(report['symbols'][symbols[0]]['events'][0]['quantity'],500)


    def test_hsg_invalid_kbs_ratio_uses_dated_vietcap_shareholders(self):
        from unittest import mock
        from datetime import datetime
        raw_profile={
            'SB':'HSG','Shareholders':[{'NM':'Lê Phước Vũ','OR':1669,
                                      'V':136949728,'D':'2026-06-30'}],
            'Leaders':[{'NM':'Lê Phước Vũ','PN':'CTHĐQT'}],
            'Ownership':[{'NM':'Cổ đông cá nhân','OR':20.0,'D':'2026-06-30'}]
        }
        response={'data':[
            {'ownerName':'Lê Phước Vũ','percentage':0.1696,'quantity':136949728,
             'publicDate':'2026-06-30'},
            {'ownerName':'Cổ đông rất cũ','percentage':0.50,'quantity':0,
             'publicDate':'2012-11-28'},
            {'ownerName':'Cổ đông nhỏ','percentage':0.005,'quantity':150,
             'publicDate':'2026-06-30'}
        ]}
        def fetch_mock(url,*args,**kwargs):
            if '/profile/' in url:return raw_profile
            if url.endswith('/HSG/shareholder'):return response
            raise AssertionError(url)
        with mock.patch.object(m,'fetch_json',side_effect=fetch_mock):
            result=m.fetch_company('HSG',fetch_events=False)
        self.assertTrue(result['profileOk'])
        self.assertEqual(result['errors'],[])
        profile=m.profile_sections('HSG',result['profile'])
        self.assertEqual(len(profile['shareholders']),1)
        self.assertEqual(profile['shareholders'][0]['name'],'Lê Phước Vũ')
        self.assertAlmostEqual(profile['shareholders'][0]['percentage'],16.96)
        self.assertEqual(profile['shareholders'][0]['shares'],136949728)
        self.assertTrue(profile['shareholdersSource'].endswith('/HSG/shareholder'))
        self.assertEqual(len(profile['leaders']),1)



if __name__=='__main__':
    unittest.main()
