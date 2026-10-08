import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]

spec=importlib.util.spec_from_file_location('news_intelligence',ROOT/'scripts/news_intelligence.py')
ni=importlib.util.module_from_spec(spec);spec.loader.exec_module(ni)

plan_spec=importlib.util.spec_from_file_location('refresh_business_plans',ROOT/'scripts/refresh_business_plans.py')
bp=importlib.util.module_from_spec(plan_spec);plan_spec.loader.exec_module(bp)

COMPANIES=[
 {'symbol':'HCM','name':'Công ty Cổ phần Chứng khoán Thành phố Hồ Chí Minh'},
 {'symbol':'VIX','name':'Công ty Cổ phần Chứng khoán VIX'},
 {'symbol':'VND','name':'Công ty Cổ phần Chứng khoán VNDIRECT'},
 {'symbol':'CEO','name':'Công ty Cổ phần Tập đoàn C.E.O'},
 {'symbol':'GAS','name':'Tổng Công ty Khí Việt Nam - CTCP'},
 {'symbol':'FPT','name':'Công ty Cổ phần FPT'},
 {'symbol':'FRT','name':'Công ty Cổ phần Bán lẻ Kỹ thuật số FPT'},
]
ALIASES={'FPT':['Tập đoàn FPT'],'FRT':['FPT Retail'],'VND':['VNDirect'],'VIX':['Chứng khoán VIX'],'HCM':['Chứng khoán HCM','HSC'],'GAS':['PV GAS']}

class NewsIntelligenceTests(unittest.TestCase):
    def symbols(self,title,body=''):
        return [x['symbol'] for x in ni.resolve_company_symbols(COMPANIES,title,body,ALIASES)]

    def test_ambiguous_hcm_city_is_not_hcm_securities(self):
        self.assertNotIn('HCM',self.symbols('Ngân hàng ở TPHCM bơm 5,8 triệu tỷ đồng ra thị trường'))
        self.assertIn('HCM',self.symbols('Chứng khoán HCM báo lãi quý III tăng 25%'))

    def test_ambiguous_vix_index_is_not_vix_securities(self):
        self.assertNotIn('VIX',self.symbols('The VIX Is Calm as Stocks Fall. Should Investors Worry?'))
        self.assertNotIn('VIX',self.symbols('CBOE VIX rises to 18 points as Wall Street falls'))
        self.assertIn('VIX',self.symbols('Chứng khoán VIX báo lợi nhuận quý III tăng mạnh'))

    def test_ambiguous_vnd_currency_is_not_vndirect(self):
        self.assertNotIn('VND',self.symbols('Giá vàng đạt 143,5 triệu VND mỗi lượng'))
        self.assertNotIn('VND',self.symbols('Tỷ giá USD/VND tăng nhẹ'))
        self.assertIn('VND',self.symbols('VNDirect công bố kế hoạch lợi nhuận năm 2026'))

    def test_fpt_retail_does_not_become_fpt(self):
        syms=self.symbols('Chủ tịch FPT Retail Nguyễn Bạch Điệp vào Top 100 phụ nữ quyền lực')
        self.assertIn('FRT',syms)
        self.assertNotIn('FPT',syms)

    def test_gold_idiom_and_bare_usd_are_not_market_topics(self):
        topics,evidence=ni.classify_semantics('Vingroup chọn mặt gửi vàng cho đối tác châu Âu','Dự án trị giá 5,6 tỷ USD',[])
        self.assertNotIn('gold',topics)
        self.assertNotIn('fx',topics)
        self.assertNotIn('gold',evidence)
        self.assertNotIn('fx',evidence)

    def test_true_gold_and_fx_are_detected(self):
        topics,evidence=ni.classify_semantics('Giá vàng SJC tăng khi tỷ giá USD/VND biến động mạnh','',[])
        self.assertIn('gold',topics)
        self.assertIn('fx',topics)

    def test_story_cluster_groups_similar_headlines_and_keeps_lineage(self):
        rows=[
          {'title':'Fed phát tín hiệu còn tăng lãi suất','source':'Reuters','publisher':'Reuters','url':'https://reuters.example/a','publishedAt':'2026-10-08T01:00:00+00:00','symbols':[],'impactTag':'FED','sourcePriority':80,'topics':['rates']},
          {'title':'Fed sees higher rates ahead','source':'Bloomberg','publisher':'Bloomberg','url':'https://bloomberg.example/b','publishedAt':'2026-10-08T01:05:00+00:00','symbols':[],'impactTag':'FED','sourcePriority':80,'topics':['rates']},
        ]
        enriched,stories=ni.cluster_stories(rows,threshold=.10)
        self.assertEqual(len(stories),1)
        self.assertEqual(stories[0]['sourceCount'],2)
        self.assertEqual(len(enriched),2)
        self.assertEqual(enriched[0]['storyId'],enriched[1]['storyId'])

    def test_observed_reaction_uses_first_trade_after_news(self):
        row={'publishedAt':'2026-10-07T02:15:20+00:00','symbols':['FPT']}
        bars=[
          {'time':'2026-10-07T02:16:00+00:00','close':100},
          {'time':'2026-10-07T02:31:00+00:00','close':102},
          {'time':'2026-10-07T03:16:00+00:00','close':101},
          {'time':'2026-10-07T07:45:00+00:00','close':103},
        ]
        r=ni.realized_reaction(row,bars)
        self.assertEqual(r['basePrice'],100)
        self.assertEqual(r['return15mPct'],2.0)
        self.assertEqual(r['return60mPct'],1.0)
        self.assertEqual(r['returnEodPct'],3.0)

    def test_24hmoney_live_parser_keeps_metadata_only(self):
        raw='''<html><body><a href="/news/fpt-ky-hop-dong-ai-c1a123.html">FPT ký hợp đồng AI mới, mở rộng thị trường quốc tế</a><span>5 phút trước</span></body></html>'''
        rows=ni.parse_24hmoney_live(raw,datetime(2026,10,8,2,0,tzinfo=timezone.utc),COMPANIES,ALIASES)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['source'],'24HMoney')
        self.assertIn('FPT',rows[0]['symbols'])
        self.assertEqual(rows[0]['contentType'],'news')
        self.assertLessEqual(len(rows[0]['summary']),1)

    def test_plan_parser_extracts_plan_actual_completion(self):
        raw='''<html><body>FPT Kế hoạch kinh doanh 2026 Doanh thu Kế hoạch 100.000 Thực hiện 50.000 Hoàn thành 50% Lợi nhuận trước thuế Kế hoạch 20.000 Thực hiện 11.000 Hoàn thành 55%</body></html>'''
        rows,status=bp.parse_plan_html(raw,'FPT','https://24hmoney.vn/stock/FPT/ke-hoach-kinh-doanh')
        self.assertEqual(status['status'],'ok')
        revenue=next(x for x in rows if x['metric']=='revenue')
        self.assertEqual(revenue['completionPct'],50.0)

if __name__=='__main__':
    unittest.main()
