"""Public Vietcap market snapshots and publisher RSS; no credentials required."""
import argparse
import csv
import io
import html
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
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
         ('VietnamNet', 'https://vietnamnet.vn/kinh-doanh.rss'),
         ('CafeF', 'https://cafef.vn/thi-truong-chung-khoan.rss'),
         ('CafeF', 'https://cafef.vn/doanh-nghiep.rss'),
         ('CafeF', 'https://cafef.vn/tai-chinh-ngan-hang.rss'),
         ('VnEconomy', 'https://vneconomy.vn/tin-moi.rss'),
         ('VnEconomy', 'https://vneconomy.vn/tai-chinh.rss'),
         ('VnEconomy', 'https://vneconomy.vn/chung-khoan.rss'),
         ('VnEconomy', 'https://vneconomy.vn/thi-truong.rss'),
         ('VnEconomy', 'https://vneconomy.vn/dau-tu.rss'),
         ('VnEconomy', 'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss')]
FEED_TOPICS = {
    'https://baodautu.vn/chung-khoan.rss': {'stocks', 'market', 'investment'},
    'https://baodautu.vn/doanh-nghiep.rss': {'company', 'investment'},
    'https://cafef.vn/thi-truong-chung-khoan.rss': {'stocks', 'market', 'investment'},
    'https://cafef.vn/doanh-nghiep.rss': {'company'},
    'https://cafef.vn/tai-chinh-ngan-hang.rss': {'finance', 'banking'},
    'https://vneconomy.vn/tai-chinh.rss': {'finance'},
    'https://vneconomy.vn/chung-khoan.rss': {'stocks', 'market', 'investment'},
    'https://vneconomy.vn/thi-truong.rss': {'market'},
    'https://vneconomy.vn/dau-tu.rss': {'investment', 'market'},
    'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss': {'company'},
}
TOPIC_PATTERNS = {
    'finance': re.compile(r'tài chính|trái phiếu|tỷ giá|bảo hiểm|ngân sách', re.I),
    'market': re.compile(r'thị trường|giá vàng|giá dầu|hàng hóa|bất động sản', re.I),
    'rates': re.compile(r'lãi suất|tiền gửi|cho vay|tín dụng', re.I),
    'stocks': re.compile(r'chứng khoán|cổ phiếu|vn-?index|hose|hnx|upcom|phái sinh', re.I),
    'banking': re.compile(r'ngân hàng|tín dụng|tiền gửi', re.I),
    'investment': re.compile(r'đầu tư|fdi|giải ngân|dự án|quỹ đầu tư', re.I),
    'macro': re.compile(r'gdp|cpi|lạm phát|kinh tế|xuất khẩu|nhập khẩu|tăng trưởng', re.I),
}
ALIASES = {'MBB': ['MB Bank', 'MBBank', 'Ngân hàng MB', 'Ngân hàng Quân đội', 'Ngân hàng Quân Đội'],
           'VCB': ['Vietcombank'], 'BID': ['BIDV'], 'CTG': ['VietinBank'],
           'TCB': ['Techcombank'], 'VPB': ['VPBank'], 'STB': ['Sacombank'],
           'HDB': ['HDBank'], 'LPB': ['LPBank'], 'VIB': ['Ngân hàng Quốc tế'],
           'VIC': ['Vingroup'], 'VHM': ['Vinhomes'], 'VRE': ['Vincom Retail'],
           'VNM': ['Vinamilk'], 'HPG': ['Tập đoàn Hòa Phát'], 'BVH': ['Tập đoàn Bảo Việt'],
           'MWG': ['Thế Giới Di Động'], 'MSN': ['Masan'], 'SAB': ['Sabeco'],
           'DCM': ['PVCFC', 'Phân bón Cà Mau'], 'FRT': ['FPT Retail'], 'FPT': ['Tập đoàn FPT'],
           'GAS': ['PV GAS'], 'PLX': ['Petrolimex'], 'VJC': ['Vietjet'], 'HVN': ['Vietnam Airlines']}
