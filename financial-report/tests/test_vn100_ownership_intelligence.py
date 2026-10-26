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


if __name__=='__main__':
    unittest.main()
