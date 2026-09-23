"""Bundle the production entry point so a cold CDN needs only one HTML request."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build():
    front = ROOT / 'frontend'
    html = (front / 'index.html').read_text()
    html = html.replace('href="favicon.svg"', 'href="frontend/favicon.svg"')
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (front / 'style.css').read_text() + '</style>')
    html = html.replace('<script defer src="xlsx.js"></script><script defer src="app.js"></script>', '')
    datasets = {p.stem: json.loads(p.read_text()) for p in (ROOT / 'data').glob('*.json') if p.stem.isupper()}
    boot = {'companies': json.loads((ROOT / 'data/companies.json').read_text()), 'datasets': datasets}
    payload = json.dumps(boot, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    scripts = '<script id="financial-bootstrap" type="application/json">' + payload + '</script>'
    scripts += '<script>' + (front / 'xlsx.js').read_text() + '</script>'
    scripts += '<script data-base="./data/">' + (front / 'app.js').read_text() + '</script>'
    html = html.replace('</body>', scripts + '</body>')
    (ROOT / 'index.html').write_text(html)
    print('CDN build:', len(datasets), 'companies;', len(html.encode()), 'bytes')

if __name__ == '__main__':
    build()