VBMA_TABLES = {
    'macro_overview': ('tong_quan_kinh_te_vi_mo', 'Tổng quan kinh tế vĩ mô'),
    'fdi': ('tinh_hinh_fdi', 'Tình hình FDI'),
    'gdp_growth': ('toc_do_tang_truong_gdp_thuc_te', 'Tăng trưởng GDP thực tế'),
    'pmi': ('pmi_theo_thang', 'PMI theo tháng'),
    'money_supply': ('tong_cung_tien_theo_thang', 'Tổng cung tiền theo tháng'),
    'credit_sector': ('du_no_tin_dung_theo_nganh_nghe', 'Dư nợ tín dụng theo ngành nghề'),
}


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
    if isinstance(v, bool):
        return None
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
            try:
                return datetime.fromtimestamp(n, timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                return None
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


def normalize_history(payload, symbol, minute=False):
    if isinstance(payload, dict):
        payload = payload.get('data', [])
    if not payload:
        raise ValueError('Empty OHLC response')
    data = next((x for x in payload if x.get('symbol') == symbol), None)
    if data is None:
        raise ValueError('OHLC response is for a different issuer')
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
        key = stamp if minute else day
        rows[key] = dict(time=key, open=o, high=h, low=l, close=c, volume=v)
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


POSITIVE_NEWS = re.compile(r'tăng|tăng trưởng|lãi|lợi nhuận|kỷ lục|vượt kế hoạch|ký kết|trúng thầu|cổ tức|mua vào|nâng hạng|mở rộng|phục hồi|khởi sắc', re.I)
NEGATIVE_NEWS = re.compile(r'giảm|sụt|lỗ|thua lỗ|xử phạt|điều tra|bán ra|hạ dự báo|rủi ro|nợ xấu|chậm thanh toán|thu hồi|cảnh báo|khởi tố', re.I)
DRIVER_WEIGHTS = {'market': .20, 'relative': .28, 'volume': .22, 'momentum': .15, 'news': .15}


def clamp(value, low=-100.0, high=100.0):
    return max(low, min(high, value))


def movement_driver(symbol, quote, bars, news_items, market_change):
    """Transparent factor attribution. Scores describe association, not proven causality."""
    change = number((quote or {}).get('changePct'))
    price = number((quote or {}).get('price'))
    volumes = [number(row.get('volume')) for row in (bars or [])[-20:]]
    volumes = [v for v in volumes if v is not None and v >= 0]
    avg_volume = sum(volumes) / len(volumes) if volumes else None
    current_volume = number((quote or {}).get('volume'))
    volume_ratio = current_volume / avg_volume if avg_volume and current_volume is not None else None

    closes = [number(row.get('close')) for row in (bars or []) if number(row.get('close')) and number(row.get('close')) > 0]
    anchor = closes[-6] if len(closes) >= 6 else closes[0] if closes else None
    momentum = (price / anchor - 1) * 100 if price and anchor else None
    returns = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(max(1, len(closes) - 20), len(closes)) if closes[i - 1] > 0]
    if returns:
        avg_return = sum(returns) / len(returns)
        volatility = (sum((x - avg_return) ** 2 for x in returns) / len(returns)) ** .5
    else:
        volatility = None

    high, low = number((quote or {}).get('high')), number((quote or {}).get('low'))
    range_position = (price - low) / (high - low) * 100 if price is not None and high is not None and low is not None and high > low else None
    relative = change - market_change if change is not None and market_change is not None else None

    current = datetime.now(timezone.utc)
    company_news = []
    weighted_news = []
    for item in news_items or []:
        if symbol not in (item.get('symbols') or []):
            continue
        try:
            published = datetime.fromisoformat(str(item.get('publishedAt')).replace('Z', '+00:00'))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age_hours = max(0, (current - published.astimezone(timezone.utc)).total_seconds() / 3600)
        except (TypeError, ValueError, OverflowError):
            continue
        if age_hours > 72:
            continue
        title = clean(item.get('title'))
        pos, neg = len(POSITIVE_NEWS.findall(title)), len(NEGATIVE_NEWS.findall(title))
        raw = clamp((pos - neg) * 45)
        freshness = 1 if age_hours <= 24 else .65 if age_hours <= 48 else .4
        if raw:
            weighted_news.append(raw * freshness)
        company_news.append({
            'title': title, 'url': item.get('url'), 'source': item.get('source'),
            'publishedAt': item.get('publishedAt'), 'signal': round(raw, 1)
        })
    news_score = sum(weighted_news) / len(weighted_news) if weighted_news else 0.0

    direction = 1 if (change or 0) > 0 else -1 if (change or 0) < 0 else 0
    scores = {
        'market': clamp((market_change or 0) / 2.5 * 100) if market_change is not None else None,
        'relative': clamp(relative / 3.5 * 100) if relative is not None else None,
        'volume': direction * clamp((volume_ratio - 1) * 80) if volume_ratio is not None and direction else 0.0 if volume_ratio is not None else None,
        'momentum': clamp(momentum / 8 * 100) if momentum is not None else None,
        'news': clamp(news_score) if company_news else 0.0,
    }
    labels = {
        'market': 'Thị trường chung', 'relative': 'Sức mạnh tương đối',
        'volume': 'Thanh khoản', 'momentum': 'Động lượng 5 phiên', 'news': 'Tin tức gần nhất'
    }
    factors = []
    total = 0.0
    available = 0
    for key in ('market', 'relative', 'volume', 'momentum', 'news'):
        score = scores[key]
        if score is None:
            continue
        available += 1
        contribution = score * DRIVER_WEIGHTS[key]
        total += contribution
        factors.append({
            'id': key, 'label': labels[key], 'score': round(score, 1),
            'weight': DRIVER_WEIGHTS[key], 'contribution': round(contribution, 1)
        })
    total = round(clamp(total), 1)
    factors.sort(key=lambda row: abs(row['contribution']), reverse=True)
    evidence = available / len(DRIVER_WEIGHTS)
    confidence_score = round(clamp(38 + evidence * 32 + min(len(company_news), 3) * 4 + min(abs(total), 50) * .18, 0, 92))
    confidence = 'cao' if confidence_score >= 75 else 'trung bình' if confidence_score >= 58 else 'thấp'
    leaders = factors[:2]
    summary = 'Chưa đủ dữ liệu để phân rã biến động.'
    if leaders:
        joined = ' và '.join(f"{row['label']} ({row['contribution']:+.1f})" for row in leaders)
        summary = f"Tín hiệu nổi bật: {joined}. Điểm tổng {total:+.1f}/100."
    return {
        'symbol': symbol, 'generatedAt': now(), 'changePct': change,
        'marketMedianChangePct': round(market_change, 3) if market_change is not None else None,
        'relativeStrengthPct': round(relative, 3) if relative is not None else None,
        'volumeRatio20': round(volume_ratio, 3) if volume_ratio is not None else None,
        'momentum5dPct': round(momentum, 3) if momentum is not None else None,
        'volatility20dPct': round(volatility, 3) if volatility is not None else None,
        'rangePositionPct': round(range_position, 1) if range_position is not None else None,
        'news72hCount': len(company_news), 'newsScore': round(news_score, 1),
        'score': total, 'confidence': confidence, 'confidenceScore': confidence_score,
        'factors': factors, 'headlines': company_news[:5], 'summary': summary,
        'causality': 'association_not_proven'
    }


