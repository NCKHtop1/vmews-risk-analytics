"""Focused stdlib-only regression tests for FinQuery news ingestion."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('market',ROOT/'scripts/refresh_market.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NewsParserTests(unittest.TestCase):
    def setUp(self):
        self.current=datetime(2026,10,7,7,0,tzinfo=timezone.utc)

    def test_luatvietnam_absolute_and_relative_timestamps(self):
        dt,basis,precision=m._luatvietnam_datetime('6 phút trước',self.current)
        self.assertEqual(dt.isoformat(),'2026-10-07T06:54:00+00:00')
        self.assertEqual((basis,precision),('relative_age','relative'))
        dt,basis,precision=m._luatvietnam_datetime('Ngày cập nhật: Thứ Tư, 07/10/2026 11:48 (GMT+7)',self.current)
        self.assertEqual(dt.isoformat(),'2026-10-07T04:48:00+00:00')
        self.assertEqual((basis,precision),('updated','minute'))

    def test_absolute_timestamp_wins_over_unrelated_relative_widget(self):
        text='5 phút trước · Ngày cập nhật: Thứ Tư, 07/10/2026 11:48 (GMT+7)'
        dt,basis,precision=m._luatvietnam_datetime(text,self.current)
        self.assertEqual(dt.isoformat(),'2026-10-07T04:48:00+00:00')
        self.assertEqual((basis,precision),('updated','minute'))

    def test_old_but_parseable_listing_is_healthy_empty_not_error(self):
        source=next(x for x in m.LUATVIETNAM_DIRECT_SOURCES if x['scope']=='stocks')
        filler='x'*1800
        raw=f'''<html><title>LuatVietnam</title><h1>Chứng khoán</h1>
        <a href="/chung-khoan/van-ban-hop-nhat-12-2026-abc-d1.html">Văn bản hợp nhất 12/VBHN-BTC về thị trường giao dịch cổ phiếu và chứng khoán phái sinh</a>
        {filler}<span>Cập nhật: 17/06/2026</span></html>'''.encode()
        rows,health=m._parse_luatvietnam_listing(raw,source,[],self.current)
        self.assertEqual(rows,[])
        self.assertTrue(health['parserHealthy'])
        self.assertEqual(health['status'],'empty')
        self.assertGreaterEqual(health['datedCandidates'],1)
        self.assertEqual(health['recentDatedCandidates'],0)

    def test_valid_listing_extracts_only_market_relevant_item(self):
        source=next(x for x in m.LUATVIETNAM_DIRECT_SOURCES if x['scope']=='finance')
        raw='''<html><title>LuatVietnam</title><h1>Tài chính-Ngân hàng</h1>
        <a href="/linh-vuc-khac/thong-tu-53-2026-tt-nhnn-449984-d1.html">Thông tư 53/2026/TT-NHNN quy định quản lý rủi ro AI trong ngân hàng</a>
        <span>Cập nhật: 07/10/2026, 11:48</span>
        <a href="/linh-vuc-khac/quyet-dinh-giao-duc-449111-d1.html">Quyết định công bố thủ tục hành chính giáo dục</a>
        <span>Cập nhật: 07/10/2026, 10:30</span></html>'''.encode()
        rows,health=m._parse_luatvietnam_listing(raw,source,[],self.current)
        self.assertTrue(health['parserHealthy'])
        self.assertEqual(health['status'],'ok')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['sourceTier'],'trusted_legal_direct')
        self.assertEqual(rows[0]['sourcePriority'],94)
        self.assertEqual(rows[0]['publishedAt'],'2026-10-07T04:48:00+00:00')
        self.assertIn('sbv',rows[0]['topics'])

    def test_http_200_broken_template_is_error(self):
        source=next(x for x in m.LUATVIETNAM_DIRECT_SOURCES if x['scope']=='stocks')
        raw='<html><title>LuatVietnam</title><h1>Chứng khoán</h1>HTTP 200 template changed</html>'.encode()
        rows,health=m._parse_luatvietnam_listing(raw,source,[],self.current)
        self.assertEqual(rows,[])
        self.assertFalse(health['parserHealthy'])
        self.assertEqual(health['status'],'error')
        self.assertIn('parser contract failed',health['error'])

    def test_direct_group_does_not_claim_unmade_detail_checks(self):
        raw='''<html><title>LuatVietnam</title><h1>Tài chính-Ngân hàng</h1>
        <a href="/linh-vuc-khac/thong-tu-53-2026-tt-nhnn-449984-d1.html">Thông tư 53/2026/TT-NHNN quy định quản lý rủi ro AI trong ngân hàng</a>
        <span>Cập nhật: 07/10/2026, 11:48</span></html>'''.encode()
        original=m.request
        try:
            m.request=lambda url,*args,**kwargs: raw
            rows,sources,group=m._fetch_luatvietnam_direct([],self.current)
        finally:
            m.request=original
        self.assertEqual(len(sources),4)
        self.assertEqual(group['parserHealthy'],4)
        self.assertEqual(group['status'],'ok')
        self.assertEqual(group['detailChecks'],0)
        self.assertEqual(group['detailTimestampVerified'],0)
        self.assertGreaterEqual(group['preciseTimestamps'],1)
        self.assertTrue(rows)

    def test_all_broken_direct_parsers_are_red(self):
        original=m.request
        try:
            m.request=lambda url,*args,**kwargs: b'<html><title>LuatVietnam</title><body>template changed</body></html>'
            rows,sources,group=m._fetch_luatvietnam_direct([],self.current)
        finally:
            m.request=original
        self.assertEqual(rows,[])
        self.assertEqual(group['parserHealthy'],0)
        self.assertEqual(group['status'],'error')
        self.assertTrue(all(x['status']=='error' for x in sources))

    def test_verified_exact_direct_row_beats_invalid_verified_relative_legacy(self):
        title='Thông tư 53/2026/TT-NHNN quy định quản lý rủi ro AI trong ngân hàng'
        legacy={
            'title':title,'url':'https://luatvietnam.vn/x-d1.html',
            'publishedAt':'2026-10-07T07:13:00+00:00','source':'Luật Việt Nam',
            'sourcePriority':94,'directSource':True,'detailTimestampVerified':True,
            'timePrecision':'relative'
        }
        exact={
            'title':title,'url':'https://luatvietnam.vn/x-d1.html',
            'publishedAt':'2026-10-07T04:48:00+00:00','source':'Luật Việt Nam',
            'sourcePriority':94,'directSource':True,'detailTimestampVerified':True,
            'timePrecision':'minute'
        }
        picked=m._unique_news([legacy,exact])
        self.assertEqual(len(picked),1)
        self.assertEqual(picked[0]['publishedAt'],'2026-10-07T04:48:00+00:00')
        self.assertEqual(picked[0]['timePrecision'],'minute')

    def test_retention_rejects_invalid_legacy_direct_timestamp_contract(self):
        current=self.current
        bad={
            'title':'Bad legacy','url':'https://luatvietnam.vn/bad-d1.html',
            'publishedAt':'2026-10-07T06:50:00+00:00','source':'Luật Việt Nam',
            'directSource':True,'detailTimestampVerified':True,'timePrecision':'relative'
        }
        self.assertFalse(m._retain_news_row(bad,current))
        old_relative={**bad,'detailTimestampVerified':False,'publishedAt':'2026-10-06T20:00:00+00:00'}
        self.assertFalse(m._retain_news_row(old_relative,current))
        exact={**bad,'detailTimestampVerified':True,'timePrecision':'minute','publishedAt':'2026-10-07T04:48:00+00:00'}
        self.assertTrue(m._retain_news_row(exact,current))

    def test_dedupe_priority_official_over_direct_over_discovery(self):
        stamp='2026-10-07T04:48:00+00:00'
        title='Thông tư 53/2026/TT-NHNN quy định quản lý rủi ro AI trong ngân hàng'
        google={'title':title,'url':'https://news.google.com/articles/x','publishedAt':stamp,'sourcePriority':92}
        direct={'title':title,'url':'https://luatvietnam.vn/x-d1.html','publishedAt':stamp,'sourcePriority':94}
        official={'title':title,'url':'https://sbv.gov.vn/x','publishedAt':stamp,'sourcePriority':100}
        self.assertEqual(m._unique_news([google,direct])[0]['url'],direct['url'])
        self.assertEqual(m._unique_news([direct,official])[0]['url'],official['url'])


    def test_news_ui_does_not_present_approximate_time_as_exact(self):
        market=(ROOT/'frontend/market.js').read_text()
        self.assertIn("function newsTimeLabel(r)",market)
        self.assertIn("timePrecision==='relative'&&!r?.detailTimestampVerified",market)
        self.assertIn("return'~ '+shortAge(r)+' trước'",market)
        self.assertIn("timePrecision==='day'",market)
        self.assertIn("esc(newsTimeLabel(r))",market)
        self.assertNotIn("esc(date(r.publishedAt))",market)


    def test_sbv_listing_date_is_day_precision_not_fake_clock_time(self):
        raw='''<html><body>
        <a href="/w/thong-cao-ty-gia">Ngân hàng Nhà nước công bố tỷ giá trung tâm mới</a>
        <span>07/10/2026</span>
        </body></html>'''.encode()
        original=m.request
        try:
            m.request=lambda *_args,**_kwargs: raw
            rows,health=m._fetch_sbv_news(self.current)
        finally:
            m.request=original
        self.assertEqual(health['status'],'ok')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['timePrecision'],'day')
        self.assertEqual(rows[0]['timestampBasis'],'listing_date')

    def test_news_workflows_require_healthy_luatvietnam_and_bundle_contract(self):
        root=ROOT.parent
        live=(root/'.github/workflows/market-news-live.yml').read_text()
        guard=(root/'.github/workflows/market-realtime-guard.yml').read_text()
        ci=(root/'.github/workflows/finquery-news-parser-ci.yml').read_text()
        pages=(root/'.github/workflows/pages.yml').read_text()
        bundle=(root/'.github/workflows/finquery-bundle-sync.yml').read_text()
        self.assertIn("int(luat.get('parserHealthy') or 0)<3",live)
        self.assertIn("luat.get('status')!='ok'",live)
        self.assertIn("int(luat.get('parserHealthy') or 0)<3",guard)
        self.assertIn("luat.get('status')!='ok'",guard)
        self.assertIn('Build standalone FinQuery and verify News bundle contract',ci)
        self.assertIn("news-company-latest.json",pages)
        self.assertIn("function newsTimeLabel(r)",pages)
        self.assertIn("build_cdn.py",bundle)

    def test_sbv_omo_is_a_token_not_a_substring(self):
        for text in ('tomorrow rate decision','SOMO crude sales','Moomoo market update'):
            self.assertIsNone(m.TOPIC_PATTERNS['sbv'].search(text),text)
            self.assertIsNone(m.SBV_PATTERN.search(text),text)
        for text in ('NHNN bơm vốn qua OMO','thị trường mở OMO'):
            self.assertIsNotNone(m.TOPIC_PATTERNS['sbv'].search(text),text)
            self.assertIsNotNone(m.SBV_PATTERN.search(text),text)

    def test_global_tomorrow_story_is_not_tagged_sbv(self):
        xml='''<?xml version="1.0"?><rss><channel>
        <item><title>Fed minutes coming tomorrow could give markets important clues about future rate hikes</title>
        <link>https://news.google.com/articles/fed-test</link>
        <pubDate>Tue, 06 Oct 2026 20:38:35 +0000</pubDate>
        <description>Global central bank outlook.</description></item>
        </channel></rss>'''
        url=next(url for name,url in m.FEEDS if name=='Global Central Banks')
        rows=m.parse_feed(xml,'Global Central Banks',url,[],self.current)
        self.assertEqual(len(rows),1)
        self.assertNotIn('sbv',rows[0]['topics'])
        self.assertNotEqual(rows[0].get('impactTag'),'NHNN')

    def test_legal_document_code_dedupe_prefers_direct_over_discovery(self):
        stamp='2026-10-07T04:48:00+00:00'
        google={
            'title':'Thông tư 53/2026/TT-NHNN: Quy định an toàn và quản lý rủi ro AI trong Ngân hàng - LuatVietnam',
            'url':'https://news.google.com/articles/tt53','publishedAt':stamp,
            'source':'LuatVietnam','sourceTier':'trusted_legal','sourcePriority':92
        }
        direct={
            'title':'Thông tư 53/2026/TT-NHNN của Ngân hàng Nhà nước Việt Nam quy định về an toàn, quản lý rủi ro AI',
            'url':'https://luatvietnam.vn/tt53-d1.html','publishedAt':stamp,
            'source':'Luật Việt Nam','sourceTier':'trusted_legal_direct','sourcePriority':94,
            'directSource':True,'timePrecision':'minute','detailTimestampVerified':True
        }
        picked=m._unique_news([google,direct])
        self.assertEqual(len(picked),1)
        self.assertEqual(picked[0]['url'],direct['url'])

    def test_frontend_guards_omo_and_fpt_retail_false_positives(self):
        market=(ROOT/'frontend/market.js').read_text()
        self.assertIn(r"\bomo\b",market)
        self.assertIn("title=title.replace(/\\bfpt\\s+(?:retail|securities)\\b/g,' ')",market)
        self.assertIn("summary=summary.replace(/\\bfpt\\s+(?:retail|securities)\\b/g,' ')",market)


if __name__=='__main__':
    unittest.main()
