"""Reject corrupt market values, unsafe RSS links and issuer mismatches."""
import importlib.util
import pathlib
import tempfile
import pandas as pd
import pandas_ta_classic as ta
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

    def test_intraday_missing_backfill_targets_only_missing_symbols(self):
        companies=[{'symbol':'FPT'},{'symbol':'VHM'},{'symbol':'VCB'}]
        original=m._refresh_one_history
        old_env=m.os.environ.get('INTRADAY_ONLY_MISSING')
        calls=[]
        def fake(out,symbol,minute=False):
            calls.append((symbol,minute))
            return symbol,True,None
        try:
            m._refresh_one_history=fake
            m.os.environ['INTRADAY_ONLY_MISSING']='1'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                m.write(out/'intraday/FPT.json',{'bars':[{'time':'x'}]})
                m.refresh_history_group(out,companies,minute=True)
                self.assertEqual({s for s,_ in calls},{'VHM','VCB'})
                self.assertTrue(all(minute for _,minute in calls))
                status=m.read(out/'intraday-status.json',{})
                self.assertEqual(status['expected'],2)
                self.assertEqual(status['universe'],3)
                self.assertTrue(status['onlyMissing'])
        finally:
            m._refresh_one_history=original
            if old_env is None:m.os.environ.pop('INTRADAY_ONLY_MISSING',None)
            else:m.os.environ['INTRADAY_ONLY_MISSING']=old_env

    def test_intraday_forced_symbols_override_missing_scan(self):
        companies=[{'symbol':'FPT'},{'symbol':'VHM'},{'symbol':'VCB'}]
        original=m._refresh_one_history
        old_symbols=m.os.environ.get('INTRADAY_SYMBOLS')
        old_workers=m.os.environ.get('INTRADAY_WORKERS')
        calls=[]
        def fake(out,symbol,minute=False):
            calls.append((symbol,minute))
            return symbol,True,None
        try:
            m._refresh_one_history=fake
            m.os.environ['INTRADAY_SYMBOLS']='VHM,VCB'
            m.os.environ['INTRADAY_WORKERS']='1'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                m.refresh_history_group(out,companies,minute=True)
                self.assertEqual([s for s,_ in calls],['VHM','VCB'])
                status=m.read(out/'intraday-status.json',{})
                self.assertEqual(status['forcedSymbols'],['VHM','VCB'])
                self.assertEqual(status['expected'],2)
        finally:
            m._refresh_one_history=original
            if old_symbols is None:m.os.environ.pop('INTRADAY_SYMBOLS',None)
            else:m.os.environ['INTRADAY_SYMBOLS']=old_symbols
            if old_workers is None:m.os.environ.pop('INTRADAY_WORKERS',None)
            else:m.os.environ['INTRADAY_WORKERS']=old_workers

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

    def test_pandas_ta_reference_suite_is_available(self):
        rows=80
        df=pd.DataFrame({
            'open':[100+i*.4 for i in range(rows)],
            'high':[102+i*.4 for i in range(rows)],
            'low':[99+i*.4 for i in range(rows)],
            'close':[101+i*.4+(1 if i%7==0 else 0) for i in range(rows)],
            'volume':[100000+i*1000 for i in range(rows)],
        })
        checks={
            'sma':df.ta.sma(length=20),
            'ema':df.ta.ema(length=20),
            'wma':df.ta.wma(length=20),
            'vwma':df.ta.vwma(length=20),
            'rsi':df.ta.rsi(length=14),
            'macd':df.ta.macd(fast=12,slow=26,signal=9),
            'bbands':df.ta.bbands(length=20,std=2),
            'supertrend':df.ta.supertrend(length=10,multiplier=3),
            'atr':df.ta.atr(length=14),
            'adx':df.ta.adx(length=14),
            'stoch':df.ta.stoch(k=14,d=3,smooth_k=3),
            'cci':df.ta.cci(length=20),
            'roc':df.ta.roc(length=10),
            'willr':df.ta.willr(length=14),
            'obv':df.ta.obv(),
            'mfi':df.ta.mfi(length=14),
            'cmf':df.ta.cmf(length=20),
        }
        self.assertTrue(all(v is not None and len(v)==rows for v in checks.values()))
        html=(ROOT/'frontend/index.html').read_text()
        for label in ('SMA','EMA','WMA','VWMA','RSI','MACD','Bollinger Bands','Supertrend','ATR','ADX','Stochastic','CCI','ROC','Williams %R','OBV','MFI','CMF'):
            self.assertIn(label,html)
        self.assertNotIn('id="tradingview-link"',html)

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