def build_drivers(out, companies):
    quote_bundle = read(out / 'quotes.json', {'quotes': {}})
    quotes = quote_bundle.get('quotes') or {}
    changes = [number(row.get('changePct')) for row in quotes.values() if row.get('status') == 'ok']
    changes = sorted(v for v in changes if v is not None)
    market_change = changes[len(changes) // 2] if changes else None
    news_items = read(out / 'news.json', {'items': []}).get('items') or []
    symbols = {}
    for company in companies:
        symbol = company['symbol']
        quote = quotes.get(symbol)
        if not quote:
            continue
        bars = read(out / 'history' / (symbol + '.json'), {}).get('bars') or []
        symbols[symbol] = movement_driver(symbol, quote, bars, news_items, market_change)
    write(out / 'drivers.json', {
        'generatedAt': now(), 'methodVersion': 'movement-drivers-v1',
        'marketMedianChangePct': round(market_change, 3) if market_change is not None else None,
        'weights': DRIVER_WEIGHTS, 'symbols': symbols
    })
    return symbols


def prices(out, companies):
    """Fast 15-minute quote snapshot.

    Daily and minute candles are refreshed by separate jobs so the board update
    never waits for 200 per-symbol history requests.
    """
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
        elif symbol in old.get('quotes', {}):
            quotes[symbol] = {**old['quotes'][symbol], 'status': 'retained'}
    write(board_path, {'checkedAt': collected, 'source': 'Vietcap', 'quotes': quotes, 'errors': errors, 'coverage': len(fresh), 'expected': len(symbols)})
    available_histories = sum(1 for symbol in symbols if read(out / 'history' / (symbol + '.json'), {}).get('bars'))
    write(out / 'prices-status.json', {
        'checkedAt': now(), 'quotes': len(fresh), 'histories': available_histories,
        'expected': len(symbols), 'errors': errors, 'historyRefresh': 'separate_eod_job'
    })
    drivers = build_drivers(out, companies)
    print(f'Prices: {len(fresh)}/{len(symbols)}; retained histories: {available_histories}/{len(symbols)}; drivers: {len(drivers)}', flush=True)
    if not fresh:
        raise RuntimeError('Quote collection incomplete; previous successful data retained')


def _refresh_one_history(out, symbol, minute=False):
    folder = 'intraday' if minute else 'history'
    path = out / folder / (symbol + '.json')
    previous = read(path, {})
    frame = 'ONE_MINUTE' if minute else 'ONE_DAY'
    count = int(os.environ.get('INTRADAY_COUNT_BACK', '700')) if minute else 1600
    try:
        payload = json.loads(request(API + 'chart/OHLCChart/gap-chart', {'timeFrame': frame, 'symbols': [symbol], 'to': int(time.time()), 'countBack': count}))
        bars = normalize_history(payload, symbol, minute=minute)
        row = {
            'symbol': symbol, 'source': 'Vietcap', 'unit': 'VND',
            'interval': '1m' if minute else '1D', 'collectedAt': now(),
            'checkedAt': now(), 'status': 'ok', 'bars': bars
        }
        if not minute:
            row['sourceUrl'] = 'https://trading.vietcap.com.vn/'
        write(path, row)
        return symbol, True, None
    except Exception as e:
        if previous.get('bars'):
            write(path, {**previous, 'checkedAt': now(), 'status': 'retained', 'error': str(e)})
        return symbol, False, str(e)


def refresh_history_group(out, companies, minute=False):
    all_symbols = [c['symbol'] for c in companies]
    only_missing = minute and os.environ.get('INTRADAY_ONLY_MISSING') == '1'
    forced = [s.strip().upper() for s in os.environ.get('INTRADAY_SYMBOLS', '').split(',') if s.strip()]
    if minute and forced:
        symbols = [s for s in all_symbols if s in forced]
    else:
        symbols = [s for s in all_symbols if not read(out / 'intraday' / (s + '.json'), {}).get('bars')] if only_missing else all_symbols
    errors, success = [], 0
    # Intraday responses are heavier; use a smaller pool to avoid upstream read timeouts.
    workers = int(os.environ.get('INTRADAY_WORKERS', '3')) if minute else 6
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_refresh_one_history, out, symbol, minute) for symbol in symbols]
        for future in as_completed(futures):
            symbol, ok, error = future.result()
            if ok:
                success += 1
            else:
                errors.append(f'{symbol}{" intraday" if minute else ""}: {error}')
    name = 'intraday' if minute else 'history'
    write(out / f'{name}-status.json', {'checkedAt': now(), 'success': success, 'expected': len(symbols), 'universe': len(all_symbols), 'onlyMissing': only_missing, 'forcedSymbols': forced, 'errors': errors})
    if not minute:
        build_drivers(out, companies)
    print(f'{name}: {success}/{len(symbols)} target; universe {len(all_symbols)}', flush=True)
    # Keep retained data available if a minority of requests fail. Fail only
    # when the entire upstream route is unavailable.
    if success == 0:
        raise RuntimeError(f'{name} refresh failed for all symbols')


