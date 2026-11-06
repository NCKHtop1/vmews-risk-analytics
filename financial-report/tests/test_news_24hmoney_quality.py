"""Regression for stale SSR vs hydrated 24HMoney Live and isolated News health."""
import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('refresh_market', ROOT/'scripts/refresh_market.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ni=m.ni
NOW=datetime(2026,11,6,4,0,tzinfo=timezone.utc)
COMPANIES=[{'symbol':'FPT','name':'Cong ty Co phan FPT'}]


def page(days):
    cards=[]
    for i,stamp in enumerate(days):
        cards.append(
            '<div><span>'+stamp+'</span><a href="/news/fpt-bai-viet-'+str(i)+'.html">'
            'FPT công bố kết quả kinh doanh và doanh thu quý III - số '+str(i)+
            '</a></div>'
        )
    return ('<html><body>'+''.join(cards)+'</body></html>').encode()


class HmLiveQualityTests(unittest.TestCase):
    def audit(self,raw):
        return ni.audit_24hmoney_live_listing(raw,NOW)

    def test_twenty_stale_ssr_links_are_degraded_not_parser_mismatch(self):
        raw=page(['28/10/2026']*20)
        a=self.audit(raw)
        self.assertEqual((a['eligibleUnique'],a['datedUnique'],a['recentUnique'],a['staleUnique']),
                         (20,20,0,20))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,0),('degraded','SOURCE_SSR_STALE'))
        self.assertEqual(ni.parse_24hmoney_live(raw,NOW,COMPANIES),[])

    def test_one_current_nineteen_stale_is_not_false_green(self):
        raw=page(['06/11/2026']+['28/10/2026']*19)
        a=self.audit(raw)
        self.assertEqual((a['recentUnique'],a['staleUnique'],a['freshShareOfDated']),(1,19,.05))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,1),('degraded','SOURCE_SSR_PARTIAL'))

    def test_hydrated_distribution_is_not_false_degradation(self):
        raw=page(['06/11/2026']*21+['28/10/2026']*20)
        a=self.audit(raw)
        self.assertEqual((a['datedUnique'],a['recentUnique'],a['staleUnique']),(41,21,20))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,6),('ok','CURRENT_HTTP_LISTING'))

    def test_current_only_nonfinancial_is_healthy_empty(self):
        raw=('<a href="/news/khach-san-trang-nhat.html">Khách sạn '
             'lâu đời nhất Hà Nội qua ảnh tư liệu</a>'
             '<span>06/11/2026</span>').encode()
        a=self.audit(raw)
        self.assertEqual((a['eligibleUnique'],a['recentUnique']),(1,1))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,0),('empty','FINANCIAL_FILTERED'))

    def test_undated_markup_is_degraded_not_no_news(self):
        raw=page(['Không có ngày']*5)
        a=self.audit(raw)
        self.assertEqual((a['eligibleUnique'],a['undatedUnique']),(5,5))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,0),('degraded','SOURCE_TIMESTAMP_UNAVAILABLE'))

    def test_no_article_listing_is_explicitly_empty(self):
        a=self.audit('<html><p>Chưa co tin moi</p></html>'.encode())
        self.assertEqual(ni.classify_24hmoney_live_listing(a,0),('empty','NO_LISTING_ARTICLES'))

    def test_future_time_never_counts_as_fresh(self):
        a=self.audit(page(['09/11/2026']*3))
        self.assertEqual((a['futureUnique'],a['recentUnique']),(3,0))
        self.assertEqual(ni.classify_24hmoney_live_listing(a,0),('degraded','SOURCE_TIMESTAMP_UNAVAILABLE'))

    def test_dedup_and_reject_foreign_hosts(self):
        url='/news/fpt-ky-ket-hop-dong-ai.html'
        title='FPT công bố kết quả kinh doanh quý III năm 2026'
        raw=(
            f'<span>06/11/2026</span><a href="{url}?a=1">{title}</a>'
            f'<span>06/11/2026</span><a href="{url}?a=2">{title}</a>'
            f'<span>06/11/2026</span><a href="https://attacker.example/news/any">{title}</a>'
            f'<span>06/11/2026</span><a href="https://fake24hmoney.vn/news/any">{title}</a>'
        ).encode()
        a=self.audit(raw)
        self.assertEqual((a['eligibleUnique'],a['recentUnique']),(1,1))

    def test_fetch_stale_ssr_returns_degraded_no_detail_requests(self):
        raw=page(['28/10/2026']*20)
        calls=[]
        def requester(url,**kwargs):
            calls.append(url)
            return raw
        with patch.object(m,'request',side_effect=requester):
            rows,health=m._fetch_24hmoney_live(COMPANIES,NOW)
        self.assertEqual(rows,[])
        self.assertEqual(health['status'],'degraded')
        self.assertEqual(health['statusReason'],'SOURCE_SSR_STALE')
        self.assertEqual(health['detailTimestampAttempted'],0)
        self.assertEqual(calls,[m.MONEY24_LIVE_URL])
        self.assertTrue(health['qualityChecked'])

    def test_fetch_one_recent_article_still_degraded(self):
        raw=page(['06/11/2026']+['28/10/2026']*19)
        detail=b'<meta property="article:published_time" content="2026-11-06T10:30:00+07:00">'
        with patch.object(m,'request',side_effect=lambda u,**kwargs:raw if u==m.MONEY24_LIVE_URL else detail):
            rows,health=m._fetch_24hmoney_live(COMPANIES,NOW)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['detailTimestampVerified'])
        self.assertEqual((health['status'],health['statusReason']),('degraded','SOURCE_SSR_PARTIAL'))
        self.assertEqual((health['recentUnique'],health['staleUnique']),(1,19))

    def test_transport_failure_is_source_error_not_a_fake_success(self):
        with patch.object(m,'request',side_effect=TimeoutError('remote timeout')):
            rows,health=m._fetch_24hmoney_live(COMPANIES,NOW)
        self.assertEqual(rows,[])
        self.assertEqual(health['status'],'error')
        self.assertEqual(health['statusReason'],'TRANSPORT_OR_PARSE_FAILURE')
        self.assertFalse(health['qualityChecked'])

    def test_news_healthy_providers_not_counted_twice(self):
        self.assertEqual(ni.news_provider_group({'name':'CafeF'}),'CafeF')
        self.assertEqual(ni.news_provider_group({'name':'LuatVietnam Direct · Chứng khoán'}),'LuatVietnam')
        self.assertEqual(ni.news_provider_group({'name':'24HMoney Live'}),'24HMoney')
        self.assertEqual(ni.news_provider_group({'name':'24HMoney Symbol'}),'24HMoney')
        self.assertEqual(ni.news_provider_group({'name':'Vietnam Policy Watch'}),'Google News Discovery')
        self.assertEqual(ni.news_provider_group({'name':'Global Markets'}),'Google News Discovery')
        fixtures=[{'name':x,'status':'ok'} for x in
                  ('CafeF','CafeF','LuatVietnam Direct · Chứng khoán',
                   'LuatVietnam Direct · Văn bản mới','24HMoney Symbol','24HMoney Live')]
        unique={ni.news_provider_group(x) for x in fixtures}
        self.assertEqual(len(fixtures),6)
        self.assertEqual(len(unique),3)

    def test_independent_workflows_keep_total_news_freshness_gates(self):
        base=ROOT.parent
        live=(base/'.github/workflows/market-news-live.yml').read_text()
        guard=(base/'.github/workflows/market-realtime-guard.yml').read_text()
        for code in (live,guard):
            self.assertIn("live24.get('qualityChecked') is not True",code)
            self.assertIn("fresh*4<dated",code)
            self.assertIn("('degraded','error')",code)
            self.assertIn("symbol24.get('status')=='error'",code)
            self.assertIn("'healthyProviderCount') or 0)<3",code)
            self.assertIn('24HMoney Symbol isolated low reachability',code)
        self.assertIn("'healthy') or 0)<3",live)
        self.assertIn("'healthy') or 0)<3",guard)


if __name__=='__main__':
    unittest.main()
