"""Public Vietcap market snapshots and publisher RSS; no credentials required."""
import argparse
import html
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VN = timezone(timedelta(hours=7))
API = 'https://trading.vietcap.com.vn/api/'
FEEDS = [('VnExpress', 'https://vnexpress.net/rss/kinh-doanh.rss'),
         ('Báo Đầu tư', 'https://baodautu.vn/chung-khoan.rss'),
         ('Báo Đầu tư', 'https://baodautu.vn/doanh-nghiep.rss'),
         ('VietnamNet', 'https://vietnamnet.vn/kinh-doanh.rss')]
ALIASES = {'MBB': ['MB Bank', 'MBBank', 'Ngân hàng Quân đội', 'Ngân hàng Quân Đội'],
           'VCB': ['Vietcombank'], 'BID': ['BIDV'], 'CTG': ['VietinBank'],
           'TCB': ['Techcombank'], 'VPB': ['VPBank'], 'STB': ['Sacombank'],
           'HDB': ['HDBank'], 'LPB': ['LPBank'], 'VIB': ['Ngân hàng Quốc tế'],
           'VIC': ['Vingroup'], 'VHM': ['Vinhomes'], 'VRE': ['Vincom Retail'],
           'VNM': ['Vinamilk'], 'HPG': ['Tập đoàn Hòa Phát'], 'BVH': ['Tập đoàn Bảo Việt'],
           'MWG': ['Thế Giới Di Động'], 'MSN': ['Masan'], 'SAB': ['Sabeco'],
           'GAS': ['PV GAS'], 'PLX': ['Petrolimex'], 'VJC': ['Vietjet'], 'HVN': ['Vietnam Airlines']}


def now():
    return datetime.now(timezone.utc).isoformat()


def request(url, payload=None):
    headers = {'User-Agent': 'FinQuery/1.0 public financial dashboard', 'Accept': 'application/json, application/xml, text/xml, */*'}
    if payload is not None:
        headers.update({'Content-Type': 'application/json', 'Referer': 'https://trading.vietcap.com.vn/', 'Origin': 'https://trading.vietcap.com.vn'})
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    with urlopen(req, timeout=25) as response:
        return response.read()


def number(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def timestamp(v):
    n = number(v)
    if n is not None:
        if n > 1e12:
            n /= 1000
        if n > 1e9:
            return datetime.fromtimestamp(n, timezone.utc).isoformat()
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return d.replace(tzinfo=d.tzinfo or VN).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def normalize_board(items, symbols, collected):
    rows = {}
    for item in items:
        listing, match = item.get('listingInfo', {}), item.get('matchPrice', {})
        symbol = listing.get('symbol') or match.get('symbol')
        if symbol not in symbols:
            continue
        price, ref = number(match.get('matchPrice')), number(listing.get('refPrice'))
        if price is None or price <= 0:
            continue
        # Vietcap raw price board and OHLC endpoints express prices in VND.
        rows[symbol] = {'symbol': symbol, 'price': price, 'reference': ref,
                        'changePct': (price / ref - 1) * 100 if ref and ref > 0 else None,
                        'volume': number(match.get('accumulatedVolume')),
                        'high': number(match.get('highest')), 'low': number(match.get('lowest')),
                        'sourceTime': timestamp(match.get('time')), 'collectedAt': collected,
                        'source': 'Vietcap', 'unit': 'VND', 'status': 'ok'}
    if not rows:
        raise ValueError('No valid prices in Vietcap response')
    return rows


def normalize_history(payload, symbol):
    if isinstance(payload, dict):
        payload = payload.get('data', [])
    if not payload:
        raise ValueError('Empty OHLC response')
    data = next((x for x in payload if x.get('symbol') == symbol), payload[0])
    fields = ['t', 'o', 'h', 'l', 'c', 'v']
    if not all(isinstance(data.get(k), list) for k in fields) or len({len(data[k]) for k in fields}) != 1:
        raise ValueError('Unexpected OHLC arrays')
    rows = {}
    for values in zip(*(data[k] for k in fields)):
        t, o, h, l, c, v = values
        stamp = timestamp(t)
        nums = [number(x) for x in [o, h, l, c, v]]
        if not stamp or any(x is None for x in nums):
            continue
        o, h, l, c, v = nums
        if min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c) or l > h:
            continue
        day = datetime.fromisoformat(stamp).astimezone(VN).date().isoformat()
        if day > datetime.now(VN).date().isoformat():
            continue
        rows[day] = dict(time=day, open=o, high=h, low=l, close=c, volume=v)
    if not rows:
        raise ValueError('No valid OHLC bars')
    return [rows[k] for k in sorted(rows)]


