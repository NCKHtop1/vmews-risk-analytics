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

    def test_dedupe_priority_official_over_direct_over_discovery(self):
        stamp='2026-10-07T04:48:00+00:00'
        title='Thông tư 53/2026/TT-NHNN quy định quản lý rủi ro AI trong ngân hàng'
        google={'title':title,'url':'https://news.google.com/articles/x','publishedAt':stamp,'sourcePriority':92}
        direct={'title':title,'url':'https://luatvietnam.vn/x-d1.html','publishedAt':stamp,'sourcePriority':94}
        official={'title':title,'url':'https://sbv.gov.vn/x','publishedAt':stamp,'sourcePriority':100}
        self.assertEqual(m._unique_news([google,direct])[0]['url'],direct['url'])
        self.assertEqual(m._unique_news([direct,official])[0]['url'],official['url'])


if __name__=='__main__':
    unittest.main()