def history(out, companies):
    refresh_history_group(out, companies, minute=False)


def intraday(out, companies):
    refresh_history_group(out, companies, minute=True)


def clean(value):
    return re.sub(r'\s+', ' ', re.sub('<[^>]*>', ' ', html.unescape(value or ''))).strip()


def company_match(company, text):
    symbol = company['symbol']
    # MB is an issuer name only in explicit banking context, never a memory unit.
    if symbol == 'MBB' and re.search(r'(?:ngân hàng|lãi suất)', text, re.I) and re.search(r'(?i:ngân hàng|tại|của|từ)\s+MB(?!\w)', text):
        return True
    if symbol == 'FPT':
        text = re.sub(r'FPT\s+(?:Retail|Securities)', '', text, flags=re.I)
    # Short tickers such as GAS, DIG, CEO must be explicitly uppercase in publisher text.
    if re.search(r'(?<!\w)' + re.escape(symbol) + r'(?!\w)', text):
        return True
    aliases = ALIASES.get(symbol, []) + [company['name']]
    return any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I) for alias in aliases if len(alias) >= 5)


def parse_feed(raw, publisher, feed_url, companies, current):
    rows = []
    domain = urlsplit(feed_url).hostname
    text = raw.decode('utf-8-sig') if isinstance(raw, bytes) else raw
    # Some publishers prepend blank lines or a BOM before the XML declaration.
    text = text.lstrip('\ufeff \t\r\n')
    for item in ET.fromstring(text).findall('.//item'):
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
        body = clean(item.findtext('description'))
        text = title + ' ' + body
        matched = [c['symbol'] for c in companies if company_match(c, text)]
        topics = set(FEED_TOPICS.get(feed_url, ()))
        for topic, pattern in TOPIC_PATTERNS.items():
            if pattern.search(text):
                topics.add(topic)
        if matched:
            topics.add('company')
        rows.append({'title': title, 'url': urlunsplit((link.scheme, link.netloc, link.path, '', '')), 'source': publisher, 'publishedAt': dt.isoformat(), 'symbols': matched, 'topics': sorted(topics)})
    return rows