def read(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
    temp.replace(path)


def prices(out, companies):
    symbols = [c['symbol'] for c in companies]
    board_path = out / 'quotes.json'
    old = read(board_path, {'quotes': {}})
    collected = now()
    errors = []
    try:
        payload = json.loads(request(API + 'price/symbols/getList', {'symbols': symbols}))
        fresh = normalize_board(payload, symbols, collected)
    except Exception as e:
        fresh = {}
        errors.append('quotes: ' + str(e))
    quotes = {}
    for symbol in symbols:
        if symbol in fresh:
            quotes[symbol] = fresh[symbol]
        elif symbol in old['quotes']:
            quotes[symbol] = {**old['quotes'][symbol], 'status': 'retained'}
    write(board_path, {'checkedAt': collected, 'source': 'Vietcap', 'quotes': quotes, 'errors': errors, 'coverage': len(fresh), 'expected': len(symbols)})
    histories = 0
    for symbol in symbols:
        path = out / 'history' / (symbol + '.json')
        previous = read(path, {})
        try:
            payload = json.loads(request(API + 'chart/OHLCChart/gap-chart', {'timeFrame': 'ONE_DAY', 'symbols': [symbol], 'to': int(time.time()), 'countBack': 800}))
            bars = normalize_history(payload, symbol)
            write(path, {'symbol': symbol, 'source': 'Vietcap', 'sourceUrl': 'https://trading.vietcap.com.vn/', 'unit': 'VND', 'interval': '1D', 'collectedAt': now(), 'checkedAt': now(), 'status': 'ok', 'bars': bars})
            histories += 1
        except Exception as e:
            errors.append(symbol + ': ' + str(e))
            if previous.get('bars'):
                write(path, {**previous, 'checkedAt': now(), 'status': 'retained', 'error': str(e)})
        time.sleep(0.6)
    write(out / 'prices-status.json', {'checkedAt': now(), 'quotes': len(fresh), 'histories': histories, 'expected': len(symbols), 'errors': errors})
    print(f'Prices: {len(fresh)}/{len(symbols)}; histories: {histories}/{len(symbols)}', flush=True)
    if not fresh or histories == 0:
        raise RuntimeError('Market collection incomplete; previous successful data retained')


def clean(value):
    return re.sub(r'\s+', ' ', re.sub('<[^>]*>', ' ', html.unescape(value or ''))).strip()


def company_match(company, text):
    symbol = company['symbol']
    # Short tickers such as GAS, DIG, CEO must be explicitly uppercase in publisher text.
    if re.search(r'(?<!\w)' + re.escape(symbol) + r'(?!\w)', text):
        return True
    aliases = ALIASES.get(symbol, []) + [company['name']]
    return any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I) for alias in aliases if len(alias) >= 5)


def parse_feed(raw, publisher, feed_url, companies, current):
    rows = []
    domain = urlsplit(feed_url).hostname
    for item in ET.fromstring(raw).findall('.//item'):
        title = clean(item.findtext('title'))
        link = urlsplit((item.findtext('link') or '').strip())
        if link.scheme not in ('http', 'https') or link.hostname != domain or not title:
            continue
        try:
            dt = parsedate_to_datetime(item.findtext('pubDate'))
            dt = dt.replace(tzinfo=dt.tzinfo or VN).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if dt > current + timedelta(minutes=10) or dt < current - timedelta(days=30):
            continue
        text = title + ' ' + clean(item.findtext('description'))
        matched = [c['symbol'] for c in companies if company_match(c, text)]
        rows.append({'title': title, 'url': urlunsplit((link.scheme, link.netloc, link.path, '', '')), 'source': publisher, 'publishedAt': dt.isoformat(), 'symbols': matched})
    return rows


def news(out, companies):
    path = out / 'news.json'
    previous = read(path, {'items': []})
    current = datetime.now(timezone.utc)
    rows, sources = [], []
    for publisher, url in FEEDS:
        try:
            items = parse_feed(request(url), publisher, url, companies, current)
            rows.extend(items)
            sources.append({'name': publisher, 'url': url, 'status': 'ok', 'items': len(items)})
        except Exception as e:
            sources.append({'name': publisher, 'url': url, 'status': 'error', 'error': str(e)})
    unique = {}
    titles = set()
    for row in sorted(rows + previous['items'], key=lambda r: r['publishedAt'], reverse=True):
        if datetime.fromisoformat(row['publishedAt']) < current - timedelta(days=30):
            continue
        key = clean(row['title']).casefold()
        if row['url'] in unique or key in titles:
            continue
        unique[row['url']] = row
        titles.add(key)
    ok = any(s['status'] == 'ok' for s in sources)
    write(path, {'checkedAt': now(), 'lastSuccessAt': now() if ok else previous.get('lastSuccessAt'), 'status': 'ok' if ok else 'retained', 'sources': sources, 'items': list(unique.values())[:1200]})
    print(f'News: {len(rows)} fetched; {len(unique)} unique; sources {sum(s["status"] == "ok" for s in sources)}/{len(sources)}', flush=True)
    if not ok:
        raise RuntimeError('All RSS sources failed; previous news retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['prices', 'news', 'all'], default='all')
    args = parser.parse_args()
    companies = read(ROOT / 'data/companies.json', [])
    if len({c['symbol'] for c in companies}) != 100:
        raise RuntimeError('Expected 100 unique VN100 symbols')
    errors = []
    for mode in (['prices', 'news'] if args.mode == 'all' else [args.mode]):
        try:
            globals()[mode](args.output, companies)
        except Exception as e:
            errors.append(str(e))
    if errors:
        raise SystemExit('; '.join(errors))
