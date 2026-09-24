"""Integration checks for visual summaries, units and period comparisons."""
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class DashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = """
const fs=require('fs'),dash=require(process.argv[1]);
const vic=JSON.parse(fs.readFileSync(process.argv[2])).quarterly;
const annual=JSON.parse(fs.readFileSync(process.argv[3]));const mbb=annual.quarterly;
const m=dash.model(vic,['2025-Q3','2026-Q2']);
const incomplete=structuredClone(vic);
incomplete.sections.find(s=>s.id==='income_statement').rows.find(r=>r.id==='net_profit_loss_after_tax').values['2026-Q2']=null;
incomplete.sections.find(s=>s.id==='balance_sheet').rows.find(r=>r.id==='owners_equity').values['2026-Q2']=-5;
const cash=incomplete.sections.find(s=>s.id==='cash_flow');cash.basis='year_to_date';
console.log(JSON.stringify({vic:m,annual:dash.model(annual,[2020,2025]),bank:dash.model(mbb,['2026-Q2']),incomplete:dash.model(incomplete,['2026-Q2']),geometry:dash.geometry([{period:'2025-Q3',value:-100},{period:'2025-Q4',value:null},{period:'2026-Q2',value:0}]),empty:dash.model(null,[])}));
"""
        cls.models = json.loads(subprocess.check_output(['node','-e',script,str(ROOT/'frontend/dashboard.js'),str(ROOT/'data/VIC.json'),str(ROOT/'data/MBB.json')],text=True))

    def test_reviewed_vic_values_and_actual_prior_quarter(self):
        m=self.models['vic'];k={r['key']:r for r in m['metrics']}
        self.assertEqual(m['latest'],'2026-Q2')
        self.assertAlmostEqual(k['assets']['value'],1309346.482)
        self.assertAlmostEqual(k['profit']['value'],15294.192)
        self.assertEqual(k['profit']['prior'],'2026-Q1')
        self.assertEqual([p['period'] for p in k['profit']['series']],['2025-Q3','2026-Q2'])
        self.assertAlmostEqual(m['capital']['debt']+m['capital']['equity'],m['capital']['assets'],places=3)

    def test_missing_values_sector_labels_and_cash_basis(self):
        k={r['key']:r for r in self.models['incomplete']['metrics']}
        self.assertIsNone(k['profit']['value'])
        self.assertIsNone(k['cash']['delta'])
        self.assertIn('Lũy kế',k['cash']['label'])
        self.assertIsNone(self.models['incomplete']['capital'])
        revenue=next(r for r in self.models['bank']['metrics'] if r['key']=='revenue')
        self.assertEqual(revenue['label'],'Thu nhập lãi thuần')
        self.assertIsNotNone(revenue['value'])
        self.assertFalse(self.models['empty']['periods'])

    def test_chart_does_not_turn_missing_into_zero_or_join_gap(self):
        g=self.models['geometry'];a,b,c=g['points']
        self.assertIsNone(b['y'])
        self.assertEqual(c['value'],0)
        self.assertGreater(a['y'],g['zero'])
        self.assertAlmostEqual(c['y'],g['zero'])
        self.assertAlmostEqual((b['x']-a['x'])/(c['x']-a['x']),1/3)
        self.assertEqual(g['path'].count('M'),2)

    def test_reviewed_annual_workbook_ids_have_explicit_mapping(self):
        m=self.models['annual'];k={r['key']:r for r in m['metrics']}
        self.assertAlmostEqual(k['assets']['value'],1615763.927)
        self.assertAlmostEqual(k['revenue']['value'],51610.117)
        self.assertEqual(k['revenue']['label'],'Thu nhập lãi thuần')
        self.assertAlmostEqual(k['profit']['value'],27382.978)
        self.assertAlmostEqual(k['cash']['value'],137357.399)
        self.assertAlmostEqual(m['capital']['equity'],142022.525)

if __name__=='__main__':unittest.main()