def _vbma_cell(value):
    text = clean(value).strip()
    if not text:
        return None
    candidate = text.replace(' ', '').replace('%', '')
    if re.fullmatch(r'-?\d+(?:[.,]\d+)?', candidate):
        if candidate.count(',') == 1 and candidate.count('.') == 0:
            candidate = candidate.replace(',', '.')
        elif candidate.count('.') > 1 and ',' not in candidate:
            candidate = candidate.replace('.', '')
        try:
            value = float(candidate)
            return int(value) if value.is_integer() else value
        except ValueError:
            pass
    return text


def parse_vbma_table(raw):
    """Decode VBMA macro CSV tables across their legacy encodings/delimiters."""
    best = None
    for encoding in ('utf-16', 'utf-16-le', 'utf-16-be', 'utf-8-sig', 'utf-8', 'cp1258', 'latin1'):
        try:
            text = raw.decode(encoding)
        except (UnicodeError, LookupError):
            continue
        for sep in (',', ';', '\t', '|'):
            try:
                rows = list(csv.reader(io.StringIO(text), delimiter=sep))
            except csv.Error:
                continue
            rows = [[clean(x) for x in row] for row in rows if any(clean(x) for x in row)]
            if not rows or len(rows[0]) <= 1:
                continue
            width = len(rows[0])
            consistent = sum(1 for row in rows[1:51] if len(row) == width)
            score = width * 100 + consistent
            if best is None or score > best[0]:
                best = (score, rows)
    if best is None:
        raise ValueError('Cannot decode VBMA table')
    rows = best[1]
    header = [x or ('Cột ' + str(i + 1)) for i, x in enumerate(rows[0])]
    header[0] = 'Date' if header[0] in ('Unnamed: 0', '') else header[0]
    unique, seen = [], {}
    for name in header:
        seen[name] = seen.get(name, 0) + 1
        unique.append(name if seen[name] == 1 else f'{name} ({seen[name]})')
    data = []
    for raw_row in rows[1:]:
        padded = raw_row + [''] * (len(unique) - len(raw_row))
        data.append({unique[i]: _vbma_cell(padded[i]) for i in range(len(unique))})
    numeric = [name for name in unique if any(isinstance(row.get(name), (int, float)) and not isinstance(row.get(name), bool) for row in data)]
    return {'columns': unique, 'numericColumns': numeric, 'rows': data}


