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

    def test_full_daily_history_paginates_and_preserves_older_retained_bars(self):
        original=m.request
        calls=[]
        base=1700000000
        def payload(times):
            return [{'symbol':'FPT','t':times,'o':[100]*len(times),'h':[110]*len(times),'l':[90]*len(times),'c':[105]*len(times),'v':[1000]*len(times)}]
        pages=[
            list(range(base-1599*86400,base+1,86400)),
            list(range(base-3199*86400,base-1599*86400,86400)),
        ]
        def fake_request(url,payload_arg=None):
            calls.append(payload_arg)
            idx=min(len(calls)-1,len(pages)-1)
            return m.json.dumps(payload(pages[idx])).encode()
        try:
            m.request=fake_request
            bars=m._full_daily_history('FPT',2500)
            self.assertGreaterEqual(len(bars),2500)
            self.assertGreaterEqual(len(calls),2)
            self.assertTrue(all(call['countBack']<=1600 for call in calls))
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                m.write(out/'history/FPT.json',{'symbol':'FPT','bars':[{'time':'2000-01-03','open':90,'high':100,'low':80,'close':95,'volume':500}]})
                m.os.environ['HISTORY_COUNT_BACK']='2500'
                ok=m._refresh_one_history(out,'FPT',minute=False)
                saved=m.read(out/'history/FPT.json',{})
                self.assertTrue(ok[1])
                self.assertEqual(saved['bars'][0]['time'],'2000-01-03')
                self.assertEqual(saved['barCount'],len(saved['bars']))
                self.assertEqual(saved['firstBar'],'2000-01-03')
        finally:
            m.request=original
            m.os.environ.pop('HISTORY_COUNT_BACK',None)

    def test_full_daily_history_resumes_before_retained_oldest_bar_and_keeps_partial_progress(self):
        original=m._history_page
        calls=[]
        previous=[
            {'time':'2020-01-02','open':100,'high':110,'low':90,'close':105,'volume':1000},
            {'time':'2020-01-03','open':100,'high':110,'low':90,'close':105,'volume':1000},
        ]
        older=[
            {'time':'2019-12-30','open':90,'high':100,'low':80,'close':95,'volume':900},
            {'time':'2019-12-31','open':91,'high':101,'low':81,'close':96,'volume':950},
        ]
        def fake(symbol,frame,to,count,minute=False,retries=3):
            calls.append(to)
            if len(calls)==1:return older
            raise TimeoutError('older page unavailable')
        try:
            m._history_page=fake
            bars=m._full_daily_history('FPT',10,previous)
            self.assertEqual(bars[0]['time'],'2019-12-30')
            self.assertEqual(bars[-1]['time'],'2020-01-03')
            retained_cursor=int(m.datetime.fromisoformat('2020-01-02').replace(tzinfo=m.VN).timestamp())-1
            self.assertEqual(calls[0],retained_cursor)
        finally:
            m._history_page=original

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
        self.assertIn('<option value="1d" selected>Ngày</option>',html)
        self.assertIn('<option value="0" selected>Tất cả</option>',html)
        self.assertIn("nativeTitle.textContent='Biểu đồ FinQuery · '+state.symbol",market)
        self.assertIn("this.tf=$('chart-interval')?.value||'1d'",chart)
        self.assertIn("if(M.intraday(this.tf)&&(!months||months>=12))",chart)

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

    def test_vbma_macro_parser_handles_legacy_delimiters_and_numeric_cells(self):
        raw='Date;PMI;Ghi chú\n2026-08;50,5;Mở rộng\n2026-09;51,2;Tăng\n'.encode('utf-8-sig')
        data=m.parse_vbma_table(raw)
        self.assertEqual(data['columns'],['Date','PMI','Ghi chú'])
        self.assertIn('PMI',data['numericColumns'])
        self.assertAlmostEqual(data['rows'][-1]['PMI'],51.2)
        self.assertEqual(data['rows'][-1]['Ghi chú'],'Tăng')

    def test_vbma_parser_prefers_real_multi_column_header(self):
        raw='Date,Metric,Note\nT1 2026,10,"a;b"\nT2 2026,11,"c;d"\n'.encode('utf-8')
        data=m.parse_vbma_table(raw)
        self.assertEqual(data['columns'],['Date','Metric','Note'])
        self.assertEqual(data['rows'][-1]['Metric'],11)

    def test_vbma_amount_normalization_for_money_supply_and_credit(self):
        money={'columns':['Cột 1','M2 (tỷ VND)','% YoY'],'rows':[{'Cột 1':'T6 2026','M2 (tỷ VND)':'20,414,616','% YoY':4.24}]}
        money=m.normalize_vbma_dataset('money_supply',money)
        self.assertEqual(money['rows'][0]['M2 (tỷ VND)'],20414616)
        self.assertAlmostEqual(money['rows'][0]['% YoY'],4.24)
        credit={'columns':['Cột 1','Nông, lâm, thủy sản','Vận tải, viễn thông'],'rows':[{'Cột 1':'T6 2026','Nông, lâm, thủy sản':'1,225,073','Vận tải, viễn thông':546.391}]}
        credit=m.normalize_vbma_dataset('credit_sector',credit)
        self.assertEqual(credit['rows'][0]['Nông, lâm, thủy sản'],1225073)
        self.assertEqual(credit['rows'][0]['Vận tải, viễn thông'],546391)

    def test_macro_collection_scope_excludes_bond_and_swap_curves(self):
        self.assertEqual(set(m.VBMA_TABLES),{'macro_overview','fdi','gdp_growth','pmi','money_supply','credit_sector'})
        joined=' '.join(slug for slug,_ in m.VBMA_TABLES.values()).lower()
        for forbidden in ('bond','swap','yield_curve','short_term_benchmark'):
            self.assertNotIn(forbidden,joined)

    def test_indicator_picker_signals_macro_gate_and_natural_macro_answers_are_wired(self):
        html=(ROOT/'frontend/index.html').read_text()
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        research=(ROOT/'frontend/research-ai.js').read_text()
        macro=(ROOT/'frontend/macro.js').read_text()
        self.assertIn('normalizeDataset',macro)
        self.assertIn('periodRank',macro)
        self.assertIn("timed.sort((a,b)=>a.rank-b.rank)",macro)
        self.assertIn('indicator-open',html)
        self.assertIn('indicator-search',html)
        self.assertIn('signal-feed',html)
        self.assertIn('macro-access-code',html)
        self.assertIn('ACCESS_HASH',macro)
        self.assertNotIn("ACCESS_HASH='13579'",macro)
        self.assertIn('showWorkspace',macro)
        self.assertIn("workspace.hidden=false",macro)
        self.assertIn("workspace.style.display='block'",macro)
        build=(ROOT/'scripts/build_cdn.py').read_text()
        self.assertIn("(front / 'macro.js').read_text()",build)
        for token in ('MACD cắt lên Signal','RSI thoát vùng quá bán','Supertrend đổi hướng','ADX vượt 25'):
            self.assertIn(token,chart)
        self.assertIn('setInterval(()=>{if(!document.hidden)refresh();},60000)',market)
        self.assertIn("return'macro'",research)
        self.assertIn('macroHTML',research)
        self.assertIn('chưa đủ để coi đó là nguyên nhân',research)

    def test_professional_logo_and_dolphin_ai_shell_are_present(self):
        html=(ROOT/'frontend/index.html').read_text()
        app=(ROOT/'frontend/app.js').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        research=(ROOT/'frontend/research-ai.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('id="company-logo"',html)
        self.assertIn('id="ai-fab"',html)
        self.assertIn('Dolphin AI',html)
        self.assertIn('companiesmarketcap.com/img/company-logos/64/',app)
        self.assertIn('ticker-with-logo',market)
        self.assertIn('openDrawer',research)
        self.assertIn('.indicator-dialog{position:fixed!important;top:76px!important;right:22px!important',css)

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

