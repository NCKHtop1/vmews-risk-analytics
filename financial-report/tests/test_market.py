"""Reject corrupt market values, unsafe RSS links and issuer mismatches."""
import importlib.util
import json
import os
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

esg_spec = importlib.util.spec_from_file_location('esg_refresh', ROOT / 'scripts/refresh_esg.py')
esm = importlib.util.module_from_spec(esg_spec)
esg_spec.loader.exec_module(esm)

class MarketTests(unittest.TestCase):
    def test_corporate_esg_registry_covers_vn100_banks_and_external_providers(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        required={'ACB','BID','CTG','EIB','HDB','LPB','MBB','MSB','NAB','OCB','SHB','SSB','STB','TCB','TPB','VCB','VIB','VPB'}
        self.assertTrue(required.issubset(set(cfg['banks'])))
        self.assertTrue(all(cfg['banks'][s]['seed_urls'] for s in required))
        self.assertGreaterEqual(cfg['version'],10)
        self.assertTrue(any('EN_ESG_Report_2024.pdf' in u for u in cfg['banks']['HDB']['seed_urls']))
        self.assertTrue(any('static2.vietstock.vn' in u for u in cfg['banks']['VIB']['seed_urls']))
        self.assertEqual(next(x for x in cfg['banks']['HDB']['validated_metrics'] if x['metricId']=='training_hours')['value'],914910)
        self.assertEqual(next(x for x in cfg['banks']['HDB']['validated_metrics'] if x['metricId']=='women_workforce_pct')['value'],63)
        self.assertEqual(next(x for x in cfg['banks']['VIB']['validated_metrics'] if x['metricId']=='training_hours')['value'],417556)
        self.assertEqual(next(x for x in cfg['banks']['VIB']['validated_metrics'] if x['metricId']=='women_workforce_pct')['value'],54)
        self.assertTrue(any('20250620_HDBANK_AR-2024_190326_EN.pdf' in u for u in cfg['banks']['HDB']['seed_urls']))
        self.assertTrue(any('Annual%2Breport%2B2024%2BENG%2B-%2Bscan.pdf' in u for u in cfg['banks']['VIB']['seed_urls']))
        training_rule=next(x for x in cfg['metric_rules'] if x['id']=='training_hours')
        self.assertIn('hours of training',training_rule['aliases'])
        self.assertTrue(any('ENESGReport2024' in u for u in cfg['banks']['HDB']['seed_urls']))
        self.assertEqual(cfg['banks']['STB']['reprocess_version'],1)
        self.assertEqual(cfg['banks']['VIB']['reprocess_version'],1)
        women_rule=next(x for x in cfg['metric_rules'] if x['id']=='women_workforce_pct')
        self.assertIn('nhân sự là nữ',women_rule['aliases'])
        self.assertTrue(any('2025.11.03%2BTPBank' in u for u in cfg['banks']['TPB']['seed_urls']))
        self.assertTrue(any('Bao%2Bcao%2Bthuong%2Bnien%2B2024%2BVN.pdf' in u for u in cfg['banks']['VIB']['seed_urls']))
        self.assertTrue(any('20260127_esg-namabank-2024_vn_view.pdf' in u for u in cfg['banks']['NAB']['seed_urls']))
        self.assertEqual(cfg['banks']['HDB']['type_overrides'][next(u for u in cfg['banks']['HDB']['seed_urls'] if 'HDBankESGReport2024' in u)],'sustainability_report')
        self.assertEqual(cfg['banks']['LPB']['type_overrides']['https://lpbank.com.vn/api/content-file/public/file/view/5bb2a4bb-a070-415a-8eea-54b36c848de6'],'annual_report')
        self.assertTrue(any('B%C3%A1o%2Bc%C3%A1o%2BPTBV%2BBIDV%2B2025_F.pdf' in u for u in cfg['banks']['BID']['seed_urls']))
        self.assertTrue(any('Annual%20Report%202025_%20CBTT.pdf' in u for u in cfg['banks']['SSB']['seed_urls']))
        self.assertTrue(any('20260318---nab---bao-cao-thuong-nien-nam-2025.pdf' in u for u in cfg['banks']['NAB']['seed_urls']))
        self.assertTrue(any('HDBankESGReport2024' in u for u in cfg['banks']['HDB']['seed_urls']))
        self.assertEqual(cfg['banks']['MSB']['year_overrides']['https://www.msb.com.vn/ve-chung-toi/phat-trien-ben-vung/'],2025)
        self.assertEqual(cfg['banks']['SHB']['year_overrides']['https://www.shb.com.vn/wp-content/uploads/2026/04/260420_SHB_BCTN_2025_Web.pdf'],2025)
        self.assertEqual(cfg['banks']['TCB']['year_overrides']['https://techcombank.com/content/dam/techcombank/public-site/documents/bao-cao-phat-trien-ben-vung-2026-eng-15052026.pdf'],2025)
        self.assertTrue(any('260420_SHB_BCTN_2025_Web.pdf' in u for u in cfg['banks']['SHB']['seed_urls']))
        self.assertTrue(any('bao-cao-thuong-nien-2025.pdf' in u for u in cfg['banks']['STB']['seed_urls']))
        self.assertTrue(cfg['banks']['VPB']['year_url_templates'])
        self.assertTrue(cfg['banks']['CTG']['year_url_templates'])
        self.assertTrue(cfg['banks']['VCB']['year_url_templates'])
        self.assertIn('acb-bao-cao-phat-trien-ben-vung',' '.join(cfg['banks']['ACB']['seed_urls']))
        providers={x['provider'] for x in cfg['external_sources']}
        self.assertTrue({'WWF SUSBA','HOSE VNSI','VIS Rating','Morningstar Sustainalytics','S&P Global Ratings'}.issubset(providers))
        self.assertGreaterEqual(len(cfg['metric_rules']),15)
        self.assertTrue(any(x['type']=='ESG Credit Impact Score' for x in cfg['rating_patterns']))
        registry=esm.build_company_registry(cfg)
        core=json.loads((ROOT/'data/companies.json').read_text())
        self.assertEqual(len(registry),100)
        self.assertEqual(set(registry),{x['symbol'] for x in core})
        self.assertEqual(sum(x['entityType']=='bank' for x in registry.values()),18)
        self.assertIn('https://24hmoney.vn/stock/fpt/report',registry['FPT']['seed_urls'])
        self.assertFalse(any('/financial-report' in u for u in registry['FPT']['seed_urls']))
        self.assertIn('https://24hmoney.vn/stock/acb/report',registry['ACB']['seed_urls'])
        self.assertIn('acb.com.vn',' '.join(registry['ACB']['seed_urls']))

    def test_corporate_esg_prunes_plain_financial_statement_noise(self):
        quarterly={
            'title':'FPT Báo cáo tài chính hợp nhất Quý 2/2026',
            'url':'https://cdn.example/fpt-q2-2026.pdf',
            'sourcePage':'https://24hmoney.vn/stock/fpt/financial-report',
            'type':'esg_other',
        }
        annual_financial={
            'title':'FPT Báo cáo tài chính thường niên năm 2025',
            'url':'https://cdn.example/fpt-financial-2025.pdf',
            'sourcePage':'https://24hmoney.vn/stock/fpt/financial-report',
            'type':'annual_report',
        }
        annual_report={
            'title':'FPT Báo cáo thường niên năm 2025',
            'url':'https://cdn.example/fpt-annual-report-2025.pdf',
            'sourcePage':'https://24hmoney.vn/report/annual',
            'type':'annual_report',
        }
        listing={
            'title':'FPT: Sự kiện liên quan',
            'url':'https://24hmoney.vn/stock/fpt/report',
            'sourcePage':'https://24hmoney.vn/stock/fpt/report',
            'type':'annual_report',
        }
        sustainability={
            'title':'VNM Báo cáo phát triển bền vững 2025',
            'url':'https://cdn.example/vnm-esg-2025.pdf',
            'sourcePage':'https://24hmoney.vn/stock/vnm/report',
            'type':'sustainability_report',
        }
        self.assertFalse(esm.esg_document_candidate(quarterly))
        self.assertFalse(esm.esg_document_candidate(annual_financial))
        self.assertFalse(esm.esg_document_candidate(listing))
        self.assertTrue(esm.esg_document_candidate(annual_report))
        self.assertTrue(esm.esg_document_candidate(sustainability))
        self.assertEqual(esm.classify_document('FPT Báo cáo tài chính thường niên năm 2025'),'esg_other')
        self.assertEqual(esm.classify_document('FPT Báo cáo thường niên năm 2025'),'annual_report')

    def test_corporate_esg_discovery_follows_generic_download_redirects(self):
        seed='https://bank.example/reports'
        detail='https://bank.example/report-2025'
        download='https://cdn.example/download?id=123'
        final='https://cdn.example/report-2025.pdf'
        pages={
            seed:(b'<a href="/report-2025">Sustainability Report 2025</a>','text/html',seed),
            detail:(b'<html><body>Sustainability Report 2025 <a href="https://cdn.example/download?id=123">here</a></body></html>','text/html',detail),
            download:(b'%PDF-1.7 fake','application/pdf',final),
        }
        original=esm.fetch
        try:
            esm.fetch=lambda url,timeout=25: pages[url]
            docs,status=esm.discover_seed(seed,['sustainability','report'])
        finally:
            esm.fetch=original
        self.assertEqual(status['status'],'ok')
        pdf=next(x for x in docs if x['url']==final)
        self.assertEqual(pdf['year'],2025)
        self.assertEqual(pdf['type'],'sustainability_report')

    def test_corporate_esg_extracts_scaled_training_hours(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='ACB năm 2025 cung cấp hơn 1,05 triệu giờ đào tạo cho nhân viên.'
        rows=esm.extract_metrics(text,cfg['metric_rules'],2025,'https://acb.example/report','ACB ESG 2025','sustainability_report')
        row=next(x for x in rows if x['metricId']=='training_hours')
        self.assertEqual(row['value'],1050000)
        self.assertEqual(row['unit'],'hours')

    def test_corporate_esg_html_entities_are_unescaped_before_extraction(self):
        raw='''<p>cung cấp hơn 1,05 triệu giờ đ&agrave;o tạo cho nh&acirc;n vi&ecirc;n; ủng hộ 4 tỷ đồng cho cộng đồng.</p>'''.encode()
        text=esm.strip_html(raw)
        self.assertIn('đào tạo',text)
        self.assertIn('nhân viên',text)

    def test_corporate_esg_green_credit_prefers_outstanding_over_product_package(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='''BIDV triển khai gói tín dụng xanh 10.000 tỷ đồng. Quy mô tín dụng xanh qua các năm: 2025 Dư nợ tín dụng xanh đạt 82.332 tỷ đồng, tỷ lệ 3,5%.'''
        rows=esm.extract_metrics(text,cfg['metric_rules'],2025,'https://bank/report.pdf','BIDV PTBV 2025','sustainability_report')
        row=next(x for x in rows if x['metricId']=='green_credit')
        repaired=esm.repair_canonical_row(row)
        self.assertEqual(repaired['value'],82332)

    def test_corporate_esg_semantics_distinguish_totals_from_intensity_and_subtotals(self):
        rows=[
            {'metricId':'electricity','year':2024,'value':330942,'rawValue':'330,942','unit':'kWh','qualityScore':100,'confidence':'high','sourceType':'sustainability_report','snippet':'As of December 31, 2024, the total electricity consumption across the bank was 7 ,330,942 kWh.'},
            {'metricId':'electricity','year':2025,'value':1385.7,'rawValue':'1,385.7','unit':'kWh','qualityScore':103,'confidence':'high','sourceType':'annual_report','snippet':'In 2025, electricity consumption per employee reached 1,385.7 kWh/employee.'},
            {'metricId':'water','year':2025,'value':7.5,'rawValue':'7,5','unit':'m3','qualityScore':100,'confidence':'high','sourceType':'annual_report','snippet':'Water consumption per employee in 2025: ~7,5 m3/employee.'},
            {'metricId':'ghg_total','year':2025,'value':4957,'rawValue':'4,957','unit':'tCO2e','qualityScore':101,'confidence':'high','sourceType':'sustainability_report','snippet':'Direct emissions (scope 1): 716 tCO2e. Indirect emissions (scope 2): 4,957 tCO2e.'},
            {'metricId':'training_hours','year':2025,'value':600,'rawValue':'600','unit':'hours','qualityScore':116,'confidence':'high','sourceType':'sustainability_report','snippet':'Training: organized 30 service-quality classes in 9 regions. A total of 600 training hours were delivered.'},
            {'metricId':'scope1','year':2025,'value':624,'rawValue':'624','unit':'tCO2e','qualityScore':107,'confidence':'high','sourceType':'annual_report','snippet':'Direct emissions (Scope 1): 624 tCO2eq for SeABank.'},
        ]
        canonical={x['metricId']:x for x in esm.canonical_metrics(rows)}
        self.assertEqual(canonical['electricity']['value'],7330942)
        self.assertNotIn('water',canonical)
        self.assertNotIn('ghg_total',canonical)
        self.assertNotIn('training_hours',canonical)
        self.assertEqual(canonical['scope1']['value'],624)

    def test_corporate_esg_repairs_bidv_total_csr_and_infographic_workforce(self):
        bid={'metricId':'csr_spend','year':2025,'value':95,'rawValue':'95','unit':'billion VND','qualityScore':103,'confidence':'high','sourceType':'sustainability_report','snippet':'CON SỐ VÀNG AN SINH XÃ HỘI 2025 DẤU ẤN VÌ CỘNG ĐỒNG 500+ tỷ đồng 95 tỷ đồng 8 tỷ đồng.'}
        mbb_women={'metricId':'women_workforce_pct','year':2025,'value':2.5,'rawValue':'2,5','unit':'%','qualityScore':70,'confidence':'medium','sourceType':'annual_report','snippet':'Tỷ lệ nữ giới Mạng lưới Dự án HiGreen 2,5% so với năm 2024 620 1.696 61% trong lực lượng CBNV (tính riêng MB).'}
        mbb_training={'metricId':'training_hours_per_employee','year':2025,'value':70.73,'rawValue':'70,73','unit':'hours','qualityScore':105,'confidence':'high','sourceType':'annual_report','snippet':'Số giờ đào tạo trung bình mỗi năm (Đơn vị tính: giờ/người/năm) 70,73 giờ 82,91 giờ 17%.'}
        self.assertEqual(esm.repair_canonical_row(bid)['value'],500)
        self.assertEqual(esm.repair_canonical_row(mbb_women)['value'],61)
        self.assertEqual(esm.repair_canonical_row(mbb_training)['value'],82.91)

    def test_corporate_esg_type_override_and_targeted_reprocess_are_one_time(self):
        url='https://bank.example/report'
        cfg={'year_overrides':{url:2024},'type_overrides':{url:'sustainability_report'},'reprocess_version':2,'reprocess_urls':[url]}
        old={'url':url,'year':2025,'type':'esg_other','processedAt':'2026-01-01T00:00:00+00:00','contentHash':'x','textLength':1,'reprocessVersion':1}
        row=esm.corrected_document_year(old,cfg)
        self.assertEqual(row['year'],2024)
        self.assertEqual(row['type'],'sustainability_report')
        self.assertNotIn('processedAt',row)
        self.assertEqual(row['reprocessVersion'],2)
        row['processedAt']='2026-01-02T00:00:00+00:00'
        same=esm.corrected_document_year(row,cfg)
        self.assertIn('processedAt',same)

    def test_corporate_esg_final_canonical_prefers_outstanding_and_bankwide_training(self):
        rows=[
            {'metricId':'green_credit','year':2025,'value':10000,'rawValue':'10.000','unit':'billion VND','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'Sản phẩm tiên phong: gói tín dụng xanh 10.000 tỷ đồng, trái phiếu ESG.'},
            {'metricId':'green_credit','year':2025,'value':82332,'rawValue':'82.332','unit':'billion VND','qualityScore':106,'confidence':'high','sourceType':'sustainability_report','snippet':'Tỷ lệ dư nợ tín dụng xanh/Tổng dư nợ: 3,5%. Dư nợ tín dụng xanh 82.332 tỷ đồng.'},
            {'metricId':'training_hours','year':2025,'value':1050000,'rawValue':'1,05 triệu','unit':'hours','qualityScore':116,'confidence':'high','sourceType':'sustainability_report','snippet':'Năm 2025, ngân hàng cung cấp hơn 1,05 triệu giờ đào tạo cho nhân viên.'},
        ]
        canonical={(x['metricId'],x['year']):x for x in esm.canonical_metrics(rows)}
        self.assertEqual(canonical[('green_credit',2025)]['value'],82332)
        self.assertEqual(canonical[('training_hours',2025)]['value'],1050000)

    def test_corporate_esg_repairs_mbb_csr_and_nearest_workforce_percentage(self):
        csr={'metricId':'csr_spend','year':2025,'value':1696,'rawValue':'1.696','unit':'billion VND','qualityScore':103,'confidence':'high','sourceType':'annual_report','snippet':'Năm 2025, MB đã triển khai 137 chương trình an sinh xã hội với tổng kinh phí hơn 620 tỷ đồng. Đồng thời, thông qua Nền tảng Thiện nguyện, MB cùng các đối tác và cộng đồng đã huy động 1.696 tỷ đồng.'}
        women={'metricId':'women_workforce_pct','year':2025,'value':2.5,'rawValue':'2,5','unit':'%','qualityScore':70,'confidence':'medium','sourceType':'annual_report','snippet':'Tỷ lệ nữ giới Mạng lưới Dự án HiGreen 2,5% so với năm 2024 620 1.696 61% trong lực lượng CBNV (tính riêng MB).'}
        self.assertEqual(esm.repair_canonical_row(csr)['value'],620)
        self.assertEqual(esm.repair_canonical_row(women)['value'],61)

    def test_corporate_esg_repairs_tpb_bankwide_training_table(self):
        row={'metricId':'training_hours','year':2024,'value':905,'rawValue':'905','unit':'hours','qualityScore':95,'confidence':'medium','sourceType':'sustainability_report','snippet':'Số giờ đào tạo 295.905 Giờ Tổng số CBNV 7.880 Người. Số giờ đào tạo bình quân 37,55 giờ/người.'}
        repaired=esm.repair_canonical_row(row)
        self.assertEqual(repaired['value'],295905)
        self.assertTrue(esm.metric_row_valid(repaired))

    def test_corporate_esg_revives_aes_pdf_failures(self):
        failed={'url':'https://bank/report.pdf','lastError':'cryptography>=3.1 is required for AES algorithm','retryAfter':'2099-01-01T00:00:00+00:00','failedAttempts':1}
        revived=esm.revive_transport_failure(failed)
        self.assertNotIn('retryAfter',revived)
        self.assertNotIn('lastError',revived)

    def test_corporate_esg_metric_and_rating_extraction_preserves_native_scale_and_provenance(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='''VPBank Sustainable Development Report 2024. Green credit VND 21,943 billion. Training hours in 2024 1,681,691. Female employees 58.6%. Moody’s ESG Credit Impact Score remained CIS-2. VPBank continued in VNSI and was assessed under WWF Sustainable Banking Assessment (SUSBA).'''
        metrics=esm.extract_metrics(text,cfg['metric_rules'],2024,'https://example.com/vpb.pdf','VPBank ESG 2024')
        ids={x['metricId'] for x in metrics}
        self.assertIn('green_credit',ids)
        self.assertIn('training_hours',ids)
        self.assertIn('women_workforce_pct',ids)
        metric_by_id={x['metricId']:x for x in metrics}
        self.assertEqual(metric_by_id['training_hours']['value'],1681691)
        self.assertAlmostEqual(metric_by_id['women_workforce_pct']['value'],58.6)
        self.assertEqual(metric_by_id['green_credit']['unit'],'billion VND')
        self.assertTrue(all(x['sourceUrl']=='https://example.com/vpb.pdf' for x in metrics))
        ratings=esm.extract_ratings(text,cfg['rating_patterns'],2024,'https://example.com/vpb.pdf','VPBank ESG 2024')
        self.assertTrue(any(x['provider']=="Moody's" and x['value']=='CIS-2' for x in ratings))
        self.assertTrue(any(x['provider']=='HOSE' for x in ratings))
        self.assertTrue(any(x['provider']=='WWF' for x in ratings))

    def test_corporate_esg_document_discovery_helpers_are_year_and_type_aware(self):
        self.assertEqual(esm.extract_year('Sustainability Report 2025 published 2026'),2025)
        self.assertEqual(esm.classify_document('Báo cáo phát triển bền vững 2025'),'sustainability_report')
        self.assertEqual(esm.classify_document('Green Bond Framework Second Party Opinion'),'sustainable_finance_assessment')
        self.assertTrue(esm.relevant('Báo cáo thường niên 2025',['annual report','báo cáo thường niên']))
        self.assertEqual(len(esm.doc_key('https://example.com/a.pdf')),20)

    def test_corporate_esg_v2_rejects_percentage_and_page_number_false_positives(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='''Sustainability Report 2025. Green credit exposure increased by nearly 15% compared with 2024 and reached VND 18.7 trillion. Scope 1 and Scope 2 emissions are reported in the appendix on page 31-32. Water consumption was reduced by 30-50%. Paper consumption target was reduced by 20%. A total of 866,193 training hours were recorded, while technology programs represented 15% of training time.'''
        metrics=esm.extract_metrics(text,cfg['metric_rules'],2025,'https://example.com/tcb.pdf','TCB Sustainability 2025','sustainability_report')
        by_id={x['metricId']:x for x in metrics}
        self.assertEqual(by_id['green_credit']['value'],18700)
        self.assertEqual(by_id['green_credit']['unit'],'billion VND')
        self.assertEqual(by_id['training_hours']['value'],866193)
        self.assertNotIn('scope1',by_id)
        self.assertNotIn('scope2',by_id)
        self.assertNotIn('water',by_id)
        self.assertNotIn('paper',by_id)

    def test_corporate_esg_v2_normalizes_vietnamese_thousands_and_total_emissions(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='''Báo cáo phát triển bền vững 2025. Tổng phát thải khí nhà kính 3.218.052 tCO2e. Dư nợ tín dụng xanh đạt 71.000 tỷ đồng. Hơn 14 tỷ đồng dành cho hoạt động cộng đồng.'''
        metrics=esm.extract_metrics(text,cfg['metric_rules'],2025,'https://example.com/report.pdf','ESG 2025','sustainability_report')
        by_id={x['metricId']:x for x in metrics}
        self.assertEqual(by_id['green_credit']['value'],71000)
        self.assertEqual(by_id['green_credit']['unit'],'billion VND')
        self.assertEqual(by_id['ghg_total']['value'],3218052)
        self.assertEqual(by_id['ghg_total']['unit'],'tCO2e')

    def test_corporate_esg_v2_infers_reporting_year_from_document_content(self):
        self.assertEqual(esm.infer_report_year('Published 15 May 2026. Sustainability Report 2025. Environment chapter.',2026),2025)
        self.assertEqual(esm.infer_report_year('Báo cáo phát triển bền vững năm 2024 được công bố tháng 4/2025',2025),2024)
        self.assertTrue(esm.metric_document_allowed({'type':'sustainability_report','url':'https://bank/report.pdf'}))
        self.assertFalse(esm.metric_document_allowed({'type':'esg_web_content','url':'https://bank/tin-tuc/giai-thuong-esg'}))

    def test_corporate_esg_v2_canonical_metric_prefers_stronger_report_source(self):
        rows=[
            {'metricId':'green_credit','year':2025,'value':15000,'rawValue':'15.000','unit':'billion VND','qualityScore':90,'confidence':'medium','sourceType':'esg_web_content','snippet':'Dư nợ tín dụng xanh đạt 15.000 tỷ đồng.'},
            {'metricId':'green_credit','year':2025,'value':18700,'rawValue':'18.700','unit':'billion VND','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'Tổng dư nợ tín dụng xanh đạt 18.700 tỷ đồng.'},
        ]
        canonical=esm.canonical_metrics(rows)
        self.assertEqual(len(canonical),1)
        self.assertEqual(canonical[0]['value'],18700)
        self.assertEqual(esm.EXTRACTOR_VERSION,2)

    def test_corporate_esg_canonical_repairs_vcb_multivalue_snippets(self):
        rows=[
            {'metricId':'green_credit','year':2024,'value':2000,'rawValue':'2.000','unit':'billion VND','qualityScore':68,'confidence':'medium','sourceType':'sustainability_report','snippet':'Tổng dư nợ tín dụng xanh của Vietcombank tăng trưởng trung bình hơn 4 lần qua các năm, từ hơn 11.765 tỷ VND năm 2020 lên đến ~47.600 tỷ VND tại thời điểm 31/12/2024. Phát hành thành công 2.000 tỷ đồng trái phiếu xanh.'},
            {'metricId':'women_workforce_pct','year':2025,'value':81,'rawValue':'81','unit':'%','qualityScore':98,'confidence':'medium','sourceType':'sustainability_report','snippet':'Về cơ cấu lao động: Cơ cấu theo giới tính: 60% nhân sự là nữ, 40% là nam. Cơ cấu theo cấp bậc: 19% cán bộ thuộc nhóm lãnh đạo quản lý, trong khi 81% là chuyên viên. Trong đó, tỷ lệ nữ trong đội ngũ lãnh đạo chiếm 54%.'},
            {'metricId':'csr_spend','year':2024,'value':2311,'rawValue':'2.311','unit':'billion VND','qualityScore':76,'confidence':'medium','sourceType':'sustainability_report','snippet':'S5. Đóng góp cho cộng đồng. Trong giai đoạn 2020 - 2024, số tiền dành cho hoạt động an sinh xã hội của Vietcombank là hơn 2.311 tỷ đồng (riêng trong năm 2024 là 571 tỷ đồng).'},
            {'metricId':'training_hours_per_employee','year':2025,'value':49.64,'rawValue':'49,64','unit':'hours','qualityScore':112,'confidence':'high','sourceType':'sustainability_report','snippet':'Số giờ đào tạo trung bình trên một cán bộ năm 2025 là 48,96 giờ/năm. Trong đó, số giờ đào tạo trung bình trên một cán bộ quản lý là 49,64 giờ/năm/người.'},
        ]
        canonical={x['metricId']:x for x in esm.canonical_metrics(rows)}
        self.assertEqual(canonical['green_credit']['value'],47600)
        self.assertEqual(canonical['women_workforce_pct']['value'],60)
        self.assertEqual(canonical['csr_spend']['value'],571)
        self.assertAlmostEqual(canonical['training_hours_per_employee']['value'],48.96)

    def test_corporate_esg_canonical_rejects_gri_codes_and_non_csr_money(self):
        rows=[
            {'metricId':'training_hours','year':2025,'value':4041,'rawValue':'404.1.','unit':'hours','qualityScore':109,'confidence':'high','sourceType':'annual_report','snippet':'GRI 404: ĐÀO TẠO VÀ GIÁO DỤC 2016 404.1. Số giờ đào tạo trung bình hằng năm của mỗi nhân viên (trang 255).'},
            {'metricId':'csr_spend','year':2025,'value':30000,'rawValue':'30.000','unit':'billion VND','qualityScore':86,'confidence':'medium','sourceType':'annual_report','snippet':'VietinBank đã ban hành gói tín dụng ưu đãi quy mô đến 30.000 tỷ đồng dành cho chủ đầu tư và người mua nhà. Gói tài chính xanh Green UP 5.000 tỷ đồng.'},
            {'metricId':'women_workforce_pct','year':2025,'value':25,'rawValue':'25','unit':'%','qualityScore':82,'confidence':'medium','sourceType':'annual_report','snippet':'Tỷ lệ nữ giới trong các cấp quản lý, lãnh đạo và CBNV: 57 ,25 % cán bộ quản lý là nữ giới; 61,4% nhân viên là nữ giới.'},
        ]
        canonical={x['metricId']:x for x in esm.canonical_metrics(rows)}
        self.assertNotIn('training_hours',canonical)
        self.assertNotIn('csr_spend',canonical)
        self.assertAlmostEqual(canonical['women_workforce_pct']['value'],61.4)

    def test_corporate_esg_latency_is_bounded_and_report_label_wins(self):
        self.assertLessEqual(esm.DISCOVERY_TIMEOUT,8)
        self.assertLessEqual(esm.DETAIL_TIMEOUT,6)
        self.assertLessEqual(esm.DOCUMENT_TIMEOUT,22)
        self.assertLessEqual(esm.DOCS_PER_RUN,24)
        self.assertLessEqual(esm.HISTORY_DOCS_PER_RUN,10)
        self.assertLessEqual(esm.MAX_PDF_PAGES,280)
        self.assertLessEqual(esm.MAX_TEXT_CHARS,900000)
        self.assertEqual(esm.parse_number('19.321','m3'),19321)
        mixed='Sustainability Report 2025. Green Bond Framework and Annual Report references.'
        self.assertEqual(esm.classify_document(mixed),'sustainability_report')
        self.assertEqual(esm.classify_document('FPT Báo cáo tài chính thường niên năm 2025'),'esg_other')

    def test_corporate_esg_bootstrap_prioritizes_bank_reports_over_external_archives(self):
        report={'type':'sustainability_report','year':2025,'url':'https://bank/report.pdf'}
        annual={'type':'annual_report','year':2025,'url':'https://bank/annual.pdf'}
        external={'type':'sustainability_report','year':2026,'url':'https://provider/project'}
        self.assertGreater(esm.backlog_priority('TCB',report),esm.backlog_priority('__external__',external))
        self.assertGreater(esm.backlog_priority('ACB',annual),esm.backlog_priority('__external__',external))

    def test_corporate_esg_recent_fast_path_separates_old_history(self):
        self.assertEqual(esm.backlog_bucket('TCB',{'type':'sustainability_report','year':2025,'url':'https://bank/2025.pdf'},2026),'recent')
        self.assertEqual(esm.backlog_bucket('OCB',{'type':'annual_report','year':2021,'url':'https://bank/2021.pdf'},2026),'history')
        self.assertEqual(esm.backlog_bucket('MSB',{'type':'esg_web_content','year':2026,'url':'https://bank/tin-tuc/esg'},2026),'skip')
        self.assertEqual(esm.backlog_bucket('__external__',{'type':'susba','year':None,'url':'https://provider/report'},2026),'recent')

    def test_corporate_esg_tcb_pdf_layout_is_repaired_canonically(self):
        rows=[
            {'metricId':'green_credit','year':2025,'value':1.87e-8,'rawValue':'18.7','unit':'billion VND','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'In 2025, Techcombank green credit exposure reached nearly 15% compared with 2024 Trillion VND18.7 Green credit exposure 2024 (VND billion) 4,463 Green credit exposure 2025 (VND billion) 10,535.'},
            {'metricId':'sustainable_finance','year':2025,'value':500,'rawValue':'500','unit':'billion VND','qualityScore':98,'confidence':'medium','sourceType':'sustainability_report','snippet':'In 2025, Techcombank continued to advance sustainable finance through the new issuance of VND 500 billion Green Bond, reinforcing its commitment.'},
        ]
        canonical={x['metricId']:x for x in esm.canonical_metrics(rows)}
        self.assertEqual(canonical['green_credit']['value'],18700)
        self.assertEqual(canonical['green_credit']['unit'],'billion VND')
        self.assertEqual(canonical['sustainable_finance']['value'],500)
        self.assertTrue(canonical['sustainable_finance']['repaired'])

    def test_corporate_esg_vnsi_reference_is_not_membership(self):
        reference={'provider':'HOSE','assessmentType':'VNSI membership','year':2024,'value':'VNSI','snippet':'Báo cáo tham chiếu các khung GRI, UN SDGs, VNSI và quy định pháp luật.'}
        actual={'provider':'HOSE','assessmentType':'VNSI membership','year':2025,'value':'VNSI','sourceUrl':'https://bank/report-2025.pdf','sourceTitle':'Báo cáo phát triển bền vững 2025','snippet':'Năm thứ 5 liên tiếp VietinBank nằm trong Top 20 VNSI.'}
        continued={'provider':'HOSE','assessmentType':'VNSI membership','year':2025,'value':'VNSI','sourceUrl':'https://bank/milestones','sourceTitle':'Milestones','snippet':'VPBank continued in VNSI in 2025.'}
        unknown_year={'provider':'HOSE','assessmentType':'VNSI membership','year':None,'value':'VNSI','sourceUrl':'https://bank/detail','sourceTitle':'VietinBank lần đầu ra mắt Báo cáo phát triển bền vững','snippet':'Giải thưởng tín dụng xanh 2024 - Năm thứ 4 liên tiếp VietinBank nằm trong TOP 20 VNSI.'}
        cleaned=esm.sanitize_external_assessments([reference,actual,continued,unknown_year])
        self.assertFalse(any(x.get('snippet')==reference['snippet'] for x in cleaned))
        rows_2025=[x for x in cleaned if x.get('year')==2025]
        self.assertEqual(len(rows_2025),1)
        self.assertEqual(rows_2025[0]['sourceUrl'],'https://bank/report-2025.pdf')
        self.assertEqual(rows_2025[0]['evidenceCount'],2)
        row_2024=next(x for x in cleaned if x.get('year')==2024)
        self.assertTrue(row_2024.get('yearInferred'))
        self.assertEqual(esm.infer_vnsi_year(row_2024['snippet']),2024)

    def test_corporate_esg_normalizes_unsafe_urls_and_revives_transport_failures(self):
        raw='https://media.eximbank.com.vn/exim/files/EXIMBANK BCTN 2025 TV 3.pdf'
        normalized=esm.normalize_url(raw)
        self.assertIn('EXIMBANK%20BCTN%202025%20TV%203.pdf',normalized)
        self.assertEqual(esm.normalize_url(normalized),normalized)
        failed={'url':raw,'lastError':"URL can't contain control characters. '/exim/files/EXIMBANK BCTN 2025 TV 3.pdf'",'retryAfter':'2099-01-01T00:00:00+00:00','failedAttempts':2}
        revived=esm.revive_transport_failure(failed)
        self.assertNotIn('retryAfter',revived)
        legacy_big={'url':'https://bank/report.pdf','lastError':'document too large > 36700160 bytes','retryAfter':'2099-01-01T00:00:00+00:00'}
        revived_big=esm.revive_transport_failure(legacy_big)
        if esm.HISTORY_BACKFILL:
            self.assertNotIn('retryAfter',revived_big)
            self.assertGreaterEqual(esm.MAX_DOC_BYTES,90*1024*1024)
        else:
            self.assertIn('retryAfter',revived_big)
            self.assertLessEqual(esm.MAX_DOC_BYTES,35*1024*1024)

    def test_corporate_esg_precision_rejects_systemwide_and_non_csr_money(self):
        rows=[
            {'metricId':'green_credit','year':2023,'value':528300,'rawValue':'528.300','unit':'billion VND','qualityScore':100,'confidence':'high','sourceType':'annual_report','snippet':'Đến 30/6/2023, dư nợ cấp tín dụng xanh tại Việt Nam đạt gần 528.300 tỷ đồng, chiếm 4,2% tổng dư nợ toàn nền kinh tế.'},
            {'metricId':'csr_spend','year':2025,'value':300,'rawValue':'300','unit':'billion VND','qualityScore':100,'confidence':'high','sourceType':'annual_report','snippet':'Nhiều bằng khen cho hoạt động cộng đồng. Eximbank AMC có vốn thực góp 300 tỷ đồng. Lợi nhuận trước thuế năm 2025 đạt 14,5 tỷ đồng.'},
            {'metricId':'board_independence_pct','year':2025,'value':0,'rawValue':'0.00','unit':'%','qualityScore':105,'confidence':'high','sourceType':'annual_report','snippet':'Chủ tịch HĐQT - Thành viên độc lập HĐQT 0 0.00% tỷ lệ sở hữu.'},
            {'metricId':'csr_spend','year':2024,'value':30,'rawValue':'30','unit':'billion VND','qualityScore':100,'confidence':'high','sourceType':'annual_report','snippet':'Trong năm 2024, OCB đã dành gần 30 tỷ đồng cho các hoạt động cộng đồng, thể hiện cam kết trách nhiệm xã hội.'},
        ]
        canonical=esm.canonical_metrics(rows)
        self.assertEqual(len(canonical),1)
        self.assertEqual(canonical[0]['metricId'],'csr_spend')
        self.assertEqual(canonical[0]['value'],30)

    def test_corporate_esg_repairs_female_management_without_eating_digits(self):
        row={'metricId':'women_management_pct','year':2023,'value':55.5,'rawValue':'55,5','unit':'%','qualityScore':107,'confidence':'high','sourceType':'annual_report','snippet':'Tỷ lệ quản lý trên tổng số CBNV là 18% Nam quản lý chiếm 55,5% Nữ quản lý chiếm 45,5%.'}
        repaired=esm.repair_canonical_row(row)
        self.assertEqual(repaired['value'],45.5)
        self.assertTrue(repaired['repaired'])

    def test_corporate_esg_repairs_vpbank_training_highlights(self):
        total={'metricId':'training_hours','year':2025,'value':1,'rawValue':'1','unit':'hours','qualityScore':90,'confidence':'high','sourceType':'sustainability_report','snippet':'Tổng số giờ đào tạo trong năm 2025: 1.496.226 giờ. Tổng số khóa học 3.872.'}
        avg={'metricId':'training_hours_per_employee','year':2025,'value':5,'rawValue':'5','unit':'hours','qualityScore':90,'confidence':'high','sourceType':'sustainability_report','snippet':'Các chỉ số nổi bật ~ 87,5 giờ học/CBNV trong năm 2025.'}
        total_r=esm.repair_canonical_row(total)
        avg_r=esm.repair_canonical_row(avg)
        self.assertEqual(total_r['value'],1496226)
        self.assertEqual(avg_r['value'],87.5)

    def test_corporate_esg_report_year_prefers_explicit_title_and_overrides(self):
        self.assertEqual(esm.explicit_report_year_hint('Báo cáo thường niên năm 2024'),2024)
        self.assertEqual(esm.explicit_report_year_hint('260420_SHB_BCTN_2025_Web.pdf'),2025)
        self.assertEqual(esm.infer_report_year('Older Annual Report 2016 appears in history.',2016,'Báo cáo thường niên năm 2024'),2024)
        cfg={'year_overrides':{'https://bank/page':2025}}
        corrected=esm.corrected_document_year({'url':'https://bank/page','title':'Phát triển bền vững','year':2026},cfg)
        self.assertEqual(corrected['year'],2025)
        aligned=esm.align_rows_to_document_year([{'sourceUrl':'https://bank/page','year':2026,'metricId':'green_credit'}],[corrected])
        self.assertEqual(aligned[0]['year'],2025)

    def test_corporate_esg_final_semantic_audit_cases(self):
        shb={'metricId':'csr_spend','year':2025,'value':256,'rawValue':'256','unit':'billion VND','qualityScore':89,'confidence':'medium','sourceType':'annual_report','snippet':'Nguồn lực lũy kế dành cho các hoạt động an sinh xã hội giai đoạn 2019 – 2025 đã vượt mốc 1.000 tỷ đồng. Riêng trong năm 2025, SHB dành ngân sách hơn 256 tỷ đồng cho các hoạt động an sinh xã hội.'}
        msb={'metricId':'csr_spend','year':2025,'value':14,'rawValue':'14','unit':'billion VND','qualityScore':107,'confidence':'high','sourceType':'sustainability_report','snippet':'13.602 TỶ ĐỒNG phân bố cho các bên liên quan. 14 tỷ đồng CỘNG ĐỒNG 0,10% CỔ ĐÔNG 6.818 tỷ đồng (50%) TÀI TRỢ, HỖ TRỢ CỘNG ĐỒNG - 40% HOẠT ĐỘNG XÃ HỘI TỪ THIỆN - 60% 2.365 tỷ đồng CÁN BỘ NHÂN VIÊN 17%.'}
        vcb_tax={'metricId':'csr_spend','year':2025,'value':15000,'rawValue':'15.000','unit':'billion VND','qualityScore':95,'confidence':'high','sourceType':'sustainability_report','snippet':'Ngân hàng triển khai các chương trình an sinh xã hội, hỗ trợ cộng đồng yếu thế. Đóng góp cho Ngân sách Nhà nước đạt khoảng 15.000 tỷ đồng.'}
        ocb={'metricId':'women_management_pct','year':2023,'value':55.5,'rawValue':'55,5','unit':'%','qualityScore':107,'confidence':'high','sourceType':'annual_report','snippet':'Tỷ lệ quản lý trên tổng số CBNV của OCB là 18% Nam quản lý chiếm 55,5% Nữ quản lý chiếm 45,5%.'}
        self.assertEqual(esm.repair_canonical_row(shb)['value'],256)
        self.assertEqual(esm.repair_canonical_row(msb)['value'],14)
        self.assertFalse(esm.metric_row_valid(esm.repair_canonical_row(vcb_tax)))
        self.assertEqual(esm.repair_canonical_row(ocb)['value'],45.5)

    def test_corporate_esg_final_round3_semantic_repairs(self):
        tpb={'metricId':'green_credit','year':2024,'value':680000,'rawValue':'680.000','unit':'billion VND','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'Tính tới cuối năm 2024, dư nợ tín dụng xanh của cả nước khoảng 680.000 tỷ đồng, chiếm hơn 4,3% tổng dư nợ toàn nền kinh tế. Đóng góp vào kết quả này, tính đến ngày 31/12/2024, TPBank đã cấp tín dụng xanh cho 158 khách hàng, với tổng dư nợ vay và đầu tư TPDN đạt 7.371 tỷ đồng.'}
        nab_avg={'metricId':'training_hours_per_employee','year':2025,'value':372367,'rawValue':'372.367','unit':'hours','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'70,94 giờ/CBNV 372.367 giờ Số giờ đào tạo trung bình cho từng nhân viên Tổng thời lượng đào tạo thực tế tăng cao so với năm 2024.'}
        nab_total={'metricId':'training_hours','year':2025,'value':70.94,'rawValue':'70,94','unit':'hours','qualityScore':108,'confidence':'high','sourceType':'sustainability_report','snippet':'70,94 giờ/CBNV 372.367 giờ Số giờ đào tạo trung bình cho từng nhân viên Tổng thời lượng đào tạo thực tế tăng cao so với năm 2024.'}
        water={'metricId':'water','year':2024,'value':203025,'rawValue':'203.025','unit':'m3','qualityScore':107,'confidence':'high','sourceType':'sustainability_report','snippet':'Số liệu về tiêu thụ nước 2024 2023 Đơn vị tính Lượng nước tiêu thụ 203.379 203.025 m3 Hiệu suất sử dụng nước bình quân theo đầu người 25,81 25,57 m3/nhân sự.'}
        paper={'metricId':'paper','year':2024,'value':391680,'rawValue':'391,68','unit':'kg','qualityScore':107,'confidence':'high','sourceType':'sustainability_report','snippet':'Số liệu về sử dụng giấy 2024 2023 Đơn vị tính Lượng giấy tiêu thụ 406,19 391,68 Tấn Hiệu suất sử dụng giấy bình quân theo đầu người 0,052 0,049 Tấn/nhân sự.'}
        hdb={'metricId':'sustainable_finance','year':2024,'value':3,'rawValue':'3','unit':'billion VND','qualityScore':90,'confidence':'medium','sourceType':'annual_report','snippet':'HDBank successfully issued VND 3 trillion in domestic green bonds under the Sustainable Finance Framework, compliant with ICMA and LMA standards.'}
        self.assertEqual(esm.repair_canonical_row(tpb)['value'],7371)
        self.assertEqual(esm.repair_canonical_row(nab_avg)['value'],70.94)
        self.assertEqual(esm.repair_canonical_row(nab_total)['value'],372367)
        self.assertEqual(esm.repair_canonical_row(water)['value'],203379)
        self.assertEqual(esm.repair_canonical_row(paper)['value'],406190)
        self.assertEqual(esm.repair_canonical_row(hdb)['value'],3000)
        self.assertTrue(esm.metric_row_valid(esm.repair_canonical_row(tpb)))
        bad_avg=dict(nab_avg); bad_avg['snippet']='372.367 giờ/CBNV'
        self.assertFalse(esm.metric_row_valid(bad_avg))

    def test_corporate_esg_vib_hours_of_training_alias(self):
        cfg=json.loads((ROOT/'config/esg_sources.json').read_text())
        text='In 2024, employees completed 1,854 training courses, totaling 417,556 hours of training.'
        rows=esm.extract_metrics(text,cfg['metric_rules'],2024,'https://vib.example/ar.pdf','VIB Annual Report 2024','annual_report')
        training=next(x for x in rows if x['metricId']=='training_hours')
        self.assertEqual(training['value'],417556)

    def test_corporate_esg_rejects_microscopic_green_credit_false_positive(self):
        row={
            'metricId':'green_credit','year':2023,'value':1.2e-9,'rawValue':'1.2',
            'unit':'billion VND','qualityScore':101,'confidence':'high',
            'sourceType':'annual_report',
            'snippet':'PIONEERING THE PROVISION OF GREEN CREDIT PRODUCTS VND VND billion GRI 203-2'
        }
        self.assertFalse(esm.metric_row_valid(row))

    def test_corporate_esg_validated_fallback_only_fills_missing_keys(self):
        live=[
            {'metricId':'training_hours','year':2024,'value':999999,'unit':'hours','sourceUrl':'https://live.example/report.pdf'}
        ]
        cfg={'validated_metrics':[
            {'metricId':'training_hours','year':2024,'value':417556,'unit':'hours','sourceUrl':'https://official.example/ar.pdf'},
            {'metricId':'women_workforce_pct','year':2024,'value':54,'unit':'%','sourceUrl':'https://official.example/ar.pdf'}
        ]}
        filled=esm.fill_validated_metrics(live,cfg)
        by_key={(x['metricId'],x['year']):x for x in filled}
        self.assertEqual(by_key[('training_hours',2024)]['value'],999999)
        self.assertFalse(by_key[('training_hours',2024)].get('validatedFallback',False))
        self.assertEqual(by_key[('women_workforce_pct',2024)]['value'],54)
        self.assertTrue(by_key[('women_workforce_pct',2024)]['validatedFallback'])

        ratings=[{'provider':'HOSE VNSI','assessmentType':'VNSI score','year':2024,'value':'82%'}]
        rcfg={'validated_assessments':[
            {'provider':'HOSE VNSI','assessmentType':'VNSI score','year':2024,'value':'81%'},
            {'provider':'Moody\'s','assessmentType':'ESG Credit Impact Score','year':2024,'value':'CIS-2'}
        ]}
        filled_r=esm.fill_validated_assessments(ratings,rcfg)
        keys={(x['provider'],x['assessmentType'],x['year']):x for x in filled_r}
        self.assertEqual(keys[('HOSE VNSI','VNSI score',2024)]['value'],'82%')
        self.assertEqual(keys[("Moody's",'ESG Credit Impact Score',2024)]['value'],'CIS-2')
        self.assertTrue(keys[("Moody's",'ESG Credit Impact Score',2024)]['validatedFallback'])

    def test_corporate_esg_workflow_is_scheduled_and_bounded(self):
        flow=(ROOT.parent/'.github/workflows/financial-market-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/financial-market-refresh.yml').exists() else pathlib.Path('.github/workflows/financial-market-refresh.yml').read_text()
        macro=(ROOT.parent/'.github/workflows/market-macro-live.yml').read_text() if (ROOT.parent/'.github/workflows/market-macro-live.yml').exists() else pathlib.Path('.github/workflows/market-macro-live.yml').read_text()
        self.assertIn('options: [all, prices, news, macro, esg, esg-history, history, intraday]',flow)
        self.assertIn("cron: '47 14 * * 1-5'",flow)
        self.assertIn("cron: '47 2 * * 6'",flow)
        self.assertNotIn("cron: '15 1 * * 1-5'",flow)
        self.assertNotIn("mode=macro-watchdog",flow)
        self.assertIn("cron: '15 1 * * 1-5'",macro)
        self.assertIn("cron: '42 1-4 * * 1-5'",macro)
        self.assertIn('group: market-macro-live',macro)
        self.assertIn("python -u financial-report/scripts/refresh_market.py --output /tmp/market-macro/market --mode macro",macro)
        self.assertIn("git -C /tmp/market-macro add --sparse market/macro.json",macro)
        self.assertIn('pypdf==5.1.0',flow)
        self.assertIn('cryptography>=45,<47',flow)
        self.assertIn('PyMuPDF>=1.25,<1.27',flow)
        self.assertIn('refresh_esg.py',flow)
        self.assertIn("mode=esg",flow)
        self.assertIn("mode=esg-history",flow)
        self.assertIn("ESG_HISTORY_BACKFILL=1",flow)
        self.assertIn("[esg-refresh]",flow)
        self.assertIn("github.event.schedule == '47 14 * * 1-5'",flow)
        self.assertIn('git rebase FETCH_HEAD',flow)
        self.assertIn('Market data branch advanced during this run',flow)
        esg=(ROOT/'scripts/refresh_esg.py').read_text()
        self.assertIn('probe_years = 5 if HISTORY_BACKFILL else 3',esg)
        self.assertIn('selected.extend(historical_backlog[:remaining])',esg)
        self.assertIn("'company-esg.json','esg-status.json'",flow)
        pages=(ROOT.parent/'.github/workflows/pages.yml').read_text() if (ROOT.parent/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        self.assertIn('rsync -a _market-data/market/ _site/financial-report/market/',pages)

    def test_events_v6_parses_hnx_and_cafef_history(self):
        hnx='<table><tr><td>Trả cổ tức bằng tiền</td><td>13/01/2026</td><td>14/01/2026</td><td>23/01/2026</td></tr><tr><td>Họp Đại hội cổ đông thường niên</td><td>18/03/2026</td><td>19/03/2026</td><td>17/04/2026</td></tr></table>'
        rows=em.hnx_rows(hnx,'QNS','https://hnx.example/QNS','HNX')
        cash=next(x for x in rows if x['type']=='cash_dividend')
        self.assertEqual(cash['date'],'2026-01-13')
        self.assertEqual(cash['details']['recordDate'],'2026-01-14')
        self.assertEqual(cash['details']['payoutDate'],'2026-01-23')
        self.assertEqual(cash['dataQuality'],'official')
        events='<div>Lịch chia cổ tức 17/06/2022 HPG Mã HPG trả cổ tức bằng cổ phiếu, tỉ lệ 0.30, ngày GDKHQ 2022-06-17, ngày thực hiện 2022-07-06</div><div>Lịch chia cổ tức 17/06/2022 HPG Mã HPG trả cổ tức bằng tiền, tỉ lệ 0.05 (500 đồng/cổ phiếu), ngày GDKHQ 2022-06-17, ngày thực hiện 2022-07-06</div>'
        rows=em.parse_24hmoney_events(events,'HPG','https://24hmoney.example/stock/HPG/events')
        self.assertTrue(any(x['type']=='stock_dividend' and x['date']=='2022-06-17' for x in rows))
        self.assertTrue(any(x['type']=='cash_dividend' and x['date']=='2022-06-17' for x in rows))
        self.assertTrue(all(x['dataQuality']=='aggregated' for x in rows))

    def test_events_v8_parses_24hmoney_event_timeline(self):
        raw='<div>Sự kiện 15/05/2026 HPG HPG: Thông báo về ngày đăng ký cuối cùng trả cổ tức năm 2025 bằng cổ phiếu</div><div>Lịch chia cổ tức 15/05/2026 HPG Mã HPG trả cổ tức bằng cổ phiếu, tỉ lệ 0.1 (phát hành thêm: 767,546,585), ngày GDKHQ 2026-07-01, ngày thực hiện 2026-07-02</div><div>Lịch chia cổ tức 05/05/2026 HPG Mã HPG chia cổ tức bằng tiền, tỉ lệ 0.05 (500 đồng/cổ phiếu), ngày GDKHQ 2026-05-11, ngày thực hiện 2026-06-03</div>'
        rows=em.parse_24hmoney_events(raw,'HPG','https://24hmoney.vn/stock/HPG/events')
        self.assertGreaterEqual(len(rows),2)
        self.assertTrue(any(x['type']=='stock_dividend' for x in rows))
        self.assertTrue(any(x['type']=='cash_dividend' for x in rows))
        self.assertTrue(any(x['details'].get('exRightDate')=='2026-07-01' for x in rows))
        self.assertTrue(all(x['dataQuality']=='aggregated' for x in rows))

    def test_events_v8_uses_24hmoney_and_does_not_crawl_two_hundred_hnx_pages(self):
        cfg=json.loads((ROOT/'config/event_sources.json').read_text())
        enabled={x['code']:x for x in cfg['sources'] if x.get('enabled')}
        self.assertIn('24HMONEY_EVENTS',enabled)
        self.assertNotIn('HNX_LISTED',enabled)
        self.assertNotIn('HNX_UPCOM',enabled)
        self.assertNotIn('CAFEF_EVENTS',enabled)
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        self.assertIn('refresh_events.py',flow)
        self.assertIn("EVENT_FETCH_WORKERS: '12'",flow)


    def test_events_v6_dedupes_secondary_when_official_event_exists(self):
        official={'id':'a','symbol':'HPG','type':'cash_dividend','date':'2022-06-17','title':'Official','details':{'recordDate':'2022-06-20','ratio':'5%'},'source':{'publisher':'HOSE','url':'https://example.com/o'},'dataQuality':'official'}
        secondary={'id':'b','symbol':'HPG','type':'cash_dividend','date':'2022-06-17','title':'CafeF','details':{'ratio':'5%'},'source':{'publisher':'CafeF','url':'https://example.com/c'},'dataQuality':'secondary'}
        rows=em.merge_events([official],[],[secondary])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['details']['ratio'],'5%')

    def test_events_v6_has_official_registry_schedule_and_pages_trigger(self):
        sources=json.loads((ROOT/'config/event_sources.json').read_text())
        kinds={x['kind'] for x in sources['sources'] if x.get('enabled')}
        registry={x['code']:x for x in sources['sources']}
        self.assertEqual(registry['VSDC']['url'],'https://vsdc.vn/vi/')
        self.assertIn('24hmoney_events',kinds)
        self.assertIn('health',kinds)
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        pages=(ROOT.parent/'.github/workflows/pages.yml').read_text() if (ROOT.parent/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        self.assertIn("cron: '17 0-10/2 * * 1-5'",flow)
        self.assertIn('financial-insights-data-publisher-v2',flow)
        self.assertIn('refresh_events.py',flow)
        self.assertIn('event-status.json',flow)
        self.assertIn('Refresh investment insights',pages)
        self.assertIn('ref: financial-insights-data',pages)
        self.assertIn('for f in broker-research.json corporate-events.json insights-status.json event-status.json',pages)
        self.assertNotIn('rsync -a _insight-data/data/ financial-report/data/',pages)
        self.assertIn("'insightData':revision('_insight-data')",pages)
        self.assertIn('Verify deployed financial dashboard and critical datasets',pages)
        self.assertIn("grep -q 'DOLPHIN_V6'",pages)
        self.assertNotIn('NEWS STALE:',pages)
        self.assertNotIn('QUOTE STALE:',pages)
        self.assertIn('Pages verifies artifact integrity only',pages)
        self.assertIn("technical-signals.json",pages)

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

    def test_research_bootstrap_has_broad_mbb_hpg_coverage(self):
        research=json.loads((ROOT/'data/broker-research.json').read_text())
        mbb=[x for x in research['reports'] if x['symbol']=='MBB']
        hpg=[x for x in research['reports'] if x['symbol']=='HPG']
        self.assertGreaterEqual(len(mbb),10)
        self.assertGreaterEqual(len({x['broker'] for x in mbb}),8)
        self.assertGreaterEqual(sum(1 for x in mbb if x.get('targetPrice')),6)
        self.assertGreaterEqual(len(hpg),20)
        self.assertGreaterEqual(len({x['broker'] for x in hpg}),12)
        self.assertGreaterEqual(sum(1 for x in hpg if x.get('targetPrice')),14)
        self.assertTrue(all(str(x.get('sourceUrl','')).startswith('https://') for x in mbb+hpg))
        self.assertTrue(any(x.get('dataProvider')=='SMARTCHART' for x in mbb))
        self.assertTrue(any(x.get('dataProvider') in ('24HMONEY','CAFEF') for x in hpg))


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
        rows={x['code']:x for x in sources['sources']}
        self.assertEqual(rows['BSC']['url'],'https://www.bsc.com.vn/trung-tam-bao-cao-phan-tich/')
        self.assertEqual(rows['SSI']['url'],'https://www.ssi.com.vn/khach-hang-ca-nhan/bao-cao-cong-ty')
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

    def test_research_v7_collapses_long_lists_until_user_expands(self):
        insights=(ROOT/'frontend/insights.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn("compactExpanded:false",insights)
        self.assertIn("researchExpanded:false",insights)
        self.assertIn("eventExpanded:false",insights)
        self.assertIn("if(!state.compactExpanded)",insights)
        self.assertIn("insight-summary-toggle",insights)
        self.assertIn("Sự kiện doanh nghiệp",insights)
        self.assertIn("Báo cáo CTCK",insights)
        self.assertIn("reportPreview=shownReports.slice(0,state.researchExpanded?shownReports.length:4)",insights)
        self.assertIn("eventPreview=shownEvents.slice(0,state.eventExpanded?shownEvents.length:6)",insights)
        self.assertIn("data-insight-expand",insights)
        self.assertIn("data-idea-research-expand",insights)
        self.assertIn("data-idea-event-expand",insights)
        self.assertIn("state.compactExpanded=false;render()",insights)
        self.assertIn("state.researchExpanded=false;renderDashboard()",insights)
        self.assertIn("state.eventExpanded=false;renderDashboard()",insights)
        self.assertIn(".insight-more-toggle",css)
        self.assertIn(".insight-summary-toggle",css)
        self.assertIn(".idea-more-toggle",css)

    def test_research_v7_registry_has_broader_broker_coverage_and_finlens(self):
        cfg=json.loads((ROOT/'config/research_sources.json').read_text())
        codes={x['code'] for x in cfg['sources'] if x.get('enabled')}
        self.assertGreaterEqual(len(codes),22)
        self.assertTrue({'TCBS','CTS','PHS','VIX','VDSC','SMARTCHART','24HMONEY'}.issubset(codes))
        finlens=next(x for x in cfg['sources'] if x['code']=='FINLENS')
        self.assertEqual(finlens['adapter'],'finlens_mcp')
        self.assertEqual(finlens['mode'],'optional_authenticated')
        self.assertFalse(finlens['enabled'])

    def test_research_v7_text_listing_discovers_company_reports(self):
        source={'code':'TCBS','name':'Techcom Securities','url':'https://www.tcbs.com.vn/thong-tin/bao-cao-phan-tich/','adapter':'text_listing'}
        raw='<div>21/09/2026 Phân tích công ty Báo cáo phân tích lần đầu · HVN · Tổng Công ty Hàng không Việt Nam</div><div>20/09/2026 Bản tin ngày VN-Index kiểm định hỗ trợ</div>'
        rows=im.discover_text_listing(raw,source,{'HVN','HPG'})
        h=next(x for x in rows if x['symbol']=='HVN')
        self.assertEqual(h['publishedAt'],'2026-09-21')
        self.assertIn('HVN',h['title'])

    def test_research_v7_normalizes_finlens_metadata_without_copying_report_body(self):
        row=im.normalize_finlens_report({
            'ticker':'HPG','broker_name':'BIDV Securities','date':'20/08/2026',
            'title':'HPG - Báo cáo cập nhật KQKD Q2.2026','recommendation':'MUA',
            'target_price':32.7,'report_id':'abc123','summary':'Tóm tắt metadata.'
        },'HPG')
        self.assertEqual(row['broker'],'BSC')
        self.assertEqual(row['targetPrice'],32700)
        self.assertEqual(row['publishedAt'],'2026-08-20')
        self.assertEqual(row['dataProvider'],'FINLENS')
        self.assertIn('finlens.vn',row['sourceUrl'])
        self.assertLessEqual(len(row['summary']),900)

    def test_research_v7_workflow_can_use_finlens_secret_but_does_not_require_it(self):
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        self.assertNotIn('FINLENS_API_KEY:',flow)
        self.assertNotIn('FINLENS_MCP_TOKEN:',flow)
        self.assertNotIn('FINLENS_SYMBOL_BUDGET:',flow)
        self.assertIn("RESEARCH_DETAIL_BUDGET: '24'",flow)
        reports,status,cursor=im.discover_finlens({'name':'FinLens Research','url':'https://mcp.finlens.vn/mcp'}, {'HPG'}, {})
        finlens_cfg=next(x for x in json.loads((ROOT/'config/research_sources.json').read_text())['sources'] if x['code']=='FINLENS')
        self.assertFalse(finlens_cfg['enabled'])
        if not (os.environ.get('FINLENS_API_KEY') or os.environ.get('FINLENS_MCP_TOKEN')):
            self.assertEqual(reports,[])
            self.assertEqual(status['status'],'not_configured')
            self.assertEqual(cursor,0)


    def test_research_v71_registry_has_public_per_symbol_indexes(self):
        cfg=json.loads((ROOT/'config/research_sources.json').read_text())
        rows={x['code']:x for x in cfg['sources'] if x.get('enabled')}
        self.assertGreaterEqual(len(rows),22)
        self.assertEqual(rows['SMARTCHART']['adapter'],'smartchart_symbol')
        self.assertEqual(rows['24HMONEY']['adapter'],'money24_symbol')
        self.assertIn('{symbol}',rows['SMARTCHART']['urlTemplate'])
        self.assertIn('{symbol}',rows['24HMONEY']['urlTemplate'])

    def test_research_v71_parses_smartchart_and_24hmoney_metadata(self):
        smart='Báo cáo mới HPG: Khuyến nghị MUA với giá mục tiêu 26,900 đồng/cổ phiếu DSC · 2026-08-27 HPG: Khuyến nghị MUA với giá mục tiêu 25,000 đồng/cổ phiếu VietinbankSC · 2026-08-26'
        rows=im.parse_smartchart_symbol(smart,'HPG','https://smartchart.vn/bao-cao/HPG')
        self.assertEqual(len(rows),2)
        dsc=next(x for x in rows if x['broker']=='DSC')
        self.assertEqual(dsc['targetPrice'],26900)
        self.assertEqual(dsc['recommendation'],'MUA')
        self.assertEqual(dsc['publishedAt'],'2026-08-27')
        self.assertEqual(dsc['dataProvider'],'SMARTCHART')
        self.assertIn('#finquery-',dsc['sourceUrl'])
        money='HPG: Khuyến nghị MUA với giá mục tiêu 32,700 đồng/cổ phiếu Nguồn: BSC Ngày phát hành: 20/08/2026 Tải về HPG: Báo cáo cập nhật KQKD Q2/2026 Nguồn: NHSV Ngày phát hành: 13/08/2026 Tải về'
        rows=im.parse_24hmoney_symbol(money,'HPG','https://24hmoney.vn/bao-cao-phan-tich?k=HPG')
        self.assertEqual(len(rows),2)
        bsc=next(x for x in rows if x['broker']=='BSC')
        self.assertEqual(bsc['targetPrice'],32700)
        self.assertEqual(bsc['publishedAt'],'2026-08-20')
        self.assertEqual(bsc['dataProvider'],'24HMONEY')

    def test_research_v8_24hmoney_anchor_keeps_real_report_url(self):
        raw='<a href="https://24hmoney.vn/bao-cao-phan-tich/mbb-khuyen-nghi-mua-rpId5554.html">MBB: Khuyến nghị MUA với giá mục tiêu 32,900 đồng/cổ phiếu</a> Nguồn: BSC Ngày phát hành: 24/06/2026 Tải về'
        rows=im.parse_24hmoney_symbol(raw,'MBB','https://24hmoney.vn/bao-cao-phan-tich?k=MBB')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['sourceUrl'],'https://24hmoney.vn/bao-cao-phan-tich/mbb-khuyen-nghi-mua-rpId5554.html')
        self.assertEqual(rows[0]['broker'],'BSC')
        self.assertEqual(rows[0]['targetPrice'],32900)

    def test_research_and_events_include_alphanumeric_vn_tickers(self):
        insights=(ROOT/'scripts/refresh_insights.py').read_text()
        events=(ROOT/'scripts/refresh_events.py').read_text()
        pattern="r'[A-Z][A-Z0-9]{2}'"
        self.assertIn(pattern,insights)
        self.assertIn(pattern,events)
        self.assertNotIn("re.fullmatch(r'[A-Z]{3}',str(x.get('symbol','')).upper())",insights)
        self.assertNotIn("re.fullmatch(r'[A-Z]{3}',str(x.get('symbol','')).upper())",events)
        # VN100 currently includes HT1, NT2 and PC1; all three must survive the universe gate.
        companies=json.loads((ROOT/'data/companies.json').read_text())
        symbols={str(x.get('symbol','')).upper() for x in companies}
        self.assertTrue({'HT1','NT2','PC1'}.issubset(symbols))
    def test_research_v8_timeout_guard_is_bounded_and_incremental(self):
        script=(ROOT/'scripts/refresh_insights.py').read_text()
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        self.assertIn('timeout=8',script)
        self.assertIn('as_completed(futures)',script)
        self.assertIn('detail_jobs=[]',script)
        self.assertIn("min(len(symbols),default_budget)",script)
        self.assertIn("PUBLIC_AGGREGATOR_SYMBOL_BUDGET: '100'",flow)
        self.assertIn("RESEARCH_FETCH_WORKERS: '16'",flow)
        self.assertIn("timeout-minutes: 25",flow)

    def test_research_v8_merge_prefers_richer_curated_summary(self):
        prior={'id':'a','symbol':'HPG','broker':'MBS','publishedAt':'2026-09-18','title':'HPG report','summary':'Tóm tắt FinQuery đã biên soạn','highlights':['Điểm đã xác minh'],'sourceUrl':'https://mbs.example/a'}
        discovered={'id':'b','symbol':'HPG','broker':'MBS','publishedAt':'2026-09-18','title':'HPG report','summary':'Metadata ngắn','sourceUrl':'https://smartchart.example/b','dataProvider':'SMARTCHART'}
        merged=im.merge_reports([prior],[discovered])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['summary'],'Tóm tắt FinQuery đã biên soạn')
        self.assertEqual(merged[0]['highlights'],['Điểm đã xác minh'])


    def test_research_v71_workflow_prioritizes_user_visible_symbols(self):
        flow=(ROOT.parent/'.github/workflows/research-timeline-refresh.yml').read_text() if (ROOT.parent/'.github/workflows/research-timeline-refresh.yml').exists() else pathlib.Path('.github/workflows/research-timeline-refresh.yml').read_text()
        self.assertIn("PUBLIC_AGGREGATOR_SYMBOL_BUDGET: '100'",flow)
        self.assertIn("RESEARCH_PRIORITY_SYMBOLS: 'MBB,HPG,FPT,VCB,VIC'",flow)
        self.assertIn("EVENT_FETCH_WORKERS: '12'",flow)
        event_script=(ROOT/'scripts/refresh_events.py').read_text()
        self.assertIn('ThreadPoolExecutor',event_script)
        self.assertIn("EVENT_FETCH_WORKERS",event_script)
        script=(ROOT/'scripts/refresh_insights.py').read_text()
        self.assertIn("aggregatorCursors",script)
        self.assertIn("discover_public_aggregator",script)
        self.assertIn("dataProvider':provider",script)
        self.assertIn("ThreadPoolExecutor",script)
        insights_js=(ROOT/'frontend/insights.js').read_text()
        self.assertIn("if(!state.compactExpanded)",insights_js)
        self.assertIn('insight-summary-toggle',insights_js)
        self.assertIn("filtered.map(compactCard).join('')",insights_js)
        self.assertIn('symbolsCovered',insights_js)
        self.assertIn("'symbolsTotal':len(universe)",(ROOT/'scripts/refresh_insights.py').read_text())


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
        self.assertIn('financial-insights-data-publisher-v2',flow)
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
        self.assertIn('group: financial-insights-data-publisher-v2',flow)
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
        items = [{'listingInfo': {'symbol':'MBB','refPrice':25000}, 'matchPrice':{'matchPrice':26000,'openPrice':25200,'highest':26300,'lowest':24900,'accumulatedVolume':1234,'time':1727100000000}}, {'listingInfo':{'symbol':'FPT'},'matchPrice':{'matchPrice':None}}]
        rows=m.normalize_board(items,['MBB','FPT'],'2026-09-24T00:00:00+00:00')
        self.assertEqual(rows['MBB']['price'],26000)
        self.assertAlmostEqual(rows['MBB']['changePct'],4)
        self.assertEqual(rows['MBB']['volume'],1234)
        self.assertEqual(rows['MBB']['open'],25200)
        self.assertEqual(rows['MBB']['high'],26300)
        self.assertEqual(rows['MBB']['low'],24900)
        self.assertNotIn('FPT',rows)
        self.assertIsNone(m.number('NaN'))

    def test_history_effective_status_counts_retained_usable_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td); (out/'history').mkdir()
            m.write(out/'history-status.json',{'success':1,'expected':2,'errors':['BBB: timeout']})
            m.write(out/'history'/'AAA.json',{'symbol':'AAA','status':'ok','lastBar':'2026-09-29','bars':[{'time':'2026-09-29','close':10}]})
            m.write(out/'history'/'BBB.json',{'symbol':'BBB','status':'retained','lastBar':'2026-09-29','bars':[{'time':'2026-09-29','close':20}]})
            status=m.update_history_effective_status(out,['AAA','BBB'])
            self.assertEqual(status['effectiveAvailable'],2)
            self.assertEqual(status['effectiveRetained'],1)
            self.assertEqual(status['latestBar'],'2026-09-29')
            self.assertEqual(status['latestBarCoverage'],2)
            self.assertEqual(status['effectiveStatus'],'ok')
    def test_current_session_filter_rejects_t_minus_one_and_future_quotes(self):
        current=datetime(2026,9,29,7,0,tzinfo=timezone.utc)
        rows={
            'FPT':{'sourceTime':'2026-09-29T06:45:00+00:00','price':64000},
            'MBB':{'sourceTime':'2026-09-28T07:45:00+00:00','price':19800},
            'VIC':{'sourceTime':'2026-09-29T10:45:00+00:00','price':90000},
        }
        fresh,stale=m.current_session_quotes(rows,current)
        self.assertIn('FPT',fresh)
        self.assertIn('MBB',stale)
        self.assertIn('VIC',stale)
        self.assertEqual(m.newest_source_time(fresh),'2026-09-29T06:45:00+00:00')

    def test_current_session_filter_rejects_frozen_same_day_quotes_when_live_age_is_required(self):
        current=datetime(2026,10,2,4,0,tzinfo=timezone.utc)  # 11:00 Vietnam
        rows={
            'FPT':{'sourceTime':'2026-10-02T03:55:00+00:00','price':64000},
            'MBB':{'sourceTime':'2026-10-02T02:35:00+00:00','price':19800},
        }
        fresh,stale=m.current_session_quotes(rows,current,max_age_minutes=18)
        self.assertIn('FPT',fresh)
        self.assertIn('MBB',stale)
        fresh_eod,stale_eod=m.current_session_quotes(rows,current)
        self.assertIn('MBB',fresh_eod)
        self.assertNotIn('MBB',stale_eod)

    def test_kbs_session_probe_rejects_future_same_day_trade(self):
        original=m.request_query
        try:
            m.request_query=lambda *args,**kwargs: json.dumps({'data':[{'TD':'29/09/2026','FT':'14:45:00'}]}).encode()
            current=datetime(2026,9,29,1,50,tzinfo=timezone.utc)  # 08:50 Vietnam
            with self.assertRaisesRegex(RuntimeError,'future timestamp'):
                m._kbs_session_probe(['FPT'],current=current)
        finally:
            m.request_query=original

    def test_kbs_board_normalization_preserves_vnd_and_verified_session_time(self):
        payload=[
            {'SB':'FPT','RE':63700,'CP':64100,'TT':1234567,'OP':63800,'HI':64500,'LO':63600,'CHP':0.63},
            {'SB':'MBB','RE':19800,'CP':0,'TT':0,'OP':0,'HI':0,'LO':0,'CHP':0},
        ]
        verified='2026-09-29T06:45:00+00:00'
        rows=m.normalize_kbs_board(payload,['FPT','MBB'],'2026-09-29T06:46:00+00:00',verified)
        self.assertEqual(rows['FPT']['price'],64100)
        self.assertEqual(rows['FPT']['reference'],63700)
        self.assertEqual(rows['FPT']['volume'],1234567)
        self.assertEqual(rows['FPT']['source'],'KBS')
        self.assertEqual(rows['FPT']['sourceTime'],verified)
        self.assertEqual(rows['MBB']['price'],19800)
        self.assertEqual(rows['MBB']['volume'],0)
        self.assertEqual(rows['MBB']['sourceTimeBasis'],'current_session_trade_probe')

    def test_kbs_trade_timestamp_parses_trade_date_and_time(self):
        stamp=m._kbs_trade_time({'TD':'29/09/2026','FT':'14:05:01'})
        self.assertEqual(stamp,'2026-09-29T07:05:01+00:00')
        stamp2=m._kbs_trade_time({'t':'2026-09-29 14:05:01:40'})
        self.assertEqual(stamp2,'2026-09-29T07:05:01+00:00')

    def test_technical_scanner_detects_macd_rsi_and_volume_conditions(self):
        bars=[]
        for i in range(70):
            close=10000 + i*i*8
            bars.append({
                'time':f'2026-07-{1+i:02d}' if i<31 else f'2026-08-{i-30:02d}' if i<62 else f'2026-09-{i-61:02d}',
                'open':close-20,'high':close+80,'low':close-80,'close':close,
                'volume':2000000 if i==69 else 1000000,
            })
        base=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':'2026-09-08T07:45:00+00:00'})
        self.assertIsNotNone(base)
        self.assertGreater(base['macdHistogram'],0)
        previous={'barDate':base['barDate'],'macdHistogram':-abs(base['macdHistogram'])-1,'rsi14':base['rsi14']}
        row=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'changePct':1.2,'sourceTime':'2026-09-08T07:45:00+00:00'},previous)
        ids={x['id'] for x in row['signals']}
        self.assertIn('macd_cross_up',ids)
        self.assertIn('rsi_overbought',ids)
        self.assertIn('volume_spike',ids)
        self.assertAlmostEqual(row['volumeRatio20'],2.0,places=2)
        self.assertEqual(m.TECHNICAL_SCANNER_RULES['rsi']['oversold'],30)
        self.assertEqual(m.TECHNICAL_SCANNER_RULES['rsi']['overbought'],70)
        self.assertEqual(m.TECHNICAL_SCANNER_RULES['macd']['nearCrossMaxSpreadPct'],0.15)

    def test_technical_scanner_keeps_cross_signal_for_repeated_same_source_snapshot(self):
        bars=[]
        for i in range(70):
            close=10000 + i*i*8
            bars.append({
                'time':f'2026-07-{1+i:02d}' if i<31 else f'2026-08-{i-30:02d}' if i<62 else f'2026-09-{i-61:02d}',
                'open':close-20,'high':close+80,'low':close-80,'close':close,
                'volume':1000000,
            })
        stamp='2026-09-08T07:45:00+00:00'
        base=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':stamp})
        self.assertGreater(base['macdHistogram'],0)
        previous={
            'barDate':base['barDate'],'sourceTime':stamp,
            'macdHistogram':base['macdHistogram'],'previousMacdHistogram':-abs(base['macdHistogram'])-1,
            'rsi14':base['rsi14'],'previousRsi14':base['rsi14']-5,
        }
        repeated=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':stamp},previous)
        self.assertEqual(repeated['previousMacdHistogram'],previous['previousMacdHistogram'])
        self.assertIn('macd_cross_up',{x['id'] for x in repeated['signals']})
        next_row=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':'2026-09-08T08:00:00+00:00'},previous)
        self.assertEqual(next_row['previousMacdHistogram'],previous['macdHistogram'])
        self.assertNotIn('macd_cross_up',{x['id'] for x in next_row['signals']})

    def test_technical_scanner_repairs_collapsed_same_source_comparator(self):
        bars=[]
        for i in range(70):
            close=10000 + i*i*8
            bars.append({
                'time':f'2026-07-{1+i:02d}' if i<31 else f'2026-08-{i-30:02d}' if i<62 else f'2026-09-{i-61:02d}',
                'open':close-20,'high':close+80,'low':close-80,'close':close,
                'volume':1000000,
            })
        stamp='2026-09-08T07:45:00+00:00'
        baseline=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':stamp})
        collapsed={
            'barDate':baseline['barDate'],'sourceTime':stamp,
            'macdHistogram':baseline['macdHistogram'],'previousMacdHistogram':baseline['macdHistogram'],
            'rsi14':baseline['rsi14'],'previousRsi14':baseline['rsi14'],
        }
        repaired=m.technical_scan_symbol('FPT',bars,{'price':bars[-1]['close'],'sourceTime':stamp},collapsed)
        self.assertEqual(repaired['previousMacdHistogram'],baseline['previousMacdHistogram'])
        self.assertEqual(repaired['previousRsi14'],baseline['previousRsi14'])
        self.assertNotEqual(repaired['previousMacdHistogram'],repaired['macdHistogram'])

    def test_offline_scanner_rebuild_uses_existing_snapshot_and_real_cadence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td); (out/'history').mkdir()
            bars=[]
            for i in range(70):
                close=10000+i*i*8
                bars.append({
                    'time':f'2026-07-{1+i:02d}' if i<31 else f'2026-08-{i-30:02d}' if i<62 else f'2026-09-{i-61:02d}',
                    'open':close-20,'high':close+80,'low':close-80,'close':close,'volume':1000000,
                })
            m.write(out/'history'/'FPT.json',{'symbol':'FPT','bars':bars})
            stamp='2026-09-08T07:45:00+00:00'
            m.write(out/'quotes.json',{'status':'ok','latestSourceTime':stamp,'quotes':{'FPT':{'symbol':'FPT','status':'ok','price':bars[-1]['close'],'changePct':1.2,'sourceTime':stamp}}})
            m.scanner(out,[{'symbol':'FPT','tier':'CORE'}])
            data=m.read(out/'technical-signals.json',{})
            self.assertEqual(data['sourceTime'],stamp)
            self.assertEqual(data['refreshEveryMinutes'],5)
            self.assertIn('FPT',data['symbols'])
            self.assertNotEqual(data['symbols']['FPT']['macdHistogram'],data['symbols']['FPT']['previousMacdHistogram'])
            watch=m.read(out/'watch-today.json',{})
            self.assertEqual(watch['status'],'ok')
            self.assertEqual(watch['sourceTime'],stamp)
            self.assertEqual(watch['refreshEveryMinutes'],5)

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

    def test_today_watchlist_ranks_positive_core_and_tracks_snapshot_changes(self):
        companies=[
            {'symbol':'HSG','coreMember':True,'tier':'CORE'},
            {'symbol':'VIB','coreMember':True,'tier':'CORE'},
            {'symbol':'BAD','coreMember':True,'tier':'CORE'},
            {'symbol':'FALL','coreMember':True,'tier':'CORE'},
            {'symbol':'LIQ','coreMember':False,'tier':'LIQUID'},
        ]
        quotes={
            'HSG':{'status':'ok','price':20000,'changePct':1.5,'sourceTime':'2026-09-30T03:00:00+00:00'},
            'VIB':{'status':'ok','price':18000,'changePct':1.0,'sourceTime':'2026-09-30T03:00:00+00:00'},
            'BAD':{'status':'ok','price':10000,'changePct':-1.0,'sourceTime':'2026-09-30T03:00:00+00:00'},
            'FALL':{'status':'ok','price':9000,'changePct':-1.2,'sourceTime':'2026-09-30T03:00:00+00:00'},
            'LIQ':{'status':'ok','price':12000,'changePct':3.0,'sourceTime':'2026-09-30T03:00:00+00:00'},
        }
        first={
            'HSG':{'symbol':'HSG','cadence':'LIVE_15M','barDate':'2026-09-30','bias':'bullish','rsi14':52,'volumeRatio20':1.6,'signals':[{'id':'macd_cross_up','label':'MACD vừa cắt lên Signal','direction':'bullish','strength':'high'},{'id':'volume_spike','label':'Khối lượng tích lũy ≥ 1,5x TB20','direction':'confirmation','strength':'high'}]},
            'VIB':{'symbol':'VIB','cadence':'LIVE_15M','barDate':'2026-09-30','bias':'bullish','rsi14':50,'volumeRatio20':1.0,'signals':[{'id':'macd_near_up','label':'MACD đang tiến sát giao cắt lên','direction':'bullish','strength':'medium'}]},
            'BAD':{'symbol':'BAD','cadence':'LIVE_15M','barDate':'2026-09-30','bias':'bearish','rsi14':55,'volumeRatio20':2.0,'signals':[{'id':'macd_cross_down','label':'MACD vừa cắt xuống Signal','direction':'bearish','strength':'high'}]},
            'FALL':{'symbol':'FALL','cadence':'LIVE_15M','barDate':'2026-09-30','bias':'bullish','rsi14':22,'volumeRatio20':1.5,'signals':[{'id':'macd_near_up','label':'MACD đang tiến sát giao cắt lên','direction':'bullish','strength':'medium'},{'id':'rsi_oversold','label':'RSI đang ở vùng quá bán','direction':'bullish_watch','strength':'medium'}]},
            'LIQ':{'symbol':'LIQ','cadence':'LIVE_15M','barDate':'2026-09-30','bias':'bullish','rsi14':55,'volumeRatio20':2.0,'signals':[{'id':'macd_cross_up','label':'MACD vừa cắt lên Signal','direction':'bullish','strength':'high'}]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)
            (out/'technical-signals.json').write_text(json.dumps({'symbols':first}),encoding='utf-8')
            rows=m.build_today_watchlist(out,companies,quotes)
            self.assertEqual([x['symbol'] for x in rows],['HSG','VIB'])
            payload=json.loads((out/'watch-today.json').read_text())
            self.assertEqual(payload['refreshEveryMinutes'],5)
            self.assertEqual(payload['universe'],'VN100/Core')
            self.assertTrue(all(x['isNew'] for x in payload['items']))
            second=dict(first)
            second['HSG']={**first['HSG'],'signals':[{'id':'macd_near_up','label':'MACD đang tiến sát giao cắt lên','direction':'bullish','strength':'medium'}],'volumeRatio20':.9}
            second['VIB']={**first['VIB'],'signals':[{'id':'macd_cross_up','label':'MACD vừa cắt lên Signal','direction':'bullish','strength':'high'},{'id':'volume_spike','label':'Khối lượng tích lũy ≥ 1,5x TB20','direction':'confirmation','strength':'high'}],'volumeRatio20':1.7}
            (out/'technical-signals.json').write_text(json.dumps({'symbols':second}),encoding='utf-8')
            rows=m.build_today_watchlist(out,companies,quotes)
            self.assertEqual(rows[0]['symbol'],'VIB')
            self.assertEqual(rows[0]['rankChange'],1)
            self.assertEqual(rows[1]['symbol'],'HSG')
            self.assertEqual(rows[1]['rankChange'],-1)

    def test_today_watch_ticker_is_dynamic_and_published_with_live_price_job(self):
        html=(ROOT/'frontend/index.html').read_text()
        app=(ROOT/'frontend/app.js').read_text()
        css=(ROOT/'frontend/style.css').read_text()
        root=ROOT.parent
        price=(root/'.github/workflows/market-price-live.yml').read_text() if (root/'.github/workflows/market-price-live.yml').exists() else pathlib.Path('.github/workflows/market-price-live.yml').read_text()
        session=(ROOT/'scripts/live_session_publisher.sh').read_text()
        self.assertIn('ĐÁNG XEM HÔM NAY',html)
        self.assertIn('id="quick-tickers-track"',html)
        self.assertNotIn('<button data-symbol="MBB">MBB</button><button data-symbol="FPT">FPT</button>',html)
        self.assertIn("marketJson('watch-today.json')",app)
        self.assertIn('rankChange',app)
        self.assertIn('futureSource=Number.isFinite(sourceTime)',app)
        self.assertIn("label.textContent=invalidFuture?'DỮ LIỆU CHƯA HỢP LỆ'",app)
        self.assertIn('if(!document.hidden)loadTodayWatch();},60000)',app)
        self.assertIn('finqueryQuickWatch',css)
        self.assertIn('market/watch-today.json',session)
        self.assertIn('market/watch-today.json market/sector-risk-calibration.json',price)

    def test_news_and_price_refreshes_are_independent_from_heavy_market_jobs(self):
        script=(ROOT/'scripts/refresh_market.py').read_text()
        root=ROOT.parent
        workflow=(root/'.github/workflows/financial-market-refresh.yml').read_text() if (root/'.github/workflows/financial-market-refresh.yml').exists() else pathlib.Path('.github/workflows/financial-market-refresh.yml').read_text()
        price=(root/'.github/workflows/market-price-live.yml').read_text() if (root/'.github/workflows/market-price-live.yml').exists() else pathlib.Path('.github/workflows/market-price-live.yml').read_text()
        intraday=(root/'.github/workflows/market-intraday-live.yml').read_text() if (root/'.github/workflows/market-intraday-live.yml').exists() else pathlib.Path('.github/workflows/market-intraday-live.yml').read_text()
        universe_flow=(root/'.github/workflows/market-universe-refresh.yml').read_text() if (root/'.github/workflows/market-universe-refresh.yml').exists() else pathlib.Path('.github/workflows/market-universe-refresh.yml').read_text()
        session=(ROOT/'scripts/live_session_publisher.sh').read_text()
        news=(root/'.github/workflows/market-news-live.yml').read_text() if (root/'.github/workflows/market-news-live.yml').exists() else pathlib.Path('.github/workflows/market-news-live.yml').read_text()
        pages=(root/'.github/workflows/pages.yml').read_text() if (root/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        self.assertIn('with ThreadPoolExecutor(max_workers=workers) as pool:',script)
        self.assertIn('pool.submit(_fetch_news_feed, publisher, url, companies, current)',script)
        self.assertIn('for future in as_completed(futures):',script)
        self.assertNotIn("cron: '7,22,37,52 2-8 * * 1-5'",workflow)
        self.assertIn("cron: '0,15,30,45 2-8 * * 1-5'",workflow)
        self.assertIn("cron: '7,22,37,52 * * * *'",workflow)
        self.assertIn("mode=prices-watchdog",workflow)
        self.assertIn("mode=news-watchdog",workflow)
        self.assertIn("PRICE WATCHDOG",workflow)
        self.assertIn("age<=18 and checked_age<=10",workflow)
        self.assertIn("NEWS WATCHDOG",workflow)
        self.assertIn("MARKET_REQUIRE_TODAY=1",workflow)
        self.assertNotIn("cron: '11,41 * * * *'",workflow)
        self.assertIn("cron: '55 1 * * 1-5'",price)
        self.assertIn("cron: '0 2 * * 1-5'",price)
        self.assertIn("cron: '55 5 * * 1-5'",price)
        self.assertIn('[ "$hhmm" -ge 0855 ]',price)
        self.assertIn("cron: '5,20,35,50 2-8 * * 1-5'",price)
        self.assertNotIn("Forecast V20.1 immutable-price audit and market intelligence",price)
        self.assertNotIn("Forecast V21 guarded session overlay",price)
        self.assertIn("workflows:\n      - Refresh market news stream",price)
        self.assertIn('github.event_name }}" = "workflow_dispatch"',price)
        self.assertNotIn('github.event_name }}" != "schedule"',price)
        self.assertIn('live_session_publisher.sh',price)
        self.assertIn("MARKET_REQUIRE_TODAY=1",session)
        self.assertIn('MARKET_MAX_QUOTE_AGE_MINUTES',session)
        self.assertIn('sleep "$INTERVAL_SECONDS"',session)
        self.assertIn('[ "$now_min" -ge 535 ]',session)
        self.assertIn('Pre-warm ready; waiting',session)
        self.assertIn('validate_snapshot',session)
        self.assertIn('sourceTime is not aligned with quotes',session)
        self.assertIn('market/watch-today.json',session)
        self.assertIn('group: market-price-live',price)
        self.assertIn('timeout-minutes: 200',price)
        self.assertIn('actions: write',price)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'push' }}",price)
        self.assertIn('gh workflow run market-price-live.yml --repo "$GH_REPO" --ref main',workflow)
        self.assertIn('gh workflow run market-news-live.yml --repo "$GH_REPO" --ref main',workflow)
        self.assertNotIn('supervise_forecast_overlay',session)
        self.assertNotIn('forecast-session-v21.json?heartbeat=',session)
        self.assertNotIn('gh workflow run forecast-v21-session-refresh.yml --repo "$GH_REPO" --ref main',session)
        self.assertIn("cron: '7 * * * *'",news)
        self.assertIn('group: market-news-live',news)
        self.assertIn('cancel-in-progress: true',news)
        self.assertIn('restore --worktree market/drivers.json',news)
        self.assertIn('add --sparse market/news.json market/news-latest.json',news)
        self.assertNotIn('add --sparse market/news.json market/drivers.json',news)
        self.assertIn('Maintain resilient news heartbeat',news)
        self.assertIn('news-latest.json',news)
        market=(ROOT/'frontend/market.js').read_text()
        refresh_script=(ROOT/'scripts/refresh_market.py').read_text()
        self.assertIn("get('news-latest.json').catch(()=>get('news.json'))",market)
        self.assertIn("write(out / 'news-latest.json'",refresh_script)
        self.assertIn('sleep 900',news)
        self.assertIn('Refresh live HOSE Core + Liquid prices',pages)
        self.assertIn('Refresh market news stream',pages)
        self.assertIn("group: pages-${{ github.event_name == 'workflow_run' && github.event.workflow_run.conclusion || 'success' }}",pages)
        self.assertIn('cancel-in-progress: true',pages)
        self.assertIn("source_day=source_dt.astimezone",pages)
        self.assertNotIn("vn_day=datetime.now(timezone.utc)",pages)
        self.assertIn("cron: '20 9 * * 1-5'",workflow)
        self.assertIn("cron: '35 9 * * 1-5'",workflow)
        self.assertNotIn("cron: '5,20,35,50 2-8 * * 1-5'",workflow)
        self.assertIn("cron: '5,20,35,50 2-8 * * 1-5'",intraday)
        self.assertIn('group: market-intraday-live',intraday)
        self.assertIn("INTRADAY_COUNT_BACK: '360'",intraday)
        self.assertIn("INTRADAY_RETRIES: '3'",intraday)
        self.assertIn("INTRADAY_RETRY_WORKERS: '1'",intraday)
        self.assertIn("INTRADAY_WORKERS: '2'",intraday)
        self.assertIn("INTRADAY_WRITE_ARCHIVE: '0'",intraday)
        self.assertIn("INTRADAY_RETAIN_1M_BARS: '700'",intraday)
        self.assertIn('add --sparse market/intraday-status.json market/intraday',intraday)
        self.assertIn('Minute candles were published as partial/retained',intraday)
        self.assertIn("HISTORY_RETRY_WORKERS: '2'",workflow)
        self.assertIn("&& '2' || '4'",workflow)
        self.assertIn("&& '3' || '2'",workflow)
        self.assertIn("HISTORY_RECENT_COUNT: '80'",workflow)
        self.assertNotIn("[universe-refresh]",workflow)
        self.assertNotIn("build_hose_universe.py",workflow)
        self.assertIn("group: market-universe-refresh",universe_flow)
        self.assertIn("FINQUERY_MARKET_DIR: /tmp/market-universe/market",universe_flow)
        self.assertIn("add --sparse market/universe.json",universe_flow)
        self.assertIn("cron: '15 10 * * 1-5'",universe_flow)
        pages=(ROOT.parent/'.github/workflows/pages.yml').read_text()
        self.assertIn("stale market universe",pages)
        universe_builder=(ROOT/'scripts/build_hose_universe.py').read_text()
        self.assertIn("Market freshness is derived from market history",universe_builder)
        self.assertIn("independent of forecast freshness",universe_builder)

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
                self.assertEqual(status['expected'],1)
                self.assertEqual(status['histories'],1)
                self.assertEqual(status['retainedQuotes'],0)
                self.assertEqual(status['quoteRefresh'],'15_minute_session_job')
                self.assertIn('server_live_quote_merge',status['historyRefresh'])
                self.assertIn('liveDailyBarsMerged',status)
        finally:
            m.request=original

    def test_live_quote_persists_current_daily_bar_without_history_network_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)
            m.write(out/'history/FPT.json',{
                'symbol':'FPT','source':'KBS','status':'retained','barCount':2,
                'firstBar':'2020-01-02','lastBar':'2026-09-25',
                'bars':[
                    {'time':'2020-01-02','open':10000,'high':10100,'low':9900,'close':10050,'volume':1000},
                    {'time':'2026-09-25','open':65500,'high':65900,'low':64600,'close':64700,'volume':3543900},
                ]
            })
            merged=m.merge_live_daily_quotes(out,{'FPT':{
                'symbol':'FPT','status':'ok','source':'Vietcap',
                'price':63700,'reference':64700,'open':64700,'high':64800,'low':63000,'volume':5148700,
                'sourceTime':'2026-09-28T07:45:00+00:00','collectedAt':'2026-09-28T17:05:35+00:00'
            }})
            saved=m.read(out/'history/FPT.json',{})
            self.assertEqual(merged,1)
            self.assertEqual(saved['source'],'KBS')
            self.assertEqual(saved['firstBar'],'2020-01-02')
            self.assertEqual(saved['lastBar'],'2026-09-28')
            self.assertEqual(saved['bars'][-1],{
                'time':'2026-09-28','open':64700.0,'high':64800.0,'low':63000.0,'close':63700.0,'volume':5148700.0
            })
            self.assertEqual(saved['liveQuoteProvider'],'Vietcap')

    def test_daily_history_normalization_drops_weekend_placeholders(self):
        def ts(year,month,day):
            return int(datetime(year,month,day,8,0,tzinfo=m.VN).timestamp())
        payload={'data':[{
            'symbol':'FPT',
            't':[ts(2026,10,2),ts(2026,10,3),ts(2026,10,4)],
            'o':[62000,62000,62000],
            'h':[63000,63000,63000],
            'l':[61000,61000,61000],
            'c':[62500,62500,62500],
            'v':[1000000,1000000,1000000],
        }]}
        bars=m.normalize_history(payload,'FPT',minute=False)
        self.assertEqual([row['time'] for row in bars],['2026-10-02'])

    def test_live_quote_merge_repairs_zero_low_and_removes_weekend_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)
            m.write(out/'history/FPT.json',{
                'symbol':'FPT','source':'Vietcap','status':'ok',
                'bars':[
                    {'time':'2026-10-02','open':62700,'high':63200,'low':62100,'close':62100,'volume':3199600},
                    {'time':'2026-10-03','open':62700,'high':63200,'low':62100,'close':62100,'volume':3199600},
                    {'time':'2026-10-04','open':62700,'high':63200,'low':62100,'close':62100,'volume':3199600},
                    {'time':'2026-10-05','open':62200,'high':62800,'low':0,'close':62400,'volume':749200},
                ],
            })
            merged=m.merge_live_daily_quotes(out,{'FPT':{
                'symbol':'FPT','status':'ok','source':'Vietcap',
                'price':62300,'reference':62100,'open':62200,'high':62800,'low':62200,'volume':783500,
                'sourceTime':'2026-10-05T03:30:04.562000+00:00','collectedAt':'2026-10-05T03:30:03.404394+00:00',
            }})
            saved=m.read(out/'history/FPT.json',{})
            self.assertEqual(merged,1)
            self.assertEqual([row['time'] for row in saved['bars']],['2026-10-02','2026-10-05'])
            self.assertEqual(saved['bars'][-1]['low'],62200.0)
            self.assertGreater(saved['bars'][-1]['low'],0)

    def test_board_normalization_treats_zero_ohlc_as_missing(self):
        rows=m.normalize_board([{
            'listingInfo':{'symbol':'FPT','refPrice':62100},
            'matchPrice':{
                'symbol':'FPT','matchPrice':62300,'accumulatedVolume':783500,
                'openPrice':62200,'highest':62800,'lowest':0,'time':1791171004562,
            },
        }],['FPT'],'2026-10-05T03:30:03+00:00')
        self.assertEqual(rows['FPT']['open'],62200)
        self.assertEqual(rows['FPT']['high'],62800)
        self.assertIsNone(rows['FPT']['low'])

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
        def business_times(end_ts,count):
            day=datetime.fromtimestamp(end_ts,timezone.utc).astimezone(m.VN).date()
            out=[]
            while len(out)<count:
                if day.weekday()<5:
                    out.append(int(datetime(day.year,day.month,day.day,8,0,tzinfo=m.VN).timestamp()))
                day-=m.timedelta(days=1)
            return sorted(out)
        first=business_times(base,1600)
        second=business_times(first[0]-1,1600)
        pages=[first,second]
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

    def test_normal_eod_history_refresh_uses_small_recent_window_and_merges_retained_history(self):
        original=m._history_page
        calls=[]
        def fake_history_page(symbol,frame,to,count,minute=False):
            calls.append({'symbol':symbol,'frame':frame,'count':count,'minute':minute})
            return [
                {'time':'2026-09-25','open':64700,'high':65000,'low':64600,'close':64700,'volume':3000000},
                {'time':'2026-09-28','open':64700,'high':64800,'low':63000,'close':63700,'volume':5148700},
            ]
        try:
            m._history_page=fake_history_page
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                m.write(out/'history/FPT.json',{'symbol':'FPT','bars':[
                    {'time':'2020-01-02','open':10000,'high':10100,'low':9900,'close':10050,'volume':1000},
                    {'time':'2026-09-25','open':64600,'high':64900,'low':64500,'close':64600,'volume':2000000},
                ]})
                m.os.environ['HISTORY_COUNT_BACK']='1600'
                m.os.environ['HISTORY_RECENT_COUNT']='80'
                ok=m._refresh_one_history(out,'FPT',minute=False)
                saved=m.read(out/'history/FPT.json',{})
                self.assertTrue(ok[1])
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0]['frame'],'ONE_DAY')
                self.assertEqual(calls[0]['count'],80)
                self.assertEqual(saved['firstBar'],'2020-01-02')
                self.assertEqual(saved['lastBar'],'2026-09-28')
                self.assertEqual(saved['bars'][-1]['close'],63700)
                self.assertIn('Vietcap recent',saved['source'])
        finally:
            m._history_page=original
            m.os.environ.pop('HISTORY_COUNT_BACK',None)
            m.os.environ.pop('HISTORY_RECENT_COUNT',None)

    def test_intraday_resamples_to_hose_aware_five_minute_buckets(self):
        bars=[
            {'time':'2026-10-05T02:15:00+00:00','open':100,'high':101,'low':99,'close':100,'volume':10},
            {'time':'2026-10-05T02:16:00+00:00','open':100,'high':102,'low':100,'close':101,'volume':20},
            {'time':'2026-10-05T02:19:00+00:00','open':101,'high':103,'low':100,'close':102,'volume':30},
            {'time':'2026-10-05T06:00:00+00:00','open':103,'high':104,'low':102,'close':104,'volume':40},
            {'time':'2026-10-05T07:45:00+00:00','open':105,'high':106,'low':104,'close':105,'volume':50},
        ]
        out=m.resample_intraday_5m(bars)
        self.assertEqual(len(out),3)
        self.assertEqual(out[0]['time'],'2026-10-05T02:20:00+00:00')
        self.assertEqual(out[0]['session'],'CONTINUOUS_AM')
        self.assertEqual(out[0]['open'],100)
        self.assertEqual(out[0]['high'],103)
        self.assertEqual(out[0]['low'],99)
        self.assertEqual(out[0]['close'],102)
        self.assertEqual(out[0]['volume'],60)
        self.assertEqual(out[1]['time'],'2026-10-05T06:05:00+00:00')
        self.assertEqual(out[1]['session'],'CONTINUOUS_PM')
        self.assertEqual(out[2]['time'],'2026-10-05T07:45:00+00:00')
        self.assertEqual(out[2]['session'],'ATC')

    def test_intraday_refresh_preserves_prior_minutes_and_appends_five_minute_archive(self):
        original=m._history_page
        old_retain=m.os.environ.get('INTRADAY_RETAIN_1M_BARS')
        def fake(symbol,frame,to,count,minute=False):
            self.assertEqual(symbol,'FPT')
            self.assertEqual(frame,'ONE_MINUTE')
            self.assertTrue(minute)
            return [
                {'time':'2026-10-06T02:15:00+00:00','open':101,'high':102,'low':100,'close':101,'volume':20},
                {'time':'2026-10-06T02:16:00+00:00','open':101,'high':103,'low':101,'close':102,'volume':30},
            ]
        try:
            m._history_page=fake
            m.os.environ['INTRADAY_RETAIN_1M_BARS']='3000'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                m.write(out/'intraday/FPT.json',{
                    'symbol':'FPT','bars':[
                        {'time':'2026-10-05T02:15:00+00:00','open':100,'high':101,'low':99,'close':100,'volume':10}
                    ]
                })
                symbol,ok,error=m._refresh_one_history(out,'FPT',minute=True)
                self.assertEqual(symbol,'FPT')
                self.assertTrue(ok,error)
                saved=m.read(out/'intraday/FPT.json',{})
                self.assertEqual(len(saved['bars']),3)
                self.assertEqual(saved['firstBar'],'2026-10-05T02:15:00+00:00')
                five=m.read(out/'intraday-5m/FPT.json',{})
                self.assertEqual(five['interval'],'5m')
                self.assertEqual(five['barCount'],2)
                self.assertEqual(five['bars'][0]['time'],'2026-10-05T02:20:00+00:00')
                self.assertEqual(five['bars'][1]['time'],'2026-10-06T02:20:00+00:00')
        finally:
            m._history_page=original
            if old_retain is None:m.os.environ.pop('INTRADAY_RETAIN_1M_BARS',None)
            else:m.os.environ['INTRADAY_RETAIN_1M_BARS']=old_retain

    def test_intraday_backfill_cursor_extends_before_existing_five_minute_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)
            m.write(out/'intraday-5m/FPT.json',{
                'bars':[{
                    'time':'2026-10-05T02:20:00+00:00','session':'CONTINUOUS_AM',
                    'open':100,'high':101,'low':99,'close':100,'volume':10
                }]
            })
            cursor=m._intraday_backfill_cursor(out,'FPT',[])
            expected=int(datetime.fromisoformat('2026-10-05T02:15:00+00:00').timestamp())-1
            self.assertEqual(cursor,expected)

    def test_intraday_backfill_chunk_uses_validated_large_request_first(self):
        original=m._history_page
        calls=[]
        direct=[
            {'time':'2026-09-04T03:50:00+00:00','open':99,'high':100,'low':98,'close':99,'volume':30},
            {'time':'2026-10-03T07:45:00+00:00','open':100,'high':101,'low':99,'close':100,'volume':20},
        ]
        def fake(symbol,frame,to,count,minute=False):
            calls.append((to,count))
            return direct
        old_count=m.os.environ.get('INTRADAY_BACKFILL_COUNT')
        try:
            m._history_page=fake
            m.os.environ['INTRADAY_BACKFILL_COUNT']='5000'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                rows=m._backfill_intraday_chunk(out,'FPT',[])
                self.assertEqual(len(rows),2)
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][1],5000)
        finally:
            m._history_page=original
            if old_count is None:m.os.environ.pop('INTRADAY_BACKFILL_COUNT',None)
            else:m.os.environ['INTRADAY_BACKFILL_COUNT']=old_count

    def test_intraday_backfill_chunk_falls_back_to_small_backward_pages(self):
        original=m._history_page
        calls=[]
        first=[
            {'time':'2026-10-03T07:44:00+00:00','open':100,'high':101,'low':99,'close':100,'volume':10},
            {'time':'2026-10-03T07:45:00+00:00','open':100,'high':101,'low':99,'close':100,'volume':20},
        ]
        second=[
            {'time':'2026-10-03T07:42:00+00:00','open':99,'high':100,'low':98,'close':99,'volume':30},
            {'time':'2026-10-03T07:43:00+00:00','open':99,'high':100,'low':98,'close':99,'volume':40},
        ]
        def fake(symbol,frame,to,count,minute=False):
            calls.append((to,count))
            if len(calls)==1:
                raise RuntimeError('large request rejected')
            return first if len(calls)==2 else second
        old_pages=m.os.environ.get('INTRADAY_BACKFILL_PAGES')
        old_count=m.os.environ.get('INTRADAY_BACKFILL_COUNT')
        try:
            m._history_page=fake
            m.os.environ['INTRADAY_BACKFILL_COUNT']='5000'
            m.os.environ['INTRADAY_BACKFILL_PAGES']='2'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                rows=m._backfill_intraday_chunk(out,'FPT',[])
                self.assertEqual(len(rows),4)
                self.assertEqual(rows[0]['time'],'2026-10-03T07:42:00+00:00')
                self.assertEqual(calls[0][1],5000)
                self.assertEqual(calls[1][1],700)
                self.assertLess(calls[2][0],calls[1][0])
        finally:
            m._history_page=original
            if old_pages is None:m.os.environ.pop('INTRADAY_BACKFILL_PAGES',None)
            else:m.os.environ['INTRADAY_BACKFILL_PAGES']=old_pages
            if old_count is None:m.os.environ.pop('INTRADAY_BACKFILL_COUNT',None)
            else:m.os.environ['INTRADAY_BACKFILL_COUNT']=old_count

    def test_intraday_archive_summary_reports_real_day_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)
            bars_a=[
                {'time':f'2026-09-{day:02d}T02:20:00+00:00','open':1,'high':1,'low':1,'close':1,'volume':1}
                for day in range(1,31)
            ]
            bars_b=[
                {'time':f'2026-08-{day:02d}T02:20:00+00:00','open':1,'high':1,'low':1,'close':1,'volume':1}
                for day in range(1,29)
            ] + [
                {'time':f'2026-09-{day:02d}T02:20:00+00:00','open':1,'high':1,'low':1,'close':1,'volume':1}
                for day in range(1,21)
            ]
            m.write(out/'intraday-5m/FPT.json',{'bars':bars_a})
            m.write(out/'intraday-5m/VCB.json',{'bars':bars_b})
            summary=m.intraday_archive_summary(out,['FPT','VCB','VHM'])
            self.assertEqual(summary['archive5mAvailable'],2)
            self.assertEqual(summary['archive5mUniverse'],3)
            self.assertEqual(summary['archive5mMinDays'],0)
            self.assertEqual(summary['archive5mAtLeast40Days'],1)
            self.assertGreaterEqual(summary['archive5mMaxDays'],40)

    def test_intraday_low_coverage_is_partial_and_fails_health_gate(self):
        companies=[{'symbol':f'S{i:03d}'} for i in range(10)]
        original=m._refresh_one_history
        old_workers=m.os.environ.get('INTRADAY_WORKERS')
        old_retry=m.os.environ.get('INTRADAY_RETRY_WORKERS')
        def fake(out,symbol,minute=False):
            return (symbol,True,None) if symbol not in {'S008','S009'} else (symbol,False,'timeout')
        try:
            m._refresh_one_history=fake
            m.os.environ['INTRADAY_WORKERS']='1'
            m.os.environ['INTRADAY_RETRY_WORKERS']='1'
            with tempfile.TemporaryDirectory() as tmp:
                out=pathlib.Path(tmp)
                with self.assertRaisesRegex(RuntimeError,'below required'):
                    m.refresh_history_group(out,companies,minute=True)
                status=m.read(out/'intraday-status.json',{})
                self.assertEqual(status['status'],'partial')
                self.assertEqual(status['success'],8)
                self.assertEqual(status['required'],9)
                # One symbol failed twice; 9/10 meets exactly 90%, so make the gate strict test with two failures.
        finally:
            m._refresh_one_history=original
            if old_workers is None:m.os.environ.pop('INTRADAY_WORKERS',None)
            else:m.os.environ['INTRADAY_WORKERS']=old_workers
            if old_retry is None:m.os.environ.pop('INTRADAY_RETRY_WORKERS',None)
            else:m.os.environ['INTRADAY_RETRY_WORKERS']=old_retry

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

    def test_live_market_api_fallback_is_fail_closed_and_frontend_gated(self):
        api=(ROOT.parent/'api/live_market.py').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        scanner=(ROOT/'frontend/technical-scanner.js').read_text()
        self.assertIn("mode == 'quotes'",api)
        self.assertIn("mode == 'news'",api)
        self.assertIn("Current-session quote coverage too low",api)
        self.assertIn("def _strict_live_session()",api)
        self.assertIn("max_age = 18 if _strict_live_session() else None",api)
        self.assertIn("current_session_quotes(fresh, max_age_minutes=max_age)",api)
        self.assertIn("Access-Control-Allow-Origin",api)
        self.assertIn("LIVE_MARKET_FALLBACK_UNAVAILABLE",api)
        self.assertIn("LIVE_FALLBACK_API='https://vmews-risk-analytics-sojd.vercel.app/api/live_market'",market)
        self.assertIn("function newsStale(data)",market)
        self.assertIn("liveFallback('news')",market)
        self.assertIn("liveFallback('quotes')",market)
        self.assertIn("newsLiveFallback",market)
        self.assertIn("setMarketSourceTime",market)
        self.assertIn("setMarketSourceTime(value)",scanner)
        self.assertIn("Scanner live chưa đồng bộ với giá mới nhất",scanner)
        self.assertIn("current:aligned?",scanner)
        self.assertIn("quoteBundleSourceTime",market)

    def test_daily_browser_smoke_exercises_production_ai_and_protected_tabs(self):
        root=ROOT.parent
        path=root/'.github/workflows/financial-dashboard-browser-smoke.yml'
        if not path.exists():
            path=pathlib.Path('.github/workflows/financial-dashboard-browser-smoke.yml')
        flow=path.read_text()
        self.assertIn("cron: '35 9 * * 1-5'",flow)
        self.assertIn("workflows: ['Deploy VMEWS Pages']",flow)
        self.assertIn("EXPECTED_SHA:",flow)
        self.assertIn("Pages deployment mismatch",flow)
        self.assertIn("selenium==4.36.0",flow)
        self.assertIn("finquery-technical-access",flow)
        self.assertIn("finquery-macro-access",flow)
        self.assertNotIn("13579",flow)
        self.assertIn("window.FinQueryAI.analyze(arguments[0])",flow)
        self.assertIn("Vì sao mã này tăng hoặc giảm trong phiên hôm nay?",flow)
        self.assertIn("quoteBundleSourceTime:m.quoteBundleSourceTime||null",flow)
        self.assertIn("bundle_source=snapshot.get('quoteBundleSourceTime')",flow)
        self.assertIn("Opening grace: waiting",flow)
        self.assertIn("9*3600+5*60-open_seconds+2",flow)
        self.assertIn("Phân tích sức khỏe tài chính của doanh nghiệp này.",flow)
        self.assertIn("Các rủi ro định lượng chính hiện tại là gì?",flow)
        self.assertIn("So sánh kỳ gần nhất với kỳ trước và cùng kỳ.",flow)
        self.assertIn("ROE là gì?",flow)
        self.assertIn("Phân tích bối cảnh lãi suất và vĩ mô hiện tại.",flow)
        self.assertIn("document.querySelector('#price-chart canvas')",flow)
        self.assertIn("technical-scanner-rows",flow)
        self.assertIn("idea-report-list",flow)

    def test_dolphin_v6_retries_transient_gemini_and_keeps_valid_key_connected(self):
        js=(ROOT/'frontend/research-ai.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('generativelanguage.googleapis.com',js)
        self.assertIn('vmews_solution_ai_browser_session',js)
        self.assertIn("DOLPHIN_VERSION='DOLPHIN_V6'",js)
        self.assertIn("AI_MODE_KEY='finquery_dolphin_mode'",js)
        self.assertIn("gemini-3.5-flash-lite",js)
        self.assertIn("gemini-3.8-flash",js)
        self.assertIn("async function probeGemini(secret)",js)
        self.assertIn(":generateContent",js)
        self.assertIn("Reply with exactly OK",js)
        self.assertIn("maxOutputTokens:256",js)
        self.assertIn("thinkingConfig={thinkingLevel:'low'}",js)
        self.assertIn("emptyGeminiReason(payload)",js)
        self.assertNotIn("maxOutputTokens:12",js)
        self.assertIn("state.geminiReady=true",js)
        self.assertIn("Dolphin chỉ báo kết nối khi probe generateContent thực sự thành công.",js)
        self.assertNotIn("GOOGLE_AI_ORIGIN+'/interactions'",js)
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
        self.assertIn('technicalScanner:m.scanner||null',js)
        self.assertIn('scanner:m.scanner?.current||null',js)
        self.assertIn('Technical Scanner đang ghi nhận:',js)
        self.assertIn('tín hiệu sàng lọc, không phải khuyến nghị mua/bán',js)
        self.assertIn('TRANSIENT_GEMINI_STATUS',js)
        self.assertIn('geminiGenerateResilient',js)
        self.assertIn('retryDelay(attempt)',js)
        self.assertIn('await waitGemini(retryDelay(attempt))',js)
        self.assertIn('plan.slice(0,6)',js)
        self.assertIn("GEMINI_TRANSIENT_EXHAUSTED",js)
        self.assertIn("thinkingLevel:deep?'medium':'low'",js)
        self.assertIn("khóa vẫn kết nối",js)
        self.assertIn('data-ai-mode="normal" data-ai-prompt="Vì sao mã này tăng hoặc giảm trong phiên hôm nay?"',html)

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

    def test_live_daily_chart_merges_only_fresh_session_quotes(self):
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        root=ROOT.parent
        workflow=(root/'.github/workflows/market-price-live.yml').read_text() if (root/'.github/workflows/market-price-live.yml').exists() else pathlib.Path('.github/workflows/market-price-live.yml').read_text()
        self.assertIn('mergeDailyQuote(q,force=false)',chart)
        self.assertIn("this.baseBars.push({time:day,open,high,low,close:price",chart)
        self.assertIn("openEstimated:!(Number.isFinite(openLive)&&openLive>0)",chart)
        self.assertIn("if(!M.intraday(this.tf))this.mergeDailyQuote(this.lastMarketQuote,true)",chart)
        self.assertIn("Snapshot live · ",chart)
        self.assertIn("currentQuote&&!quoteStale(currentQuote)",market)
        self.assertIn("if(currentQuoteLive)chartController.snapshot(currentQuote)",market)
        self.assertIn("quote=quoteStale(state.quotes[state.symbol])?null",market)
        self.assertIn("futureTimestamp(raw)",market)
        self.assertIn("age < -5 ? Infinity : age",market)
        self.assertIn("quoteBundleSourceTime:state.quoteBundleSourceTime||null",market)
        self.assertIn("setMarketSourceTime?.(state.quoteBundleSourceTime||null)",market)
        self.assertIn("scanner:scan&&(!state.quoteBundleSourceTime||String(scan.sourceTime)===String(state.quoteBundleSourceTime))?scan:null",market)
        self.assertIn('marketSessionActive()',market)
        self.assertIn('id="quote-freshness"',html)
        self.assertIn("cron: '5,20,35,50 2-8 * * 1-5'",workflow)

    def test_chart_ui_hides_verbose_status_and_keeps_vendor_license_in_bundle_only(self):
        html=(ROOT/'frontend/index.html').read_text()
        chart=(ROOT/'frontend/chart-engine.js').read_text()
        insights=(ROOT/'frontend/insights.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        self.assertIn('id="quote-time" class="market-subtitle">',html)
        self.assertIn('id="chart-range-label" hidden',html)
        self.assertIn('id="chart-status" class="market-subtitle" hidden',html)
        self.assertNotIn('class="chart-credit"',html)
        self.assertIn('attributionLogo:false',chart)
        self.assertNotIn('Charts by TradingView Lightweight Charts™',html)
        vendor=(ROOT/'frontend/vendor/lightweight-charts-5.0.9.js').read_text()
        self.assertIn('TradingView Lightweight Charts™ v5.0.9',vendor)
        self.assertIn('Licensed under Apache License 2.0',vendor)
        self.assertNotIn('⌄',insights)
        self.assertNotIn('⌃',insights)
        self.assertIn('.clean-chevron',css)

    def test_production_bundle_matches_dolphin_v6(self):
        bundle=(ROOT/'index.html').read_text()
        source=(ROOT/'frontend/research-ai.js').read_text()
        self.assertIn('DOLPHIN_V6',source)
        self.assertIn('DOLPHIN_V6',bundle)
        self.assertIn('strictCompanyNews',bundle)
        self.assertIn('chart-data-mismatch',bundle)
        self.assertIn('Flash-Lite',bundle)
        self.assertIn('id="ai-backdrop"',bundle)
        self.assertIn('data-market-view="peers"',bundle)
        self.assertIn('data-market-view="sector"',bundle)
        self.assertIn('data-market-view="scanner"',bundle)
        self.assertIn('technical-scanner-access-code',bundle)
        self.assertIn('FinTechnicalScanner',bundle)
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

    def test_password_gated_technical_scanner_is_wired_to_live_market_pipeline(self):
        html=(ROOT/'frontend/index.html').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        scanner=(ROOT/'frontend/technical-scanner.js').read_text()
        css=(ROOT/'frontend/market.css').read_text()
        build=(ROOT/'scripts/build_cdn.py').read_text()
        root=ROOT.parent
        workflow=(root/'.github/workflows/market-price-live.yml').read_text() if (root/'.github/workflows/market-price-live.yml').exists() else pathlib.Path('.github/workflows/market-price-live.yml').read_text()
        session=(ROOT/'scripts/live_session_publisher.sh').read_text()
        guard=(root/'.github/workflows/market-realtime-guard.yml').read_text() if (root/'.github/workflows/market-realtime-guard.yml').exists() else pathlib.Path('.github/workflows/market-realtime-guard.yml').read_text()
        self.assertIn('data-market-view="scanner"',html)
        self.assertIn('id="technical-scanner-access-code"',html)
        self.assertIn('MACD · RSI · Volume',html)
        self.assertIn("'scanner'",market)
        self.assertIn('FinTechnicalScanner',market)
        self.assertIn("technical-signals.json",scanner)
        self.assertIn("current:aligned?(state.data.symbols?.[symbol]||null):null",scanner)
        self.assertIn("matches:aligned?",scanner)
        self.assertIn("macd_cross_up",scanner)
        self.assertIn("macd_near_up",scanner)
        self.assertIn("rsi_oversold",scanner)
        self.assertIn("volume_spike",scanner)
        self.assertIn("ACCESS_HASH='0a0667865bc17f9d624bcf11088057bbab46336e7dae65f3d5366f4f7a18333e'",scanner)
        self.assertNotIn("ACCESS_HASH='13579'",scanner)
        self.assertIn('.technical-scanner-panel',css)
        self.assertIn("(front / 'technical-scanner.js').read_text()",build)
        self.assertIn('market/technical-signals.json',session)
        self.assertIn('market/history-status.json',session)
        self.assertIn('restore --worktree market/universe.json',session)
        self.assertNotIn('market/watch-today.json     market/universe.json',session)
        self.assertIn('news-latest.json?heartbeat=',session)
        self.assertIn('scanner coverage below 90%',session)
        self.assertIn("technical-signals.json",guard)
        self.assertIn("news-latest.json",guard)
        self.assertIn("intraday-status.json",guard)
        self.assertIn("market-intraday-live.yml",guard)
        self.assertIn("intraday stale/partial",guard)
        self.assertIn("strategy-indicators.json",guard)
        self.assertIn("watch-today.json",guard)
        self.assertIn("drivers.json",guard)
        self.assertIn("prices-status.json",guard)
        self.assertIn("FINQUERY-RISK-RULES-2.0",guard)
        self.assertNotIn("FINQUERY-RISK-RULES-1.6",guard)
        self.assertIn("watch/scanner barDate mismatch",guard)
        self.assertNotIn("Forecast V20.1 immutable-price audit and market intelligence",guard)
        self.assertNotIn("Forecast V21 guarded session overlay",guard)
        self.assertNotIn("forecast-v21-session-refresh.yml",guard)
        self.assertNotIn("data/forecast-session-v21.json",guard)
        self.assertIn("Refresh market news stream",guard)
        self.assertIn("age(q.get('checkedAt'))>10",guard)
        self.assertIn("age(q.get('latestSourceTime'))>18",guard)
        self.assertIn("540<=mins<=690 or 775<=mins<=915",guard)
        self.assertIn("d.get('sourceTime')!=q.get('latestSourceTime')",guard)

    def test_tiered_hose_universe_is_wired_end_to_end(self):
        script=(ROOT/'scripts/refresh_market.py').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        market=(ROOT/'frontend/market.js').read_text()
        scanner=(ROOT/'frontend/technical-scanner.js').read_text()
        root=ROOT.parent
        price=(root/'.github/workflows/market-price-live.yml').read_text() if (root/'.github/workflows/market-price-live.yml').exists() else pathlib.Path('.github/workflows/market-price-live.yml').read_text()
        session=(ROOT/'scripts/live_session_publisher.sh').read_text()
        pages=(root/'.github/workflows/pages.yml').read_text() if (root/'.github/workflows/pages.yml').exists() else pathlib.Path('.github/workflows/pages.yml').read_text()
        forecast=(root/'.github/workflows/forecast-v13-daily-refresh.yml').read_text() if (root/'.github/workflows/forecast-v13-daily-refresh.yml').exists() else pathlib.Path('.github/workflows/forecast-v13-daily-refresh.yml').read_text()
        self.assertIn('load_market_companies',script)
        self.assertIn("    if args.mode in {'prices', 'history', 'intraday', 'all'}:",script)
        self.assertIn("        sync_market_universe(args.output, universe)",script)
        self.assertIn("        seed_market_histories(args.output, universe, companies)",script)
        self.assertIn('seed_market_histories',script)
        self.assertIn('technical-scanner-v2-tiered-hose',script)
        self.assertIn("market/universe.json",session)
        self.assertIn("financial-report/data/universe.json",price)
        self.assertIn("math.ceil(expected*.90)",session)
        self.assertIn("financial-report/scripts/build_hose_universe.py",forecast)
        self.assertIn("financial-report/data/universe.json",forecast)
        self.assertIn("market/universe.json",pages)
        self.assertIn('id="market-universe-filter"',html)
        self.assertIn('id="technical-scanner-universe"',html)
        self.assertIn('Core · Liquid · Discovery',html)
        self.assertIn("get('universe.json')",market)
        self.assertIn('mergeUniverseCompanies',market)
        self.assertIn("tier!=='CORE'",market)
        self.assertIn("universeFilter:'all'",scanner)
        self.assertIn("Discovery EOD",scanner)
        self.assertIn("cadence==='EOD'",scanner)

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

    def test_world_bank_esg_refresh_cadence_is_weekly_and_cache_aware(self):
        self.assertEqual(m.WORLD_BANK_ESG_REFRESH_HOURS,168)
        recent={'collectedAt':datetime.now(timezone.utc).isoformat()}
        age=m.dataset_age_hours(recent)
        self.assertIsNotNone(age)
        self.assertLess(age,1)
        script=(ROOT/'scripts/refresh_market.py').read_text()
        self.assertIn("'status': 'cached'",script)
        self.assertIn("'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS",script)

    def test_world_bank_esg_vietnam_keeps_all_available_years_and_dynamic_catalog(self):
        original=m._world_bank_json
        calls=[]
        def fake(path,params=None):
            calls.append((path,params))
            if path=='/indicator':
                return {'lastupdated':'2026-09-18'},[
                    {'id':'EN.TEST','name':'Environment test','unit':'%','sourceNote':'E'},
                    {'id':'GOV_TEST','name':'Governance test','unit':'index','sourceNote':'G'},
                ]
            return {'lastupdated':'2026-09-18'},[
                {'indicator':{'id':'EN.TEST'},'date':'1960','value':1.5},
                {'indicator':{'id':'EN.TEST'},'date':'2024','value':2.5},
                {'indicator':{'id':'GOV_TEST'},'date':'1996','value':-0.2},
                {'indicator':{'id':'GOV_TEST'},'date':'2025','value':0.4},
            ]
        try:
            m._world_bank_json=fake
            ds=m.world_bank_esg_vietnam()
            self.assertEqual(ds['id'],'esg_world_bank')
            self.assertTrue(ds['allYears'])
            self.assertTrue(ds['metricTable'])
            self.assertEqual(ds['catalogCount'],2)
            self.assertEqual(ds['indicatorCount'],2)
            self.assertEqual(ds['firstYear'],1960)
            self.assertEqual(ds['lastYear'],2025)
            self.assertEqual(ds['metricLabels']['EN.TEST'],'Environment test')
            self.assertEqual(ds['rows'][0]['EN.TEST'],1.5)
            self.assertEqual(ds['rows'][-1]['GOV_TEST'],0.4)
            self.assertEqual(calls[0][1]['source'],'75')
            self.assertTrue(any('/country/VNM/indicator/' in path for path,_ in calls))
        finally:
            m._world_bank_json=original

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
        self.assertIn('metricLabels',macro)
        self.assertIn('ds.allYears?points:points.slice(-48)',macro)
        self.assertIn('ds.metricTable?[first,state.metric]',macro)
        self.assertNotIn('VBMA + World Bank Sovereign ESG + KPI ESG doanh nghiệp',html)
        self.assertIn('macro-esg-summary',macro)
        self.assertIn('filtered=ds.metricTable&&state.metric',macro)
        self.assertIn("card.hidden=true",macro)
        self.assertIn('WORLD_BANK_ESG_SOURCE', (ROOT/'scripts/refresh_market.py').read_text())
        self.assertIn('company-esg.json',macro)
        self.assertIn('corporateDataset',macro)
        self.assertIn('canonicalMetrics',macro)
        self.assertIn('macro-esg-assessments',html)
        self.assertIn("finquery:symbol-change",(ROOT/'frontend/app.js').read_text())
        self.assertIn("company_esg_",research)
        self.assertIn("externalAssessments",research)
        build=(ROOT/'scripts/build_cdn.py').read_text()
        self.assertIn("(front / 'macro.js').read_text()",build)
        for token in ('MACD cắt lên Signal','RSI thoát vùng quá bán','Supertrend đổi hướng','ADX vượt 25'):
            self.assertIn(token,chart)
        self.assertIn('setInterval(()=>{if(!document.hidden)refresh();},300000)',market)
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
        self.assertIn("HISTORY_RETRIES:",text)
        self.assertIn("&& '3' || '2'",text)
        self.assertIn("HISTORY_RETRY_WORKERS: '2'",text)
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


    def test_forecast_v21_uses_news_as_live_heartbeat_without_running_outside_session(self):
        root=ROOT.parent
        path=root/'.github/workflows/forecast-v21-session-refresh.yml'
        if not path.exists():
            path=pathlib.Path('.github/workflows/forecast-v21-session-refresh.yml')
        flow=path.read_text()
        self.assertIn('Refresh market news stream',flow)
        self.assertIn('Gate workflow heartbeat to Vietnam live session',flow)
        self.assertIn('[ "$hhmm" -ge 0900 ] && [ "$hhmm" -le 1130 ]',flow)
        self.assertIn('[ "$hhmm" -ge 1300 ] && [ "$hhmm" -le 1445 ]',flow)
        self.assertIn("if: steps.session.outputs.run == 'true'",flow)
        self.assertIn("if: steps.session.outputs.run == 'true' && success()",flow)

if __name__=='__main__': unittest.main()

