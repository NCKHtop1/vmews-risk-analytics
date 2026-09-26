"""Reject corrupt market values, unsafe RSS links and issuer mismatches."""
import importlib.util
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('market', ROOT / 'scripts/refresh_market.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MarketTests(unittest.TestCase):
    def test_board_does_not_scale_vnd_or_invent_missing_price(self):
        items = [{'listingInfo': {'symbol':'MBB','refPrice':25000}, 'matchPrice':{'matchPrice':26000,'accumulatedVolume':1234,'time':1727100000000}}, {'listingInfo':{'symbol':'FPT'},'matchPrice':{'matchPrice':None}}]
        rows=m.normalize_board(items,['MBB','FPT'],'2026-09-24T00:00:00+00:00')
        self.assertEqual(rows['MBB']['price'],26000)
        self.assertAlmostEqual(rows['MBB']['changePct'],4)
        self.assertEqual(rows['MBB']['volume'],1234)
        self.assertNotIn('FPT',rows)
        self.assertIsNone(m.number('NaN'))

    def test_candles_reject_invalid_high_low_and_keep_original_prices(self):
        data=[{'symbol':'MBB','t':[1727100000,1727186400],'o':[25000,25000],'h':[27000,24000],'l':[24000,23000],'c':[26000,26000],'v':[1000,500]}]
        rows=m.normalize_history(data,'MBB')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['close'],26000)
        data[0]['v']=[]
        with self.assertRaises(ValueError): m.normalize_history(data,'MBB')

    def test_company_matching_boundaries(self):
        c={'symbol':'MBB','name':'Ngân hàng TMCP Quân đội'}
        self.assertTrue(m.company_match(c,'MBB tăng trưởng'))
        self.assertTrue(m.company_match(c,'Ngân hàng Quân đội công bố báo cáo'))
        self.assertFalse(m.company_match(c,'XMBB1 công bố'))
        self.assertFalse(m.company_match({'symbol':'GAS','name':'Tổng công ty khí Việt Nam'},'Giá gas bán lẻ'))

    def test_mb_bank_name_requires_banking_context(self):
        c={'symbol':'MBB','name':'Ngân hàng TMCP Quân đội'}
        self.assertTrue(m.company_match(c,'Lãi suất ngân hàng 24/9 tại MB, Techcombank'))
        self.assertTrue(m.company_match(c,'Ngân hàng MB công bố kết quả'))
        self.assertFalse(m.company_match(c,'Dung lượng bộ nhớ 512 MB'))
        self.assertFalse(m.company_match(c,'Ứng dụng ngân hàng chiếm 512 MB'))

    def test_history_never_substitutes_another_issuer(self):
        data=[{'symbol':'VIC','t':[1727100000],'o':[25000],'h':[27000],'l':[24000],'c':[26000],'v':[1000]}]
        with self.assertRaises(ValueError): m.normalize_history(data,'MBB')

    def test_overflow_timestamp_and_boolean_values_are_rejected(self):
        self.assertIsNone(m.timestamp(10**50))
        self.assertIsNone(m.number(True))

    def test_distinct_fpt_listed_companies(self):
        self.assertFalse(m.company_match({'symbol':'FPT','name':'Công ty Cổ phần FPT'}, 'FPT Retail tăng trưởng'))
        self.assertTrue(m.company_match({'symbol':'FRT','name':'Công ty Bán lẻ FPT'}, 'FPT Retail tăng trưởng'))

    def test_vneconomy_finance_feed_gets_topic_tags(self):
        companies=[{'symbol':'MBB','name':'Ngân hàng Quân đội'}]
        xml='<?xml version="1.0" encoding="UTF-8"?><rss><channel><item><title>Lãi suất ngân hàng giảm, thị trường chứng khoán tăng</title><link>https://vneconomy.vn/lai-suat-thi-truong.htm</link><pubDate>Thu, 24 Sep 2026 08:00:00 +0700</pubDate></item></channel></rss>'
        rows=m.parse_feed(xml,'VnEconomy','https://vneconomy.vn/tai-chinh.rss',companies,datetime(2026,9,24,10,tzinfo=timezone.utc))
        self.assertEqual(len(rows),1)
        self.assertTrue({'finance','rates','banking','stocks'}.issubset(set(rows[0]['topics'])))

    def test_movement_driver_exposes_weighted_evidence_without_claiming_causality(self):
        quote={'price':110,'changePct':5,'volume':2500,'high':112,'low':100,'status':'ok'}
        bars=[{'close':90+i*2,'volume':1000+i*10} for i in range(21)]
        news=[{'title':'Doanh nghiệp báo lãi tăng trưởng mạnh','url':'https://vnexpress.net/a','source':'VnExpress','publishedAt':datetime.now(timezone.utc).isoformat(),'symbols':['FPT']}]
        d=m.movement_driver('FPT',quote,bars,news,1.0)
        self.assertEqual(d['causality'],'association_not_proven')
        self.assertAlmostEqual(d['relativeStrengthPct'],4)
        self.assertGreater(d['volumeRatio20'],2)
        self.assertEqual(d['news72hCount'],1)
        self.assertEqual(sum(round(f['weight'],2) for f in d['factors']),1.0)
        self.assertTrue(any(f['id']=='relative' and f['contribution']>0 for f in d['factors']))
        self.assertGreater(d['score'],0)
        self.assertIn(d['confidence'],('thấp','trung bình','cao'))

    def test_fast_price_refresh_does_not_fetch_per_symbol_candles(self):
        companies=[{'symbol':'FPT','name':'Công ty Cổ phần FPT'}]
        original=m.request
        calls=[]
        def fake_request(url,payload=None):
            calls.append((url,payload))
            return b'[{"listingInfo":{"symbol":"FPT","refPrice":100000},"matchPrice":{"symbol":"FPT","matchPrice":101000,"accumulatedVolume":500000,"highest":102000,"lowest":99000,"time":1727100000000}}]'
        try:
            m.request=fake_request
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                (out/'history').mkdir(parents=True)
                bars=[{'time':f'2026-09-{day:02d}','open':90000,'high':92000,'low':89000,'close':90000+day*100,'volume':100000+day} for day in range(1,22)]
                m.write(out/'history/FPT.json',{'symbol':'FPT','bars':bars})
                m.write(out/'news.json',{'items':[]})
                m.prices(out,companies)
                self.assertEqual(len(calls),1)
                self.assertIn('getList',calls[0][0])
                self.assertNotIn('gap-chart',calls[0][0])
                self.assertTrue((out/'drivers.json').exists())
                status=m.read(out/'prices-status.json',{})
                self.assertEqual(status['quotes'],1)
                self.assertEqual(status['histories'],1)
                self.assertEqual(status['historyRefresh'],'separate_eod_job')
        finally:
            m.request=original

    def test_research_analysis_is_local_and_ui_has_no_external_model_noise(self):
        js=(ROOT/'frontend/research-ai.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        for forbidden in ('generativelanguage.googleapis.com','Gemini','Fallback cục bộ','Máy chủ AI chưa phản hồi','research-ai-key'):
            self.assertNotIn(forbidden,js+html)
        self.assertIn('Phân tích chuyên sâu',html)
        self.assertIn('annualSnapshot',js)
        self.assertIn('quarterSnapshot',js)
        self.assertIn('riskSignals',js)

    def test_native_chart_replaces_restricted_tradingview_widget(self):
        market=(ROOT/'frontend/market.js').read_text()
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        self.assertNotIn('embed-widget-advanced-chart.js',market+html)
        self.assertNotIn('tradingview-widget-slot',html)
        self.assertIn('Biểu đồ FinQuery',html)
        self.assertIn('<option value="15m" selected>15 phút</option>',html)
        self.assertIn("nativeTitle.textContent='Biểu đồ FinQuery · '+state.symbol",market)
        self.assertIn("this.tf='1d'",chart)

    def test_local_analysis_has_natural_language_and_concept_understanding(self):
        js=(ROOT/'frontend/research-ai.js').read_text()
        self.assertIn('movementNarrative',js)
        self.assertIn('financialNarrative',js)
        self.assertIn('conceptHTML',js)
        for concept in ('ROE','ROA','FCF','OCF','Biên lợi nhuận gộp','Đòn bẩy tài chính'):
            self.assertIn(concept,js)
        self.assertIn("return'concept'",js)

    def test_rss_requires_real_publisher_link_and_publication_date(self):
        companies=[{'symbol':'MBB','name':'Ngân hàng Quân đội'}]
        def item(url,day='Thu, 24 Sep 2026 08:00:00 +0700'):
            return f'<item><title>MBB công bố kết quả</title><link>{url}</link><pubDate>{day}</pubDate></item>'
        xml='\ufeff\n \n<?xml version="1.0" encoding="UTF-8"?><rss><channel>'+item('https://vnexpress.net/a.html?utm_source=x')+item('javascript:alert(1)')+item('https://vnexpress.net.evil.test/a')+item('https://vnexpress.net/old','bad date')+'</channel></rss>'
        rows=m.parse_feed(xml,'VnExpress','https://vnexpress.net/rss/kinh-doanh.rss',companies,datetime(2026,9,24,10,tzinfo=timezone.utc))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['symbols'],['MBB'])
        self.assertEqual(rows[0]['url'],'https://vnexpress.net/a.html')

if __name__=='__main__': unittest.main()

