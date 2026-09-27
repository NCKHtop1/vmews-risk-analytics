"""Reject corrupt market values, unsafe RSS links and issuer mismatches."""
import importlib.util
import json
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

insight_spec = importlib.util.spec_from_file_location('insight_refresh', ROOT / 'scripts/refresh_insights.py')
im = importlib.util.module_from_spec(insight_spec)
insight_spec.loader.exec_module(im)

event_spec = importlib.util.spec_from_file_location('event_refresh', ROOT / 'scripts/refresh_events.py')
em = importlib.util.module_from_spec(event_spec)
event_spec.loader.exec_module(em)

class MarketTests(unittest.TestCase):
    def test_events_v6_parses_hnx_and_cafef_history(self):
        hnx='<table><tr><td>Trả cổ tức bằng tiền</td><td>13/01/2026</td><td>14/01/2026</td><td>23/01/2026</td></tr><tr><td>Họp Đại hội cổ đông thường niên</td><td>18/03/2026</td><td>19/03/2026</td><td>17/04/2026</td></tr></table>'
        rows=em.hnx_rows(hnx,'QNS','https://hnx.example/QNS','HNX')
        cash=next(x for x in rows if x['type']=='cash_dividend')
        self.assertEqual(cash['date'],'2026-01-13')
        self.assertEqual(cash['details']['recordDate'],'2026-01-14')
        self.assertEqual(cash['details']['payoutDate'],'2026-01-23')
        self.assertEqual(cash['dataQuality'],'official')
        cafe='<div>17/06/2022: Cổ tức bằng Cổ phiếu, tỷ lệ 30% Cổ tức bằng Tiền, tỷ lệ 5% 31/05/2021: Cổ tức bằng Tiền, tỷ lệ 5%</div>'
        rows=em.cafef_rows(cafe,'HPG','https://cafef.example/HPG')
        self.assertTrue(any(x['type']=='stock_dividend' and x['date']=='2022-06-17' for x in rows))
        self.assertTrue(any(x['type']=='cash_dividend' and x['date']=='2022-06-17' for x in rows))
        self.assertTrue(all(x['dataQuality']=='secondary' for x in rows))

    def test_events_v6_dedupes_secondary_when_official_event_exists(self):
        official={'id':'a','symbol':'HPG','type':'cash_dividend','date':'2022-06-17','title':'Official','details':{'recordDate':'2022-06-20','ratio':'5%'},'source':{'publisher':'HOSE','url':'https://example.com/o'},'dataQuality':'official'}
        secondary={'id':'b','symbol':'HPG','type':'cash_dividend','date':'2022-06-17','title':'CafeF','details':{'ratio':'5%'},'source':{'publisher':'CafeF','url':'https://example.com/c'},'dataQuality':'secondary'}
        rows=em.merge_events([official],[],[secondary])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['details']['ratio'],'5%')

    def test_events_v6_has_official_registry_schedule_and_pages_trigger(self):
        sources=json.loads((ROOT/'config/event_sources.json').read_text())
        kinds={x['kind'] for x in sources['sources'] if x.get('enabled')}
        self.assertIn('issuer_template',kinds)
        self.assertIn('cafef_history',kinds)
        self.assertIn('health',kinds)
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        pages=(ROOT.parent/'.github/workflows/pages.yml').read_text() if (ROOT.parent/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        self.assertIn("cron: '17 0-10/2 * * 1-5'",flow)
        self.assertIn('financial-insights-data-publisher',flow)
        self.assertIn('refresh_events.py',flow)
        self.assertIn('event-status.json',flow)
        self.assertIn('Refresh investment insights',pages)
        self.assertIn('ref: financial-insights-data',pages)
        self.assertIn('for f in broker-research.json corporate-events.json insights-status.json event-status.json',pages)
        self.assertNotIn('rsync -a _insight-data/data/ financial-report/data/',pages)
        self.assertIn("'insightData':revision('_insight-data')",pages)

    def test_investment_ideas_v6_dashboard_is_symbol_dynamic(self):
        html=(ROOT/'frontend/index.html').read_text()
        insights=(ROOT/'frontend/insights.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        for needle in ('id="investment-ideas"','id="idea-rating-distribution"','id="idea-target-zone"','id="idea-report-list"','id="idea-event-list"'):
            self.assertIn(needle,html)
        self.assertIn("Investment Ideas · '+(state.symbol||'—')",insights)
        self.assertIn("read('event-status.json').catch(()=>null)",insights)
        self.assertIn('eventSourceHealth',insights)
        self.assertIn('idea-dashboard',css)
        self.assertIn('idea-event-mark.cash_dividend',css)
        self.assertIn('idea-report-item',css)
        bundle=(ROOT/'index.html').read_text()
        self.assertIn('id="investment-ideas"',bundle)
        self.assertIn('eventSourceHealth',bundle)

    def test_hpg_seed_has_cash_stock_dividend_and_multi_broker_research(self):
        events=json.loads((ROOT/'data/corporate-events.json').read_text())
        research=json.loads((ROOT/'data/broker-research.json').read_text())
        hpg=[x for x in events['events'] if x['symbol']=='HPG' and x['date']=='2022-06-17']
        self.assertTrue(any(x['type']=='cash_dividend' and x['details']['cashAmount']=='500 đồng/cp' for x in hpg))
        self.assertTrue(any(x['type']=='stock_dividend' and x['details']['ratio']=='10:3' for x in hpg))
        brokers={x['broker'] for x in research['reports'] if x['symbol']=='HPG'}
        self.assertTrue({'MBS','VIETCAP','SHS','BSC'}.issubset(brokers))

    def test_insight_data_seeds_are_source_linked_and_attributed(self):
        events=json.loads((ROOT/'data/corporate-events.json').read_text())
        research=json.loads((ROOT/'data/broker-research.json').read_text())
        hpg_events=[x for x in events['events'] if x['symbol']=='HPG']
        self.assertTrue(any(x['type']=='stock_dividend' and x['date']=='2026-05-25' and x['details']['recordDate']=='2026-05-26' and x['details']['ratio']=='10%' for x in hpg_events))
        self.assertTrue(any(x['type']=='listing' and x['date']=='2026-07-15' for x in hpg_events))
        self.assertTrue(all(x['source']['url'].startswith('https://') for x in hpg_events))
        latest=next(x for x in research['reports'] if x['id']=='MBS-HPG-2026-09-18')
        self.assertEqual(latest['recommendation'],'KHẢ QUAN')
        self.assertEqual(latest['targetPrice'],32000)
        self.assertTrue(latest['sourceUrl'].startswith('https://www.mbs.com.vn/'))

    def test_mbs_research_parser_extracts_metadata_without_copying_report_body(self):
        listing='<a href="https://www.mbs.com.vn/hpg-bcpt-test/">HPG - BCPT - Giá thép thuận lợi</a><a href="/other/">Tin khác</a>'
        rows=im.discover_mbs_list(listing,{'HPG','FPT'})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['symbol'],'HPG')
        report='<html><body><div>Ngày đăng: 18/09/2026</div><p>Khuyến nghị KHẢ QUAN với giá mục tiêu 32,000 VND/cp.</p><p>Nội dung rất dài không được lưu nguyên văn.</p></body></html>'
        row=im.parse_mbs_report(report,rows[0])
        self.assertEqual(row['publishedAt'],'2026-09-18')
        self.assertEqual(row['recommendation'],'KHẢ QUAN')
        self.assertEqual(row['targetPrice'],32000)
        self.assertNotIn('Nội dung rất dài',row['summary'])
        prior={**row,'summary':'Tóm tắt FinQuery đã biên soạn','highlights':['Điểm đã xác minh']}
        merged=im.merge_reports([prior],[row])
        self.assertEqual(merged[0]['summary'],'Tóm tắt FinQuery đã biên soạn')
        self.assertEqual(merged[0]['highlights'],['Điểm đã xác minh'])

    def test_research_v5_registry_covers_major_brokers_and_vn100(self):
        sources=json.loads((ROOT/'config/research_sources.json').read_text())
        codes={x['code'] for x in sources['sources'] if x.get('enabled')}
        self.assertTrue({'MBS','VIETCAP','FPTS','ACBS','SHS','BSC','VCBS','KBSV','MIRAE','DSC','SSI','YUANTA'}.issubset(codes))
        self.assertGreaterEqual(len(codes),15)
        companies=json.loads((ROOT/'data/companies.json').read_text())
        self.assertEqual(len(companies),100)
        self.assertTrue(all(len(x['symbol'])==3 for x in companies))

    def test_research_v5_parses_vietcap_fpts_acbs_and_generic_bsc(self):
        universe={'HPG','FPT','MWG','VCB'}
        vietcap={'code':'VIETCAP','name':'Vietcap','url':'https://www.vietcap.com.vn/trung-tam-phan-tich','adapter':'vietcap_listing'}
        raw='HPG [BUY +58.6%] - Triển vọng lợi nhuận tích cực - Cập nhật Company Research 11 Sep 2026'
        rows=im.discover_vietcap(raw,vietcap,universe)
        self.assertEqual(rows[0]['symbol'],'HPG')
        self.assertEqual(rows[0]['publishedAt'],'2026-09-11')
        self.assertEqual(rows[0]['recommendation'],'MUA')

        fpts={'code':'FPTS','name':'FPTS','url':'https://ezsearch.fpts.com.vn/Services/EzReport/default.aspx?tabid=169','adapter':'fpts_listing'}
        rows=im.discover_fpts('14/09/2026 MWG Khuyến nghị Bán cổ phiếu MWG ngày 14/09/2026 - FPTS',fpts,universe)
        self.assertEqual(rows[0]['symbol'],'MWG')
        self.assertEqual(rows[0]['publishedAt'],'2026-09-14')

        acbs={'code':'ACBS','name':'ACBS','url':'https://acbs.com.vn/bao-cao','adapter':'acbs_listing'}
        rows=im.discover_acbs('14/09/2026 HPG Khuyến nghị Khả quan Tổng tỷ suất lợi nhuận 16% Giá mục tiêu 32.300 VND',acbs,universe)
        self.assertEqual(rows[0]['symbol'],'HPG')
        self.assertEqual(rows[0]['targetPrice'],32300)
        self.assertEqual(rows[0]['recommendation'],'KHẢ QUAN')

        bsc={'code':'BSC','name':'BSC','url':'https://www.bsc.com.vn/bao-cao-phan-tich','adapter':'generic_anchors'}
        listing='<a href="/bao-cao-phan-tich/chi-tiet-bao-cao/123">X-Alpha | HPG 40,800 +50%: Vua thép thức giấc - báo cáo phân tích</a>'
        seeds=im.discover_generic(listing,bsc,universe)
        self.assertEqual(seeds[0]['symbol'],'HPG')
        detail='<div>Ngày : 14/05/2026</div><p>Duy trì khuyến nghị MUA. Giá trị hợp lý 40,800 VND/CP.</p>'
        row=im.parse_report_page(detail,seeds[0],bsc)
        self.assertEqual(row['publishedAt'],'2026-05-14')
        self.assertEqual(row['recommendation'],'MUA')
        self.assertEqual(row['targetPrice'],40800)

    def test_research_v5_seeds_multiple_brokers_for_hpg(self):
        research=json.loads((ROOT/'data/broker-research.json').read_text())
        brokers={x['broker'] for x in research['reports'] if x['symbol']=='HPG'}
        self.assertTrue({'MBS','VIETCAP','SHS','BSC'}.issubset(brokers))

    def test_research_v5_markers_are_anchored_to_candles_not_bottom_legend(self):
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('priceToCoordinate',chart)
        self.assertIn("anchorPrice=isResearch?Number(bar.high):Number(bar.low)",chart)
        self.assertIn('chart-insight-stem',chart)
        self.assertNotIn("bottom:'+(12+stack*31)",chart)
        self.assertIn('.chart-insight-stem',css)

    def test_research_v5_has_independent_multi_daily_refresh_and_health_status(self):
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        insights=(ROOT/'frontend/insights.js').read_text()
        self.assertIn("cron: '17 0-10/2 * * 1-5'",flow)
        self.assertIn('financial-insights-data-publisher',flow)
        self.assertIn('refresh_insights.py',flow)
        self.assertIn('insights-status.json',flow)
        self.assertIn("read('insights-status.json').catch(()=>null)",insights)
        self.assertIn('sourcesReachable',insights)
        self.assertIn('sourceHealth',insights)
    def test_research_and_event_publishers_are_consolidated(self):
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        manual=(ROOT.parent/'.github/workflows/corporate-events-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/corporate-events-refresh.yml').exists() else pathlib.Path('.github/workflows/corporate-events-refresh.yml').read_text()
        financial=(ROOT.parent/'.github/workflows/financial-report-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/financial-report-refresh.yml').exists() else pathlib.Path('.github/workflows/financial-report-refresh.yml').read_text()
        self.assertIn('name: Refresh investment insights',flow)
        self.assertIn('financial-insights-data',flow)
        self.assertIn('cp financial-report/data/companies.json /tmp/insight-publish/data/companies.json',flow)
        self.assertNotIn('git push origin HEAD:refs/heads/financial-report-data',flow)
        self.assertIn('refresh_insights.py',flow)
        self.assertIn('refresh_events.py',flow)
        self.assertIn('data/broker-research.json',flow)
        self.assertIn('data/corporate-events.json',flow)
        self.assertIn('data/insights-status.json',flow)
        self.assertIn('data/event-status.json',flow)
        self.assertIn('group: financial-insights-data-publisher',flow)
        self.assertIn('name: Manual corporate event refresh',manual)
        self.assertNotIn('schedule:',manual)
        self.assertNotIn('refresh_insights.py',financial)

    def test_events_and_broker_research_are_wired_to_chart_dolphin_and_bundle(self):
        html=(ROOT/'frontend/index.html').read_text()
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        insights=(ROOT/'frontend/insights.js').read_text()
        research=(ROOT/'frontend/research-ai.js').read_text()
        build=(ROOT/'scripts/build_cdn.py').read_text()
        bundle=(ROOT/'index.html').read_text()
        workflow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml')
        flow=workflow.read_text() if workflow.exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        self.assertIn('src="insights.js"',html)
        self.assertIn('id="chart-insight-markers"',html)
        self.assertIn('id="market-insights"',html)
        self.assertIn('id="insight-detail"',html)
        self.assertIn('setInsights(items,onOpen)',chart)
        self.assertIn('timeToCoordinate',chart)
        self.assertIn('priceToCoordinate',chart)
        self.assertIn('target<first||target>last',chart)
        self.assertIn('chart-insight-marker',chart)
        self.assertIn('registerInsights(api)',market)
        self.assertIn("window.FinInsights?.select?.(symbol)",market)
        self.assertIn("window.FinInsights={select,attachChart,context,open,reload:load}",insights)
        self.assertIn('Khuyến nghị và giá mục tiêu là quan điểm của',insights)
        self.assertIn('corporateEvents',research)
        self.assertIn('brokerResearch',research)
        self.assertIn('brokerConsensus',research)
        self.assertIn('khuyến nghị của FinQuery hoặc Dolphin',research)
        self.assertIn("(front / 'insights.js').read_text()",build)
        self.assertIn('refresh_insights.py',flow)
        self.assertIn('--output /tmp/insight-publish/data',flow)
        self.assertIn('brokerResearch',research)
        self.assertIn('chart-insight-markers',bundle)
        self.assertIn('FinInsights',bundle)
        self.assertIn('brokerResearch',bundle)

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
        self.assertIn('summary',rows[0])

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

    def test_kbs_history_normalization_supports_listing_to_present_payload(self):
        payload={'symbol':'FPT','data_day':[
            {'t':'13-12-2006','o':40000,'h':42000,'l':39500,'c':41000,'v':120000},
            {'t':'14-12-2006','o':41000,'h':43000,'l':40500,'c':42500,'v':150000},
        ]}
        bars=m.normalize_kbs_history(payload,'FPT')
        self.assertEqual(len(bars),2)
        self.assertEqual(bars[0]['time'],'2006-12-13')
        self.assertEqual(bars[-1]['close'],42500)
        self.assertEqual(bars[-1]['volume'],150000)

    def test_kbs_history_rejects_wrong_symbol(self):
        with self.assertRaises(ValueError):
            m.normalize_kbs_history({'symbol':'VCB','data_day':[{'t':'01-01-2026','c':10000}]},'FPT')

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

    def test_dolphin_v4_uses_quota_aware_browser_gemini_with_local_fallback(self):
        js=(ROOT/'frontend/research-ai.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('generativelanguage.googleapis.com',js)
        self.assertIn('vmews_solution_ai_browser_session',js)
        self.assertIn("DOLPHIN_VERSION='DOLPHIN_V4'",js)
        self.assertIn("AI_MODE_KEY='finquery_dolphin_mode'",js)
        self.assertIn("mode==='deep'?(full[0]||lite[0]||''):(lite[0]||full[0]||'')",js)
        self.assertIn("if(mode==='deep'){const lite=pickModel('normal'",js)
        self.assertIn('Flash-Lite',js)
        self.assertIn('sessionStorage',js)
        self.assertIn('Google Search',js)
        self.assertNotIn('vmews-risk-analytics-sojd.vercel.app/api/solution-ai',js+html)
        self.assertNotIn('FINQUERY_AI_ENDPOINT',js+html)
        self.assertNotIn('localStorage.setItem(GEMINI_SESSION_KEY',js)
        self.assertNotIn('research-ai-subtitle',html)
        self.assertIn('data-ai-mode="deep"',html)
        self.assertIn('data-ai-mode="normal"',html)
        self.assertIn('grid-template-rows:auto auto auto minmax(0,1fr) auto',css)
        self.assertIn('dolphinPulseV4',css)
        self.assertIn('annualSnapshot',js)
        self.assertIn('quarterSnapshot',js)
        self.assertIn('riskSignals',js)
        self.assertIn('const local=analyze(q)',js)

    def test_company_news_is_strict_and_sector_news_cannot_pose_as_company_news(self):
        market=(ROOT/'frontend/market.js').read_text()
        research=(ROOT/'frontend/research-ai.js').read_text()
        self.assertIn('companyNewsScore',market)
        self.assertIn('strictCompanyNews',market)
        self.assertIn('score>=7',market)
        self.assertIn("MBB:['MBB','MBBANK','MB BANK'",market)
        self.assertIn("const relevant=strictCompanyNews(fresh,state.symbol,1)[0]",market)
        self.assertNotIn("strictCompanyNews(fresh,state.symbol,1)[0]||sectorNews",market)
        self.assertIn('sectorNews:marketNews',market)
        self.assertIn("category:'COMPANY'",research)
        self.assertIn("category:'SECTOR'",research)
        self.assertIn('Không được gọi sectorNews là tin của doanh nghiệp',research)

    def test_chart_quote_consistency_gate_hides_bad_technical_context(self):
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('delta<=.15',chart)
        self.assertIn('chart-data-mismatch',chart)
        self.assertIn('!this.dataConsistent',chart)
        self.assertIn('Dữ liệu giá và biểu đồ đang lệch nhau',chart)
        self.assertIn('.chart-data-mismatch',css)

    def test_production_bundle_matches_dolphin_v4(self):
        bundle=(ROOT/'index.html').read_text()
        source=(ROOT/'frontend/research-ai.js').read_text()
        self.assertIn('DOLPHIN_V4',source)
        self.assertIn('DOLPHIN_V4',bundle)
        self.assertIn('strictCompanyNews',bundle)
        self.assertIn('chart-data-mismatch',bundle)
        self.assertIn('Flash-Lite',bundle)
        self.assertIn('id="ai-backdrop"',bundle)
        self.assertIn('data-market-view="peers"',bundle)
        self.assertIn('data-market-view="sector"',bundle)
        self.assertIn('SECTOR_GROUPS',bundle)
        self.assertNotIn('research-ai-subtitle',bundle)
        self.assertLess(bundle.index('id="research-ai-messages"'),bundle.index('id="research-ai-form"'))

    def test_dolphin_is_centered_modal_with_backdrop_and_simple_mode_copy(self):
        html=(ROOT/'frontend/index.html').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        js=(ROOT/'frontend/research-ai.js').read_text()
        self.assertIn('id="ai-backdrop"',html)
        self.assertIn('ai-modal',html)
        self.assertIn('aria-modal="true"',html)
        self.assertIn('.ai-backdrop{position:fixed;inset:0',css)
        self.assertIn('backdrop-filter:blur(8px)',css)
        self.assertIn('left:50%!important;top:50%!important',css)
        self.assertIn('translate(-50%,-50%)',css)
        self.assertIn("$('ai-backdrop')?.addEventListener('click',closeDrawer)",js)
        self.assertIn('Nhanh & tiết kiệm<small>Flash-Lite</small>',js)
        self.assertIn('Phân tích sâu<small>Flash</small>',js)
        self.assertNotIn('dùng nhiều quota hơn',js+html)

    def test_market_has_real_price_peer_and_sector_comparison_tabs(self):
        html=(ROOT/'frontend/index.html').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('data-market-view="price"',html)
        self.assertIn('data-market-view="peers"',html)
        self.assertIn('data-market-view="sector"',html)
        self.assertIn('So sánh cổ phiếu ngành',html)
        self.assertIn('So sánh với ngành',html)
        self.assertIn('SECTOR_GROUPS',market)
        self.assertIn("MBB','MSB','OCB'",market)
        self.assertIn("get('history/'+encodeURIComponent(symbol)+'.json')",market)
        self.assertIn('normalizedPerformance',market)
        self.assertIn('bình quân equal-weight',market)
        self.assertIn('renderCompareSvg',market)
        self.assertIn('setMarketView',market)
        self.assertIn('.market-view-tabs',css)
        self.assertIn('.market-compare-panel',css)
        self.assertIn('đây không phải dữ liệu dòng tiền mua/bán',html)

    def test_pages_merges_research_seed_and_redeploys_after_research_refresh(self):
        pages=(ROOT.parent/'.github/workflows/pages.yml').read_text() if (ROOT.parent/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        merge=(ROOT/'scripts/merge_insight_data.py').read_text()
        self.assertIn('Refresh investment insights',pages)
        self.assertIn('merge_insight_data.py --seed-dir /tmp/main-insight-seed --target-dir financial-report/data',pages)
        self.assertIn("CURATED=('summary','highlights','catalysts','risks')",merge)
        self.assertIn('merge_reports',merge)
        self.assertIn('merge_events',merge)

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
        kb=(ROOT/'frontend/knowledge-base.js').read_text()
        self.assertIn('movementNarrative',js)
        self.assertIn('financialNarrative',js)
        self.assertIn('conceptHTML',js)
        self.assertIn('dynamicMetricHit',js)
        self.assertIn('memoHTML',js)
        self.assertIn('supportCase',js)
        self.assertIn('counterCase',js)
        for concept in ('ROE','ROA','ROIC','FCF','OCF','Biên lợi nhuận gộp','MACD','RSI','OMO','Lãi suất qua đêm liên ngân hàng','Vòng quay tổng tài sản','EV/EBITDA','NIM','Nợ xấu / NPL','Sharpe ratio'):
            self.assertIn(concept,kb)
        self.assertIn('conceptDiagnosis',js)
        self.assertIn('K.search',js)
        self.assertIn("return'concept'",js)
        self.assertIn("return'memo'",js)
        build=(ROOT/'scripts/build_cdn.py').read_text()
        self.assertIn("(front / 'knowledge-base.js').read_text()",build)

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
        for forbidden in ('chưa đủ để coi đó là nguyên nhân','không tự khẳng định quan hệ nhân quả','không coi việc xuất hiện cùng ngày là bằng chứng nhân quả','Chưa có lực hỗ trợ nổi bật','Chưa xuất hiện điểm suy yếu','Chưa đủ dữ liệu'):
            self.assertNotIn(forbidden,research+market)

    def test_professional_logo_and_dolphin_ai_shell_are_present(self):
        html=(ROOT/'frontend/index.html').read_text()
        app=(ROOT/'frontend/app.js').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        research=(ROOT/'frontend/research-ai.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('id="company-logo"',html)
        self.assertIn('id="ai-fab"',html)
        self.assertIn('Dolphin AI',html)
        self.assertIn('class="dolphin-logo"',html)
        self.assertIn('class="finquery-logo"',html)
        self.assertIn('storage.googleapis.com/cdn-entrade/company/',app)
        self.assertIn('cdn.simplize.vn/simplizevn/logo/',app)
        self.assertIn('companiesmarketcap.com/img/company-logos/64/',app)
        self.assertIn('data-logo-alt2',market)
        self.assertIn('placeholderLogo',app)
        self.assertIn('ticker-with-logo',market)
        self.assertIn('data-logo-placeholder',market)
        self.assertIn('openDrawer',research)
        self.assertIn('.indicator-dialog{position:fixed!important;top:76px!important;right:22px!important',css)

    def test_market_board_exposes_reference_price_and_absolute_change(self):
        html=(ROOT/'frontend/index.html').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        self.assertIn('<th>Tham chiếu</th>',html)
        self.assertIn('q.price-q.reference',market)
        self.assertIn("fmt(q?.reference)",market)
        self.assertNotIn('driver-causality',market)

    def test_technical_signal_language_is_explicit_and_contextual(self):
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        for token in ('mean-reversion','Khối lượng ','Supertrend ','MACD vừa chuyển sang phía trên Signal','Thiết lập kỹ thuật nghiêng tăng','technicalContext()'):
            self.assertIn(token,chart)
        self.assertNotIn('Nên đối chiếu RSI và khối lượng trước khi kết luận',chart)

    def test_full_history_workflow_uses_low_load_listing_backfill(self):
        workflow=(ROOT.parent/'.github/workflows/financial-market-refresh.yml')
        text=workflow.read_text() if workflow.exists() else pathlib.Path('.github/workflows/financial-market-refresh.yml').read_text()
        script=(ROOT/'scripts/refresh_market.py').read_text()
        self.assertIn("'12000'",text)
        self.assertIn("HISTORY_PAGE_SIZE",text)
        self.assertIn("'1000'",text)
        self.assertIn("HISTORY_RETRIES: '3'",text)
        self.assertIn("HISTORY_KBS_FULL",text)
        self.assertIn("HISTORY_START_DATE: '1998-01-01'",text)
        self.assertNotIn('pip install -q vnstock',text)
        self.assertIn("os.environ.get('HISTORY_PAGE_SIZE'",script)
        self.assertIn("os.environ.get('HISTORY_RETRIES'",script)
        self.assertIn("_kbs_full_history",script)
        self.assertIn("KBS_API",script)

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