def macro(out, companies=None):
    path = out / 'macro.json'
    previous = read(path, {'datasets': {}})
    datasets, sources = {}, []
    for key, (slug, title) in VBMA_TABLES.items():
        url = f'https://vbma.org.vn/csv/markets/tables/vi/{slug}.csv'
        try:
            parsed = parse_vbma_table(request(url))
            parsed.update({'id': key, 'title': title, 'source': 'VBMA', 'sourceUrl': url, 'collectedAt': now(), 'status': 'ok'})
            datasets[key] = parsed
            sources.append({'id': key, 'url': url, 'status': 'ok', 'rows': len(parsed['rows'])})
        except Exception as e:
            retained = previous.get('datasets', {}).get(key)
            if retained:
                datasets[key] = {**retained, 'status': 'retained', 'error': str(e)}
            sources.append({'id': key, 'url': url, 'status': 'error', 'error': str(e)})
    ok = any(x['status'] == 'ok' for x in sources)
    write(path, {'checkedAt': now(), 'lastSuccessAt': now() if ok else previous.get('lastSuccessAt'), 'status': 'ok' if ok else 'retained', 'source': 'VBMA', 'sources': sources, 'datasets': datasets})
    print(f'Macro: {sum(x["status"] == "ok" for x in sources)}/{len(sources)} VBMA tables; {sum(len(x.get("rows", [])) for x in datasets.values())} rows', flush=True)
    if not datasets:
        raise RuntimeError('VBMA macro collection failed and no retained data is available')


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
    write(path, {'checkedAt': now(), 'lastSuccessAt': now() if ok else previous.get('lastSuccessAt'), 'status': 'ok' if ok else 'retained', 'sources': sources, 'items': list(unique.values())[:2500]})
    drivers = build_drivers(out, companies) if (out / 'quotes.json').exists() else {}
    print(f'News: {len(rows)} fetched; {len(unique)} unique; sources {sum(s["status"] == "ok" for s in sources)}/{len(sources)}; drivers: {len(drivers)}', flush=True)
    if not ok:
        raise RuntimeError('All RSS sources failed; previous news retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['prices', 'history', 'intraday', 'news', 'macro', 'all'], default='all')
    args = parser.parse_args()
    companies = read(ROOT / 'data/companies.json', [])
    if len({c['symbol'] for c in companies}) != 100:
        raise RuntimeError('Expected 100 unique VN100 symbols')
    errors = []
    for mode in (['prices', 'news', 'macro'] if args.mode == 'all' else [args.mode]):
        try:
            globals()[mode](args.output, companies)
        except Exception as e:
            errors.append(str(e))
    if errors:
        raise SystemExit('; '.join(errors))


