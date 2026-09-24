"""Bundle the production entry point so a cold CDN needs only one HTML request."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build():
    front = ROOT / 'frontend'
    metric_path=front/'metrics.js'
    definitions=json.dumps(json.loads((ROOT/'config/derived_metrics.json').read_text()),ensure_ascii=False,separators=(',',':'))
    metric_path.write_text(re.sub(r'const definitions=/\* METRIC_DEFINITIONS \*/.*?;\n',lambda _: 'const definitions=/* METRIC_DEFINITIONS */'+definitions+';\n',metric_path.read_text()))
    checks=json.dumps(json.loads((ROOT/'config/ratio_checks.json').read_text()),ensure_ascii=False,separators=(',',':'))
    metric_path.write_text(re.sub(r'const checks=/\* RATIO_CHECKS \*/.*?;\n',lambda _: 'const checks=/* RATIO_CHECKS */'+checks+';\n',metric_path.read_text()))
    html = (front / 'index.html').read_text()
    html = html.replace('href="favicon.svg"', 'href="frontend/favicon.svg"')
    html = html.replace('<link rel="stylesheet" href="fonts.css">', '<style>' + (front / 'fonts.css').read_text() + '</style>')
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (front / 'style.css').read_text() + '</style>')
    html = html.replace('<script defer src="xlsx.js"></script><script defer src="metrics.js"></script><script defer src="app.js"></script>', '')
    datasets = {p.stem: json.loads(p.read_text()) for p in (ROOT / 'data').glob('*.json') if p.stem in ('MBB','VIC','FPT','VCB')}
    boot = {'companies': json.loads((ROOT / 'data/companies.json').read_text()), 'datasets': datasets}
    payload = json.dumps(boot, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    scripts = '<script id="financial-bootstrap" type="application/json">' + payload + '</script>'
    scripts += '<script>' + (front / 'xlsx.js').read_text() + '</script>'
    scripts += '<script>' + (front / 'metrics.js').read_text() + '</script>'
    scripts += '<script data-base="./data/">' + (front / 'app.js').read_text() + '</script>'
    html = html.replace('</body>', scripts + '</body>')
    (ROOT / 'index.html').write_text(html)
    print('CDN build:', len(datasets), 'companies;', len(html.encode()), 'bytes')

if __name__ == '__main__':
    build()
