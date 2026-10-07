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
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
VN = timezone(timedelta(hours=7))
API = 'https://trading.vietcap.com.vn/api/'
KBS_API = 'https://kbbuddywts.kbsec.com.vn/iis-server/investment'
VI_POLICY_DISCOVERY_URL = 'https://news.google.com/rss/search?' + urlencode({
    'q': '(site:sbv.gov.vn OR site:vanban.chinhphu.vn OR site:luatvietnam.vn OR site:baochinhphu.vn) '
         '(NHNN OR "Ngân hàng Nhà nước" OR "TT-NHNN" OR "chính sách tiền tệ" OR "tỷ giá trung tâm") when:7d',
    'hl': 'vi', 'gl': 'VN', 'ceid': 'VN:vi'
})
VI_DISCLOSURE_DISCOVERY_URL = 'https://news.google.com/rss/search?' + urlencode({
    'q': '(site:hsx.vn OR site:hnx.vn OR site:ssc.gov.vn) '
         '("công bố thông tin" OR "báo cáo tài chính" OR "giao dịch cổ phiếu" OR "doanh nghiệp niêm yết") when:7d',
    'hl': 'vi', 'gl': 'VN', 'ceid': 'VN:vi'
})
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
         ('VnEconomy', 'https://vneconomy.vn/nhip-cau-doanh-nghiep.rss'),
         ('Vietnam Policy Watch', VI_POLICY_DISCOVERY_URL),
         ('Vietnam Disclosure Watch', VI_DISCLOSURE_DISCOVERY_URL),
         ('Federal Reserve', 'https://www.federalreserve.gov/feeds/press_all.xml'),
         ('ECB', 'https://mid.ecb.europa.eu/rss/mid.xml'),
         ('Global Central Banks', 'https://news.google.com/rss/search?q=(Federal+Reserve+OR+Fed+OR+FOMC+OR+ECB+OR+BOJ+OR+PBOC)+when:1d&hl=en-US&gl=US&ceid=US:en'),
         ('Global Markets', 'https://news.google.com/rss/search?q=(gold+OR+oil+OR+Brent+OR+WTI+OR+Treasury+OR+dollar+OR+stocks)+markets+when:1d&hl=en-US&gl=US&ceid=US:en'),
         ('Global Risk', 'https://news.google.com/rss/search?q=(war+OR+sanctions+OR+geopolitical+OR+crisis+OR+default)+markets+when:1d&hl=en-US&gl=US&ceid=US:en')]
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
    VI_POLICY_DISCOVERY_URL: {'vietnam','macro','finance','banking','rates','central_bank','sbv'},
    VI_DISCLOSURE_DISCOVERY_URL: {'vietnam','company','stocks','market'},
    'https://www.federalreserve.gov/feeds/press_all.xml': {'global','macro','rates','central_bank'},
    'https://mid.ecb.europa.eu/rss/mid.xml': {'global','macro','rates','central_bank'},
    'https://news.google.com/rss/search?q=(Federal+Reserve+OR+Fed+OR+FOMC+OR+ECB+OR+BOJ+OR+PBOC)+when:1d&hl=en-US&gl=US&ceid=US:en': {'global','macro','rates','central_bank'},
    'https://news.google.com/rss/search?q=(gold+OR+oil+OR+Brent+OR+WTI+OR+Treasury+OR+dollar+OR+stocks)+markets+when:1d&hl=en-US&gl=US&ceid=US:en': {'global','market','finance'},
    'https://news.google.com/rss/search?q=(war+OR+sanctions+OR+geopolitical+OR+crisis+OR+default)+markets+when:1d&hl=en-US&gl=US&ceid=US:en': {'global','market','macro'},
}
TOPIC_PATTERNS = {
    'finance': re.compile(r'tài chính|trái phiếu|tỷ giá|bảo hiểm|ngân sách', re.I),
    'market': re.compile(r'thị trường|giá vàng|giá dầu|hàng hóa|bất động sản', re.I),
    'rates': re.compile(r'lãi suất|tiền gửi|cho vay|tín dụng', re.I),
    'stocks': re.compile(r'chứng khoán|cổ phiếu|vn-?index|hose|hnx|upcom|phái sinh', re.I),
    'banking': re.compile(r'ngân hàng|tín dụng|tiền gửi', re.I),
    'investment': re.compile(r'đầu tư|fdi|giải ngân|dự án|quỹ đầu tư', re.I),
    'macro': re.compile(r'gdp|cpi|lạm phát|kinh tế|xuất khẩu|nhập khẩu|tăng trưởng|inflation|economic|growth|payroll|employment|pmi', re.I),
    'global': re.compile(r'fed|federal reserve|fomc|ecb|european central bank|boj|pboc|treasury|wall street|euro area|eurozone|united states|china|japan|opec|brent|wti|geopolit', re.I),
    'central_bank': re.compile(r'fed|fomc|ecb|boj|pboc|ngân hàng nhà nước|nhnn|sbv|central bank|monetary policy', re.I),
    'sbv': re.compile(r'ngân hàng nhà nước|nhnn|sbv|thị trường mở|omo|tín phiếu|bơm ròng|hút ròng|liên ngân hàng|tỷ giá trung tâm|dự trữ bắt buộc', re.I),
}

IMPACT_PATTERN = re.compile(
    r'fed|fomc|ecb|boj|pboc|ngân hàng nhà nước|nhnn|sbv|lãi suất|interest rate|rate cut|rate hike|'
    r'omo|thị trường mở|bơm ròng|hút ròng|tỷ giá|exchange rate|treasury|bond yield|cpi|inflation|'
    r'lạm phát|gdp|payroll|employment|oil|brent|wti|gold|vàng|war|conflict|geopolit|sanction|'
    r'default|bank failure|khủng hoảng|phá sản|lao dốc|giảm mạnh|tăng mạnh|tăng vọt|sụt mạnh|'
    r'plunge|plummet|tumble|soar|surge|spike|crash|collapse|record high|record low|halt trading|'
    r'investigation|fraud|indict|arrest|resign|delist|downgrade|upgrade', re.I)
CENTRAL_BANK_PATTERN = re.compile(r'fed|fomc|ecb|boj|pboc|ngân hàng nhà nước|nhnn|sbv|central bank|monetary policy', re.I)
POLICY_DECISION_PATTERN = re.compile(r'raise(?:s|d)? rates?|hike(?:s|d)? rates?|cut(?:s)? rates?|rate cut|rate hike|holds? rates?|leaves? rates? unchanged|tăng lãi suất|giảm lãi suất|hạ lãi suất|giữ nguyên lãi suất|bơm ròng|hút ròng|omo|tín phiếu', re.I)
SBV_PATTERN = re.compile(r'ngân hàng nhà nước|nhnn|sbv|thị trường mở|omo|tín phiếu|bơm ròng|hút ròng|liên ngân hàng|tỷ giá trung tâm|dự trữ bắt buộc', re.I)
SHOCK_MOVE_PATTERN = re.compile(r'lao dốc|giảm mạnh|giảm sốc|rơi mạnh|sụt mạnh|tăng mạnh|tăng vọt|bật tăng|lập đỉnh|kỷ lục|plunge|plummet|tumble|slump|soar|surge|spike|crash|collapse|record high|record low|biggest (?:gain|drop|fall|rise)', re.I)
COMPANY_SHOCK_PATTERN = re.compile(r'phá sản|vỡ nợ|khởi tố|bắt tạm giam|điều tra|gian lận|lừa đảo|đình chỉ|hủy niêm yết|thu hồi|xử phạt|ceo .*từ chức|bankrupt|default|investigation|fraud|indict|arrest|halt trading|delist|recall|ceo .*resign', re.I)
GEOPOLITICAL_PATTERN = re.compile(r'war|conflict|geopolit|sanction|missile|attack|invasion|ceasefire|chiến tranh|xung đột|trừng phạt|tên lửa|tấn công', re.I)
COMMODITY_PATTERN = re.compile(r'gold|vàng|oil|brent|wti|dầu', re.I)
CURRENCY_PATTERN = re.compile(r'tỷ giá|exchange rate|usd|dxy|dollar|yen|yuan|eur|vnd', re.I)
MACRO_SURPRISE_PATTERN = re.compile(r'cpi|inflation|lạm phát|gdp|payroll|employment|jobs report|unemployment|pmi|retail sales|cpi Mỹ|việc làm Mỹ', re.I)

def classify_news_meta(title, body, publisher, topics, published_at):
    text = ' '.join([title or '', body or '', publisher or ''])
    title_text = title or ''
    global_publishers = {'Federal Reserve','ECB','Global Central Banks','Global Markets','Global Risk'}
    region = 'global' if ('global' in topics or publisher in global_publishers or re.search(r'fed|fomc|ecb|euro area|united states|treasury|boj|pboc|china|japan|opec', text, re.I)) else 'vietnam'
    official = 'FED' if publisher == 'Federal Reserve' else ('ECB' if publisher == 'ECB' else None)
    score = 0
    reasons = []
    if POLICY_DECISION_PATTERN.search(text):
        score += 46; reasons.append('quyết định chính sách tiền tệ')
    elif CENTRAL_BANK_PATTERN.search(text):
        score += 32; reasons.append('ngân hàng trung ương')
    if SBV_PATTERN.search(text):
        score += 34; reasons.append('thanh khoản/NHNN')
    if SHOCK_MOVE_PATTERN.search(title_text):
        score += 34; reasons.append('biến động giá mạnh')
    elif SHOCK_MOVE_PATTERN.search(text):
        score += 22; reasons.append('biến động đáng chú ý')
    if COMPANY_SHOCK_PATTERN.search(title_text):
        score += 38; reasons.append('sự kiện doanh nghiệp nghiêm trọng')
    elif COMPANY_SHOCK_PATTERN.search(text):
        score += 24; reasons.append('rủi ro doanh nghiệp')
    if GEOPOLITICAL_PATTERN.search(text):
        score += 32; reasons.append('địa chính trị')
    if COMMODITY_PATTERN.search(text):
        score += 18; reasons.append('hàng hóa')
    if CURRENCY_PATTERN.search(text):
        score += 15; reasons.append('tỷ giá')
    if MACRO_SURPRISE_PATTERN.search(text):
        score += 20; reasons.append('dữ liệu vĩ mô')
    if 'stocks' in topics or 'market' in topics:
        score += 7
    if official:
        score += 8
    try:
        age_h = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(published_at).replace('Z','+00:00')).astimezone(timezone.utc)).total_seconds()/3600)
        score += 20 if age_h <= 3 else (15 if age_h <= 8 else (10 if age_h <= 24 else (3 if age_h <= 48 else 0)))
    except Exception:
        age_h = None
    tag = 'THẾ GIỚI' if region == 'global' else 'VĨ MÔ'
    if SBV_PATTERN.search(text): tag = 'NHNN'
    elif re.search(r'\bfed\b|fomc|federal reserve', text, re.I): tag = 'FED'
    elif re.search(r'\becb\b|european central bank', text, re.I): tag = 'ECB'
    elif GEOPOLITICAL_PATTERN.search(text): tag = 'ĐỊA CHÍNH TRỊ'
    elif re.search(r'gold|vàng', text, re.I): tag = 'VÀNG'
    elif re.search(r'oil|brent|wti|dầu', text, re.I): tag = 'DẦU'
    elif CURRENCY_PATTERN.search(text): tag = 'TỶ GIÁ'
    elif COMPANY_SHOCK_PATTERN.search(text) or 'company' in topics: tag = 'DOANH NGHIỆP'
    elif MACRO_SURPRISE_PATTERN.search(text): tag = 'VĨ MÔ'
    return {
        'region': region, 'officialSource': official, 'impactScore': min(100, score),
        'marketMoving': bool(score >= 48 or IMPACT_PATTERN.search(text)),
        'impactTag': tag, 'impactReasons': reasons[:4]
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
OFFICIAL_NEWS_SOURCES = {
    'ngân hàng nhà nước việt nam', 'ngân hàng nhà nước', 'state bank of vietnam',
    'báo chính phủ', 'cổng thông tin điện tử chính phủ', 'văn bản chính phủ',
    'ho chi minh stock exchange', 'hose', 'sở giao dịch chứng khoán tp.hcm',
    'hanoi stock exchange', 'hnx', 'sở giao dịch chứng khoán hà nội',
    'ủy ban chứng khoán nhà nước', 'state securities commission of vietnam'
}
TRUSTED_POLICY_SOURCES = {'luatvietnam', 'luật việt nam', 'thư viện pháp luật'}

def news_source_quality(source, feed_source=None):
    """Return a transparent source tier used for ranking, never as a truth guarantee."""
    name = clean(source or '').casefold()
    feed = clean(feed_source or '').casefold()
    if name in OFFICIAL_NEWS_SOURCES or any(x in name for x in ('ngân hàng nhà nước', 'báo chính phủ', 'stock exchange', 'chứng khoán nhà nước')):
        return 'official', 100
    if name in TRUSTED_POLICY_SOURCES or any(x in name for x in ('luatvietnam', 'luật việt nam')):
        return 'trusted_legal', 92
    if feed in ('vietnam policy watch', 'vietnam disclosure watch'):
        return 'trusted_discovery', 84
    if name in {'vnexpress', 'báo đầu tư', 'vietnamnet', 'cafef', 'vneconomy'}:
        return 'financial_press', 80
    if name in {'federal reserve', 'ecb'}:
        return 'official', 100
    if feed.startswith('global '):
        return 'global_discovery', 68
    return 'press', 72

VBMA_TABLES = {
    'macro_overview': ('tong_quan_kinh_te_vi_mo', 'Tổng quan kinh tế vĩ mô'),
    'fdi': ('tinh_hinh_fdi', 'Tình hình FDI'),
    'gdp_growth': ('toc_do_tang_truong_gdp_thuc_te', 'Tăng trưởng GDP thực tế'),
    'pmi': ('pmi_theo_thang', 'PMI theo tháng'),
    'money_supply': ('tong_cung_tien_theo_thang', 'Tổng cung tiền theo tháng'),
    'credit_sector': ('du_no_tin_dung_theo_nganh_nghe', 'Dư nợ tín dụng theo ngành nghề'),
}

WORLD_BANK_API = 'https://api.worldbank.org/v2'
WORLD_BANK_ESG_SOURCE = '75'
WORLD_BANK_ESG_PROFILE = 'https://esgdata.worldbank.org/data/countries?iso3=VNM'
WORLD_BANK_ESG_REFRESH_HOURS = int(os.environ.get('WORLD_BANK_ESG_REFRESH_HOURS', str(24 * 7)))


def now():
    return datetime.now(timezone.utc).isoformat()


def request(url, payload=None):
    headers = {'User-Agent': 'FinQuery/1.0 public financial dashboard', 'Accept': 'application/json, application/xml, text/xml, */*'}
    if payload is not None:
        headers.update({'Content-Type': 'application/json', 'Referer': 'https://trading.vietcap.com.vn/', 'Origin': 'https://trading.vietcap.com.vn'})
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    with urlopen(req, timeout=25) as response:
        return response.read()


def request_query(url, params=None, referer=None):
    if params:
        url += ('&' if '?' in url else '?') + urlencode(params)
    headers = {'User-Agent': 'FinQuery/1.0 public financial dashboard', 'Accept': 'application/json, text/plain, */*'}
    if referer:
        headers['Referer'] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as response:
        return response.read()


def number(v):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def positive_number(v):
    n = number(v)
    return n if n is not None and n > 0 else None


def trading_weekday(value):
    try:
        day = datetime.fromisoformat(str(value)[:10]).date()
        return day.weekday() < 5
    except (ValueError, TypeError):
        return False


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
        # Preserve session OHLC fields when the board exposes them so the 15-minute
        # quote snapshot can update the live daily candle without waiting for EOD history.
        open_price = positive_number(match.get('openPrice') if match.get('openPrice') is not None else
                                     match.get('open') if match.get('open') is not None else
                                     item.get('openPrice') if item.get('openPrice') is not None else
                                     listing.get('openPrice'))
        rows[symbol] = {'symbol': symbol, 'price': price, 'reference': ref,
                        'changePct': (price / ref - 1) * 100 if ref and ref > 0 else None,
                        'volume': number(match.get('accumulatedVolume')),
                        'open': open_price,
                        'high': positive_number(match.get('highest')), 'low': positive_number(match.get('lowest')),
                        'sourceTime': timestamp(match.get('time')), 'collectedAt': collected,
                        'source': 'Vietcap', 'unit': 'VND', 'status': 'ok'}
    if not rows:
        raise ValueError('No valid prices in Vietcap response')
    return rows


def _kbs_post(path, payload, timeout=20):
    headers = {
        'User-Agent': 'FinQuery/1.0 public financial dashboard',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
        'Content-Type': 'application/json',
        'x-lang': 'vi',
        'Referer': 'https://kbbuddywts.kbsec.com.vn/',
    }
    req = Request(KBS_API + path, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def _kbs_trade_time(row):
    if not isinstance(row, dict):
        return None
    day = str(row.get('TD') or '').strip()
    clock = str(row.get('FT') or '').strip()
    if day and clock:
        for pattern in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'):
            try:
                local = datetime.strptime(day + ' ' + clock, pattern).replace(tzinfo=VN)
                return local.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
    raw = str(row.get('t') or '').strip()
    if raw:
        # KBS can append an extra centisecond field, e.g. 14:45:04:40.
        raw = re.sub(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):\d+$', r'\1', raw)
        try:
            local = datetime.fromisoformat(raw).replace(tzinfo=VN)
            return local.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def _kbs_session_probe(symbols, current=None):
    """Verify KBS is serving a real current-session timestamp before trusting its board.

    Some public boards can expose rows stamped later in the same trading date.
    A same-day check alone would incorrectly treat those future rows as live.
    """
    current = current or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    future_limit = current + timedelta(minutes=5)
    preferred = [x for x in ('FPT', 'MBB', 'HPG', 'VCB', 'VIC', 'TCB') if x in symbols]
    probes = preferred + [x for x in symbols if x not in preferred][:4]
    today = current.astimezone(VN).date().isoformat()
    errors = []
    for symbol in probes:
        try:
            raw = request_query(
                f'{KBS_API}/trade/history/{symbol}',
                {'page': 1, 'limit': 5},
                'https://kbbuddywts.kbsec.com.vn/'
            )
            payload = json.loads(raw)
            rows = payload.get('data', []) if isinstance(payload, dict) else payload
            if isinstance(rows, dict):
                rows = rows.get('data', []) or rows.get('items', [])
            stamps = [_kbs_trade_time(row) for row in (rows or [])]
            stamps = [stamp for stamp in stamps if stamp]
            if not stamps:
                errors.append(f'{symbol}: no trade timestamp')
                continue
            latest = max(stamps)
            try:
                latest_dt = datetime.fromisoformat(latest).astimezone(timezone.utc)
            except (ValueError, TypeError):
                errors.append(f'{symbol}: invalid timestamp')
                continue
            if latest_dt > future_limit:
                errors.append(f'{symbol}: future timestamp {latest}')
                continue
            if source_day(latest) == today:
                return latest, symbol
            errors.append(f'{symbol}: latest {source_day(latest)}')
        except Exception as exc:
            errors.append(f'{symbol}: {exc}')
    raise RuntimeError('KBS session probe is not current: ' + '; '.join(errors[:6]))


def normalize_kbs_board(payload, symbols, collected, verified_source_time):
    rows = payload
    if isinstance(rows, dict):
        rows = rows.get('data', rows.get('items', []))
    if not isinstance(rows, list):
        raise ValueError('Unexpected KBS price-board response')
    wanted = set(symbols)
    out = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get('SB') or item.get('symbol') or '').upper()
        if symbol not in wanted:
            continue
        ref = number(item.get('RE'))
        matched = number(item.get('CP'))
        volume = number(item.get('TT'))
        if volume is None:
            volume = number(item.get('AVO'))
        if volume is None:
            volume = number(item.get('CV'))
        volume = max(0, volume or 0)
        # A reference price with zero matched volume is not evidence that this
        # symbol traded in the current session. Never borrow another symbol's
        # session timestamp to make a zero-trade row look live.
        if not matched or matched <= 0 or volume <= 0:
            continue
        price = matched
        open_price = number(item.get('OP'))
        high = number(item.get('HI'))
        low = number(item.get('LO'))
        out[symbol] = {
            'symbol': symbol, 'price': price, 'reference': ref,
            'changePct': (price / ref - 1) * 100 if ref and ref > 0 else number(item.get('CHP')),
            'volume': volume, 'open': open_price, 'high': high, 'low': low,
            'sourceTime': verified_source_time, 'collectedAt': collected,
            'source': 'KBS', 'unit': 'VND', 'status': 'ok',
            'sourceTimeBasis': 'current_session_probe_with_symbol_trade'
        }
    return out


def kbs_current_board(symbols, collected):
    verified_source_time, probe_symbol = _kbs_session_probe(symbols)
    rows = {}
    # Keep request bodies bounded; the endpoint accepts comma-separated codes.
    for offset in range(0, len(symbols), 50):
        batch = symbols[offset:offset + 50]
        payload = json.loads(_kbs_post('/stock/iss', {'code': ','.join(batch)}))
        rows.update(normalize_kbs_board(payload, batch, collected, verified_source_time))
    for row in rows.values():
        row['sessionProbeSymbol'] = probe_symbol
    if not rows:
        raise ValueError('No valid prices in KBS price-board response')
    return rows


def source_day(value):
    stamp = timestamp(value)
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).astimezone(VN).date().isoformat()
    except (ValueError, TypeError):
        return None


def current_session_quotes(rows, current=None, max_age_minutes=None):
    """Split board rows into current-session rows and stale/invalid rows.

    max_age_minutes is optional so EOD/manual uses can still accept the latest
    same-day trade. Intraday publishers set it explicitly; this prevents a frozen
    provider board (for example, 09:35 data returned at 11:00) from being treated
    as live merely because the timestamp belongs to today's session.
    """
    current = current or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    today = current.astimezone(VN).date().isoformat()
    future_limit = current + timedelta(minutes=5)
    max_age = None
    try:
        if max_age_minutes is not None:
            max_age = max(0.0, float(max_age_minutes))
    except (ValueError, TypeError):
        max_age = None
    fresh, stale = {}, {}
    for symbol, row in (rows or {}).items():
        stamp = timestamp(row.get('sourceTime'))
        day = source_day(stamp)
        try:
            observed = datetime.fromisoformat(stamp).astimezone(timezone.utc) if stamp else None
        except (ValueError, TypeError):
            observed = None
        age_minutes = ((current - observed).total_seconds() / 60) if observed is not None else None
        current_enough = max_age is None or (age_minutes is not None and age_minutes <= max_age)
        if day == today and observed is not None and observed <= future_limit and current_enough:
            fresh[symbol] = row
        else:
            stale[symbol] = row
    return fresh, stale


def newest_source_time(rows):
    stamps = [timestamp(row.get('sourceTime')) for row in (rows or {}).values()]
    stamps = [stamp for stamp in stamps if stamp]
    return max(stamps) if stamps else None


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
        if not minute and not trading_weekday(day):
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


def load_market_universe(market_dir=None):
    if market_dir:
        published = read(Path(market_dir) / 'universe.json', {})
        if isinstance(published.get('symbols'), dict) and published.get('liveMarketSymbols'):
            return published
    return read(ROOT / 'data/universe.json', {})


def load_market_companies(core_companies, market_dir=None):
    """Return Core + dynamically promoted HOSE Liquid names for live market jobs."""
    universe = load_market_universe(market_dir)
    core = {str(row.get('symbol') or '').upper(): dict(row) for row in core_companies if row.get('symbol')}
    records = universe.get('symbols') if isinstance(universe.get('symbols'), dict) else {}
    live_symbols = universe.get('liveMarketSymbols') if isinstance(universe.get('liveMarketSymbols'), list) else []
    if not live_symbols or not records:
        return [{**row, 'tier': 'CORE', 'coreMember': True} for row in core.values()], universe
    companies = []
    for symbol in live_symbols:
        symbol = str(symbol).upper()
        meta = records.get(symbol) or {}
        base = core.get(symbol) or {}
        companies.append({
            'symbol': symbol,
            'name': base.get('name') or meta.get('name') or symbol,
            'exchange': 'HOSE',
            'tier': meta.get('tier') or ('CORE' if symbol in core else 'LIQUID'),
            'coreMember': symbol in core,
            'medianTurnover20': meta.get('medianTurnover20'),
            'forecastEligible': bool(meta.get('forecastEligible')),
        })
    # Fail safe: Core financial-report names can never disappear because of a
    # malformed/stale dynamic universe file.
    present = {row['symbol'] for row in companies}
    for symbol, row in core.items():
        if symbol not in present:
            companies.append({**row, 'tier': 'CORE', 'coreMember': True})
    companies.sort(key=lambda row: (0 if row.get('tier') == 'CORE' else 1, row['symbol']))
    return companies, universe


def fallback_market_universe(companies):
    """Core-only safety universe used until the validated dynamic universe exists."""
    rows={}
    for company in companies:
        symbol=str(company.get('symbol') or '').upper()
        if not symbol:
            continue
        rows[symbol]={
            'symbol':symbol,
            'name':company.get('name') or symbol,
            'exchange':'HOSE',
            'tier':'CORE',
            'coreMember':True,
            'fresh':True,
            'dataSufficient':True,
            'liveMarketEligible':True,
            'scannerEligible':True,
            'forecastEligible':True,
            'liquidityGatePassed':False,
        }
    symbols=sorted(rows)
    return {
        'version':'FINQUERY-HOSE-UNIVERSE-CORE-FALLBACK',
        'generatedAt':now(),
        'asOf':None,
        'policy':{'fallback':True,'description':'Core 100 safety universe until validated HOSE promotion data is published.'},
        'counts':{'listedHOSE':len(symbols),'core':len(symbols),'liquid':0,'discovery':0,'liveMarket':len(symbols),'scannerEligible':len(symbols),'forecastEligible':len(symbols),'discoveryTechnical':0},
        'liveMarketSymbols':symbols,
        'scannerSymbols':symbols,
        'forecastEligibleSymbols':symbols,
        'symbols':rows,
    }


def public_universe_payload(universe):
    if not isinstance(universe, dict):
        return {}
    output = {key: value for key, value in universe.items() if key not in {'discoveryTechnical'}}
    records = {}
    for symbol, row in (universe.get('symbols') or {}).items():
        if not isinstance(row, dict):
            continue
        records[symbol] = {key: value for key, value in row.items() if key != 'seedBars'}
    output['symbols'] = records
    return output


def sync_market_universe(out, universe):
    if universe:
        write(out / 'universe.json', public_universe_payload(universe))


def seed_market_histories(out, universe, companies):
    """Seed newly promoted Liquid names from the already validated forecast history.

    This makes the first live scanner run useful immediately instead of waiting
    for the nightly history job. Newer market-branch bars always win.
    """
    records = universe.get('symbols') if isinstance(universe, dict) else {}
    if not isinstance(records, dict):
        return 0
    seeded = 0
    for company in companies:
        symbol = company['symbol']
        meta = records.get(symbol) or {}
        raw_bars = meta.get('seedBars') if isinstance(meta, dict) else None
        if not isinstance(raw_bars, list) or not raw_bars:
            continue
        incoming = []
        for row in raw_bars:
            if not isinstance(row, dict):
                continue
            day = str(row.get('time') or row.get('date') or '')[:10]
            close = number(row.get('close'))
            volume = number(row.get('volume'))
            if len(day) != 10 or not trading_weekday(day) or close is None or close <= 0 or volume is None or volume < 0:
                continue
            open_ = number(row.get('open')) or close
            high = number(row.get('high')) or max(open_, close)
            low = number(row.get('low')) or min(open_, close)
            incoming.append({'time': day, 'open': open_, 'high': max(high, open_, close), 'low': min(low, open_, close), 'close': close, 'volume': volume})
        if not incoming:
            continue
        path = out / 'history' / (symbol + '.json')
        previous = read(path, {})
        existing = [bar for bar in previous.get('bars', []) if isinstance(bar, dict) and bar.get('time')]
        merged = {bar['time']: bar for bar in incoming}
        merged.update({bar['time']: bar for bar in existing})
        bars = [merged[key] for key in sorted(merged)]
        if existing and bars[-1]['time'] <= existing[-1]['time'] and len(bars) == len(existing):
            continue
        stamp = now()
        write(path, {
            **previous,
            'symbol': symbol,
            'source': previous.get('source') or 'Validated forecast universe seed',
            'unit': 'VND',
            'interval': '1D',
            'collectedAt': previous.get('collectedAt') or stamp,
            'checkedAt': stamp,
            'status': previous.get('status') or 'ok',
            'barCount': len(bars),
            'firstBar': bars[0]['time'],
            'lastBar': bars[-1]['time'],
            'bars': bars,
            'universeSeed': True,
        })
        seeded += 1
    return seeded


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



TECHNICAL_SCANNER_RULES = {
    'timeframe': '1D-live',
    'refreshMinutes': 15,
    'macd': {'fast': 12, 'slow': 26, 'signal': 9, 'nearCrossMaxSpreadPct': 0.15},
    'rsi': {'period': 14, 'oversold': 30, 'overbought': 70},
    'volume': {'averagePeriods': 20, 'elevatedRatio': 1.2, 'spikeRatio': 1.5},
}


def _technical_indicator_rows(bars):
    """Match the frontend chart-math EMA/MACD/RSI conventions for daily bars."""
    out = []
    fast = slow = signal = gain = loss = None
    rsi_n = TECHNICAL_SCANNER_RULES['rsi']['period']
    fast_n = TECHNICAL_SCANNER_RULES['macd']['fast']
    slow_n = TECHNICAL_SCANNER_RULES['macd']['slow']
    signal_n = TECHNICAL_SCANNER_RULES['macd']['signal']
    for i, bar in enumerate(bars):
        close = number(bar.get('close'))
        if close is None or close <= 0:
            continue
        fast = close if fast is None else fast + 2 / (fast_n + 1) * (close - fast)
        slow = close if slow is None else slow + 2 / (slow_n + 1) * (close - slow)
        macd = fast - slow
        signal = macd if signal is None else signal + 2 / (signal_n + 1) * (macd - signal)
        hist = macd - signal

        delta = close - number(bars[i - 1].get('close')) if i else 0
        up, down = max(0, delta), max(0, -delta)
        if i == rsi_n:
            total_gain = total_loss = 0.0
            valid = True
            for j in range(1, i + 1):
                a, b = number(bars[j - 1].get('close')), number(bars[j].get('close'))
                if a is None or b is None:
                    valid = False
                    break
                d = b - a
                total_gain += max(0, d)
                total_loss += max(0, -d)
            if valid:
                gain, loss = total_gain / rsi_n, total_loss / rsi_n
        elif i > rsi_n and gain is not None and loss is not None:
            gain = (gain * (rsi_n - 1) + up) / rsi_n
            loss = (loss * (rsi_n - 1) + down) / rsi_n

        rsi = None
        if i >= rsi_n and gain is not None and loss is not None:
            rsi = 50 if gain == 0 and loss == 0 else 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
        out.append({
            'time': bar.get('time'), 'close': close, 'macd': macd, 'signal': signal,
            'hist': hist, 'rsi': rsi, 'volume': max(0, number(bar.get('volume')) or 0)
        })
    return out


def _technical_signal(label, signal_id, direction, strength):
    return {'id': signal_id, 'label': label, 'direction': direction, 'strength': strength}


def technical_scan_symbol(symbol, bars, quote=None, previous=None):
    rows = _technical_indicator_rows(bars)
    if len(rows) < 35:
        return None
    current, daily_prev = rows[-1], rows[-2]
    close = current['close']
    if not close:
        return None

    # Prefer the previous live scanner snapshot when it belongs to the same
    # current-session daily bar; otherwise fall back to the previous completed day.
    current_source_time = (quote or {}).get('sourceTime') or (quote or {}).get('collectedAt')
    scan_prev_ok = (
        isinstance(previous, dict)
        and previous.get('barDate') == current.get('time')
        and number(previous.get('macdHistogram')) is not None
    )
    same_market_snapshot = (
        scan_prev_ok
        and current_source_time
        and str(previous.get('sourceTime') or '') == str(current_source_time)
    )
    stored_prev_hist = number(previous.get('previousMacdHistogram')) if same_market_snapshot else None
    stored_prev_rsi = number(previous.get('previousRsi14')) if same_market_snapshot else None
    collapsed_comparator = (
        same_market_snapshot
        and stored_prev_hist is not None
        and stored_prev_rsi is not None
        and number(previous.get('macdHistogram')) is not None
        and number(previous.get('rsi14')) is not None
        and abs(stored_prev_hist - number(previous.get('macdHistogram'))) < 1e-9
        and abs(stored_prev_rsi - number(previous.get('rsi14'))) < 1e-9
    )
    if same_market_snapshot and stored_prev_hist is not None and not collapsed_comparator:
        prev_hist = stored_prev_hist
    else:
        prev_hist = number(previous.get('macdHistogram')) if scan_prev_ok and not same_market_snapshot else daily_prev['hist']
    if same_market_snapshot and stored_prev_rsi is not None and not collapsed_comparator:
        prev_rsi = stored_prev_rsi
    else:
        prev_rsi = number(previous.get('rsi14')) if scan_prev_ok and not same_market_snapshot else daily_prev['rsi']
    hist = current['hist']
    hist_pct = hist / close * 100 if close else None
    near_limit = TECHNICAL_SCANNER_RULES['macd']['nearCrossMaxSpreadPct']

    completed = [max(0, number(row.get('volume')) or 0) for row in bars[-21:-1]]
    avg_volume20 = sum(completed) / len(completed) if len(completed) == 20 and any(completed) else None
    volume_ratio = current['volume'] / avg_volume20 if avg_volume20 else None

    signals = []
    cross_up = prev_hist is not None and prev_hist <= 0 < hist
    cross_down = prev_hist is not None and prev_hist >= 0 > hist
    if cross_up:
        signals.append(_technical_signal('MACD vừa cắt lên Signal', 'macd_cross_up', 'bullish', 'high'))
    elif cross_down:
        signals.append(_technical_signal('MACD vừa cắt xuống Signal', 'macd_cross_down', 'bearish', 'high'))
    elif prev_hist is not None and hist_pct is not None:
        if hist < 0 and prev_hist < 0 and hist > prev_hist and abs(hist_pct) <= near_limit:
            signals.append(_technical_signal('MACD đang tiến sát giao cắt lên', 'macd_near_up', 'bullish', 'medium'))
        elif hist > 0 and prev_hist > 0 and hist < prev_hist and abs(hist_pct) <= near_limit:
            signals.append(_technical_signal('MACD đang tiến sát giao cắt xuống', 'macd_near_down', 'bearish', 'medium'))

    rsi = current['rsi']
    if rsi is not None:
        if rsi <= TECHNICAL_SCANNER_RULES['rsi']['oversold']:
            signals.append(_technical_signal('RSI đang ở vùng quá bán', 'rsi_oversold', 'bullish_watch', 'medium'))
        elif rsi >= TECHNICAL_SCANNER_RULES['rsi']['overbought']:
            signals.append(_technical_signal('RSI đang ở vùng quá mua', 'rsi_overbought', 'bearish_watch', 'medium'))
        if prev_rsi is not None and prev_rsi < 30 <= rsi:
            signals.append(_technical_signal('RSI vừa thoát vùng quá bán', 'rsi_exit_oversold', 'bullish', 'high'))
        if prev_rsi is not None and prev_rsi > 70 >= rsi:
            signals.append(_technical_signal('RSI vừa rời vùng quá mua', 'rsi_exit_overbought', 'bearish', 'high'))

    quote_change = number((quote or {}).get('changePct'))
    if quote_change is None and daily_prev.get('close'):
        quote_change = (close / daily_prev['close'] - 1) * 100
    volume_direction = 'bullish' if (quote_change or 0) > 0.15 else 'bearish' if (quote_change or 0) < -0.15 else 'confirmation'
    volume_side = 'cùng giá tăng' if volume_direction == 'bullish' else 'trong phiên giảm' if volume_direction == 'bearish' else 'khi giá đi ngang'

    if volume_ratio is not None and volume_ratio >= TECHNICAL_SCANNER_RULES['volume']['spikeRatio']:
        signals.append(_technical_signal(f'Khối lượng ≥ 1,5x TB20 {volume_side}', 'volume_spike', volume_direction, 'high'))
    elif volume_ratio is not None and volume_ratio >= TECHNICAL_SCANNER_RULES['volume']['elevatedRatio']:
        signals.append(_technical_signal(f'Khối lượng ≥ 1,2x TB20 {volume_side}', 'volume_elevated', volume_direction, 'medium'))

    # Watch states such as RSI oversold/overbought are conditions to monitor,
    # not directional confirmation by themselves.
    bullish = sum(x['direction'] == 'bullish' for x in signals)
    bearish = sum(x['direction'] == 'bearish' for x in signals)
    bias = 'bullish' if bullish > bearish else 'bearish' if bearish > bullish else 'mixed' if bullish and bearish else 'neutral'

    priority = 0
    weights = {
        'macd_cross_up': 60, 'macd_cross_down': 60,
        'macd_near_up': 42, 'macd_near_down': 42,
        'rsi_exit_oversold': 40, 'rsi_exit_overbought': 40,
        'rsi_oversold': 28, 'rsi_overbought': 28,
        'volume_spike': 22, 'volume_elevated': 12,
    }
    for sig in signals:
        priority += weights.get(sig['id'], 0)
    priority = min(100, priority)

    quote = quote or {}
    return {
        'symbol': symbol, 'barDate': current.get('time'),
        'sourceTime': quote.get('sourceTime') or quote.get('collectedAt'),
        'price': number(quote.get('price')) or close,
        'changePct': number(quote.get('changePct')),
        'rsi14': round(rsi, 2) if rsi is not None else None,
        'previousRsi14': round(prev_rsi, 2) if prev_rsi is not None else None,
        'macd': round(current['macd'], 4), 'macdSignal': round(current['signal'], 4),
        'macdHistogram': round(hist, 4),
        'macdSpreadPct': round(hist_pct, 4) if hist_pct is not None else None,
        'previousMacdHistogram': round(prev_hist, 4) if prev_hist is not None else None,
        'volume': current['volume'],
        'averageVolume20': round(avg_volume20) if avg_volume20 is not None else None,
        'volumeRatio20': round(volume_ratio, 3) if volume_ratio is not None else None,
        'bias': bias, 'priority': priority, 'signals': signals,
        'matched': bool(signals),
    }


def build_technical_scanner(out, companies, quotes):
    path = out / 'technical-signals.json'
    old = read(path, {'symbols': {}})
    previous_symbols = old.get('symbols') or {}
    symbols, matches = {}, []
    for company in companies:
        symbol = company['symbol']
        bars = read(out / 'history' / (symbol + '.json'), {}).get('bars') or []
        row = technical_scan_symbol(symbol, bars, quotes.get(symbol), previous_symbols.get(symbol))
        if not row:
            continue
        row['tier'] = company.get('tier') or 'CORE'
        row['cadence'] = 'LIVE_15M'
        symbols[symbol] = row
        if row['matched']:
            matches.append(row)

    # Discovery stays fail-closed for live price/forecast decisions, but its
    # validated EOD technical snapshot remains searchable in the scanner.
    universe = load_market_universe()
    discovery = universe.get('discoveryTechnical') if isinstance(universe, dict) else {}
    records = universe.get('symbols') if isinstance(universe, dict) else {}
    if isinstance(discovery, dict):
        for symbol, source in discovery.items():
            if symbol in symbols or not isinstance(source, dict):
                continue
            meta = (records or {}).get(symbol) or {}
            if not meta.get('scannerEligible'):
                continue
            row = {**source, 'symbol': symbol, 'tier': 'DISCOVERY', 'cadence': 'EOD'}
            symbols[symbol] = row
            if row.get('matched'):
                matches.append(row)

    matches.sort(key=lambda row: (-row.get('priority', 0), row['symbol']))
    stamp = now()
    scanner_universe = universe.get('scannerSymbols') if isinstance(universe, dict) else None
    live_coverage = sum(row.get('cadence') == 'LIVE_15M' for row in symbols.values())
    discovery_coverage = sum(row.get('cadence') == 'EOD' for row in symbols.values())
    write(path, {
        'checkedAt': stamp,
        'sourceTime': newest_source_time(quotes),
        'status': 'ok' if symbols else 'retained',
        'methodVersion': 'technical-scanner-v2-tiered-hose',
        'universe': len(scanner_universe) if isinstance(scanner_universe, list) and scanner_universe else len(companies),
        'coverage': len(symbols),
        'liveCoverage': live_coverage,
        'discoveryCoverage': discovery_coverage,
        'liveUniverse': len(companies),
        'matchCount': len(matches), 'refreshEveryMinutes': 5,
        'rules': TECHNICAL_SCANNER_RULES,
        'disclaimer': 'Technical conditions are screening signals, not trade instructions. Core/Liquid uses the evolving current-session daily candle; Discovery is EOD-only until promotion.',
        'matches': matches, 'symbols': symbols,
    })
    return matches


def scanner(out, companies):
    payload = read(out / 'quotes.json', {})
    quotes = payload.get('quotes') if isinstance(payload, dict) else {}
    if not isinstance(quotes, dict) or not quotes:
        raise RuntimeError('Existing quotes snapshot is unavailable for scanner rebuild')
    matches = build_technical_scanner(out, companies, quotes)
    today_watch = build_today_watchlist(out, companies, quotes)
    print(
        f'Technical scanner rebuilt from existing market snapshot: {len(matches)} matches; '
        f'today watch: {len(today_watch)}',
        flush=True,
    )


def build_today_watchlist(out, companies, quotes):
    """Rank Core/VN100 names worth reviewing from the latest live technical snapshot.

    This is a transparent screening list, not an investment recommendation. It
    updates with the live price/scanner snapshot and preserves prior ranks
    so the UI can show NEW / rank-up / rank-down changes between snapshots.
    """
    path = out / 'watch-today.json'
    previous = read(path, {'items': []})
    scanner = read(out / 'technical-signals.json', {'symbols': {}})
    rows = scanner.get('symbols') or {}
    core_symbols = {
        str(company.get('symbol') or '').upper()
        for company in companies
        if company.get('coreMember') or str(company.get('tier') or '').upper() == 'CORE'
    }
    previous_source_date = previous.get('sourceDate')
    previous_ranks = {
        row.get('symbol'): int(row.get('rank'))
        for row in previous.get('items', [])
        if row.get('symbol') and isinstance(row.get('rank'), int)
    }

    candidates = []
    for symbol in sorted(core_symbols):
        row = rows.get(symbol) or {}
        quote = quotes.get(symbol) or {}
        if row.get('cadence') != 'LIVE_15M' or quote.get('status') != 'ok':
            continue
        signals = row.get('signals') or []
        signal_ids = {signal.get('id') for signal in signals}
        change = number(quote.get('changePct'))
        volume_ratio = number(row.get('volumeRatio20'))
        rsi = number(row.get('rsi14'))
        bias = str(row.get('bias') or 'neutral')

        # Avoid presenting sharp downside/clear bearish setups as "good today".
        if change is not None and change <= -3:
            continue
        if bias == 'bearish':
            continue
        # Plain oversold is a watch condition, not proof of recovery. Require
        # an actual exit/rebound signal before an RSI<30 name can enter the list.
        if rsi is not None and rsi < 30 and 'rsi_exit_oversold' not in signal_ids:
            continue

        score = 0.0
        reasons = []
        has_positive_signal = False
        for signal in signals:
            direction = signal.get('direction')
            strength = signal.get('strength')
            label = signal.get('label')
            if direction == 'bullish':
                score += 34 if strength == 'high' else 18
                has_positive_signal = True
                if label:
                    reasons.append(label)
            elif direction == 'bullish_watch':
                score += 10
                if signal.get('id') == 'rsi_exit_oversold':
                    has_positive_signal = True
                if label:
                    reasons.append(label)
            elif direction == 'confirmation':
                score += 16 if strength == 'high' else 8
                if label:
                    reasons.append(label)
            elif direction == 'bearish':
                score -= 30 if strength == 'high' else 16
            elif direction == 'bearish_watch':
                score -= 10

        if bias == 'bullish':
            score += 20
        elif bias == 'mixed':
            score += 2

        if change is not None:
            if change > 0:
                score += min(15, change * 4)
            elif change < 0:
                score += max(-12, change * 3)

        if volume_ratio is not None:
            if volume_ratio >= 1.5:
                score += 10
            elif volume_ratio >= 1.2:
                score += 5

        if rsi is not None:
            if 45 <= rsi <= 68:
                score += 6
            elif rsi > 75:
                score -= 12

        momentum_breakout = bool(
            change is not None and change >= 1
            and volume_ratio is not None and volume_ratio >= 1.2
            and (rsi is None or 35 <= rsi <= 72)
        )
        if momentum_breakout:
            has_positive_signal = True
            reasons.append('Giá tăng kèm thanh khoản cao')

        if not has_positive_signal or score < 28:
            continue

        bar_date = row.get('barDate')
        candidates.append({
            'symbol': symbol,
            'score': max(0, min(100, round(score))),
            'price': number(quote.get('price')),
            'changePct': round(change, 2) if change is not None else None,
            'rsi14': round(rsi, 2) if rsi is not None else None,
            'volumeRatio20': round(volume_ratio, 2) if volume_ratio is not None else None,
            'bias': bias,
            'barDate': bar_date,
            'sourceTime': quote.get('sourceTime') or quote.get('collectedAt'),
            'reasons': list(dict.fromkeys(reasons))[:3],
        })

    candidates.sort(key=lambda row: (-row['score'], -(row.get('changePct') or 0), row['symbol']))
    selected = candidates[:8]
    source_dates = [row.get('barDate') for row in selected if row.get('barDate')]
    source_date = max(source_dates) if source_dates else None
    same_session = bool(source_date and source_date == previous_source_date)
    for rank, row in enumerate(selected, start=1):
        old_rank = previous_ranks.get(row['symbol']) if same_session else None
        row['rank'] = rank
        row['previousRank'] = old_rank
        row['rankChange'] = (old_rank - rank) if old_rank is not None else None
        row['isNew'] = old_rank is None

    stamp = now()
    write(path, {
        'checkedAt': stamp,
        'sourceTime': newest_source_time(quotes),
        'sourceDate': source_date,
        'status': 'ok',
        'universe': 'VN100/Core',
        'refreshEveryMinutes': 5,
        'methodVersion': 'finquery-today-watch-v1',
        'rules': {
            'requiresPositiveTechnicalEvidence': True,
            'excludesBearishBias': True,
            'excludesChangePctAtOrBelow': -3,
            'excludesUnconfirmedOversold': True,
            'minimumScore': 28,
            'maxItems': 8,
            'inputs': ['MACD', 'RSI', 'volume/TB20', 'intraday change', 'technical bias'],
        },
        'disclaimer': 'Danh sách sàng lọc để xem nhanh, không phải khuyến nghị mua/bán.',
        'items': selected,
    })
    return selected


def merge_live_daily_quotes(out, quotes):
    """Persist the current trading-day OHLCV into retained daily history.

    The quote board already returns a cumulative session snapshot for all VN100
    symbols in one fast request. Persisting that snapshot makes the daily chart
    current even when a later per-symbol EOD history request times out. An
    official history refresh can overwrite the same date afterwards.
    """
    merged_count = 0
    for symbol, quote in (quotes or {}).items():
        if quote.get('status') != 'ok':
            continue
        price = number(quote.get('price'))
        source_time = timestamp(quote.get('sourceTime') or quote.get('collectedAt'))
        if price is None or price <= 0 or not source_time:
            continue
        try:
            day = datetime.fromisoformat(source_time).astimezone(VN).date().isoformat()
        except (ValueError, TypeError):
            continue
        if not trading_weekday(day):
            continue
        path = out / 'history' / (symbol + '.json')
        previous = read(path, {})
        previous_bars = [bar for bar in previous.get('bars', []) if isinstance(bar, dict) and bar.get('time') and trading_weekday(bar.get('time'))]
        if not previous_bars:
            continue
        last_day = str(previous_bars[-1].get('time') or '')
        if last_day and day < last_day:
            continue
        by_day = {bar['time']: bar for bar in previous_bars}
        existing = by_day.get(day, {})
        open_ = positive_number(quote.get('open')) or positive_number(existing.get('open')) or positive_number(quote.get('reference')) or price
        high_values = [positive_number(quote.get('high')), positive_number(existing.get('high')), open_, price]
        low_values = [positive_number(quote.get('low')), positive_number(existing.get('low')), open_, price]
        high = max(v for v in high_values if v is not None)
        low = min(v for v in low_values if v is not None)
        volume = max(number(quote.get('volume')) or 0, number(existing.get('volume')) or 0)
        by_day[day] = {
            'time': day, 'open': open_, 'high': high, 'low': low,
            'close': price, 'volume': volume
        }
        bars = [by_day[key] for key in sorted(by_day)]
        stamp = now()
        write(path, {
            **previous,
            'checkedAt': stamp,
            'liveQuoteMergedAt': stamp,
            'liveQuoteSourceTime': quote.get('sourceTime') or quote.get('collectedAt'),
            'liveQuoteProvider': quote.get('source') or 'Vietcap',
            'barCount': len(bars),
            'firstBar': bars[0]['time'],
            'lastBar': bars[-1]['time'],
            'bars': bars
        })
        merged_count += 1
    return merged_count


def prices(out, companies):
    """Fast quote snapshot with an optional current-session freshness gate.

    Scheduled intraday runs set MARKET_REQUIRE_TODAY=1. In that mode a provider
    response from T-1 is not accepted as a successful refresh and is never
    merged into today's candle.
    """
    universe = load_market_universe() or fallback_market_universe(companies)
    sync_market_universe(out, universe)
    seeded_histories = seed_market_histories(out, universe, companies)
    symbols = [c['symbol'] for c in companies]
    board_path = out / 'quotes.json'
    old = read(board_path, {'quotes': {}})
    collected = now()
    errors = []
    require_today = os.environ.get('MARKET_REQUIRE_TODAY', '0') == '1'
    stale = {}
    try:
        payload = json.loads(request(API + 'price/symbols/getList', {'symbols': symbols}))
        fresh = normalize_board(payload, symbols, collected)
        missing = [symbol for symbol in symbols if symbol not in fresh]
        if missing:
            try:
                retry_payload = json.loads(request(API + 'price/symbols/getList', {'symbols': missing}))
                fresh.update(normalize_board(retry_payload, missing, collected))
            except Exception as retry_error:
                errors.append(f'quote retry {len(missing)} symbols: {retry_error}')
        if require_today:
            max_quote_age = os.environ.get('MARKET_MAX_QUOTE_AGE_MINUTES')
            fresh, stale = current_session_quotes(fresh, max_age_minutes=max_quote_age)
            if stale:
                sample = ','.join(sorted(stale)[:8])
                errors.append(f'Vietcap stale session quotes rejected: {len(stale)} ({sample})')
    except Exception as e:
        fresh = {}
        errors.append('Vietcap quotes: ' + str(e))

    # KBS is the live fallback when Vietcap is stale or incomplete. A KBS board
    # is accepted only after its trade-history endpoint proves today's session.
    missing_current = [symbol for symbol in symbols if symbol not in fresh]
    if require_today and missing_current:
        try:
            kbs_rows = kbs_current_board(missing_current, collected)
            max_quote_age = os.environ.get('MARKET_MAX_QUOTE_AGE_MINUTES')
            kbs_rows, kbs_stale = current_session_quotes(kbs_rows, max_age_minutes=max_quote_age)
            stale.update(kbs_stale)
            fresh.update(kbs_rows)
            errors.append(f'KBS current-session fallback filled {len(kbs_rows)}/{len(missing_current)} symbols')
        except Exception as kbs_error:
            errors.append('KBS fallback: ' + str(kbs_error))

    quotes = {}
    for symbol in symbols:
        if symbol in fresh:
            quotes[symbol] = fresh[symbol]
        elif symbol in old.get('quotes', {}):
            quotes[symbol] = {**old['quotes'][symbol], 'status': 'retained'}

    bundle_status = 'ok' if fresh else 'retained'
    write(board_path, {
        'checkedAt': collected, 'source': 'Vietcap+KBS', 'status': bundle_status,
        'providers': sorted({row.get('source') for row in fresh.values() if row.get('source')}),
        'quotes': quotes, 'errors': errors, 'coverage': len(fresh), 'expected': len(symbols),
        'requireCurrentSession': require_today, 'staleRejected': len(stale),
        'latestSourceTime': newest_source_time(fresh) or newest_source_time(stale)
    })
    live_daily_merged = merge_live_daily_quotes(out, fresh)
    history_effective = update_history_effective_status(out, symbols)
    technical_matches = build_technical_scanner(out, companies, fresh)
    today_watch = build_today_watchlist(out, companies, fresh)
    available_histories = sum(1 for symbol in symbols if read(out / 'history' / (symbol + '.json'), {}).get('bars'))
    write(out / 'prices-status.json', {
        'checkedAt': now(), 'status': bundle_status, 'quotes': len(fresh), 'histories': available_histories,
        'expected': len(symbols), 'retainedQuotes': max(0, len(quotes) - len(fresh)),
        'staleRejected': len(stale), 'latestSourceTime': newest_source_time(fresh) or newest_source_time(stale),
        'liveDailyBarsMerged': live_daily_merged,
        'effectiveHistories': history_effective.get('effectiveAvailable'),
        'latestHistoryBar': history_effective.get('latestBar'),
        'latestHistoryBarCoverage': history_effective.get('latestBarCoverage'),
        'errors': errors, 'quoteRefresh': '15_minute_session_job',
        'historyRefresh': 'server_live_quote_merge_plus_client_replay_then_separate_eod_official',
        'universeVersion': universe.get('version') if isinstance(universe, dict) else None,
        'universeCounts': universe.get('counts') if isinstance(universe, dict) else None,
        'seededHistories': seeded_histories,
    })
    drivers = build_drivers(out, companies)
    print(f'Prices: {len(fresh)}/{len(symbols)} current-session; stale rejected: {len(stale)}; seeded histories: {seeded_histories}; live daily bars: {live_daily_merged}; technical matches: {len(technical_matches)}; today watch: {len(today_watch)}; retained histories: {available_histories}/{len(symbols)}; drivers: {len(drivers)}', flush=True)
    if not fresh:
        raise RuntimeError('Current-session quote collection incomplete; previous successful data retained')


def _history_page(symbol, frame, to, count, minute=False):
    attempts = max(1, int(os.environ.get('INTRADAY_RETRIES', '3'))) if minute else max(1, int(os.environ.get('HISTORY_RETRIES', '3')))
    last_error = None
    for attempt in range(attempts):
        try:
            payload = json.loads(request(API + 'chart/OHLCChart/gap-chart', {
                'timeFrame': frame, 'symbols': [symbol], 'to': int(to), 'countBack': int(count)
            }))
            return normalize_history(payload, symbol, minute=minute)
        except Exception as e:
            last_error = e
            if attempt + 1 < attempts:
                time.sleep(.6 * (attempt + 1))
    raise last_error


def _full_intraday_history(symbol, target):
    """Page backwards through Vietcap minute history without discarding older bars.

    The live endpoint returns a bounded window. Backfill mode walks the `to`
    cursor backwards and is intentionally page-capped so one symbol cannot
    monopolize a scheduled publisher run.
    """
    merged = {}
    cursor = int(time.time())
    page_size = min(700, max(100, int(os.environ.get('INTRADAY_PAGE_SIZE', '700'))))
    max_pages = max(1, int(os.environ.get('INTRADAY_MAX_PAGES', '12')))
    for _ in range(min(max_pages, max(1, math.ceil(target / page_size) + 1))):
        try:
            bars = _history_page(symbol, 'ONE_MINUTE', cursor, page_size, minute=True)
        except Exception:
            if merged:
                break
            raise
        before = len(merged)
        merged.update({bar['time']: bar for bar in bars})
        if len(merged) >= target or len(merged) == before:
            break
        earliest = min(bar['time'] for bar in bars)
        try:
            cursor_next = int(datetime.fromisoformat(earliest).timestamp()) - 1
        except (ValueError, TypeError):
            break
        if cursor_next >= cursor:
            break
        cursor = cursor_next
    return [merged[key] for key in sorted(merged)][-target:]


def _intraday_backfill_cursor(out, symbol, previous_bars):
    """Choose a cursor strictly before the earliest completed retained bucket."""
    archive = read(out / 'intraday-5m' / (symbol + '.json'), {})
    archived = [bar for bar in archive.get('bars', []) if isinstance(bar, dict) and bar.get('time')]
    if archived:
        first = archived[0]
        try:
            end = datetime.fromisoformat(str(first['time']).replace('Z', '+00:00')).astimezone(VN)
            mins = end.hour * 60 + end.minute
            session = str(first.get('session') or '')
            if session == 'ATO':
                start_min = 9 * 60
            elif session == 'ATC':
                start_min = 14 * 60 + 30
            elif session in ('CONTINUOUS_AM', 'CONTINUOUS_PM'):
                start_min = mins - 5
            else:
                start_min = mins - 5
            start_local = datetime(end.year, end.month, end.day, start_min // 60, start_min % 60, tzinfo=VN)
            return int(start_local.timestamp()) - 1
        except (ValueError, TypeError):
            pass
    if previous_bars:
        try:
            return int(datetime.fromisoformat(str(previous_bars[0]['time']).replace('Z', '+00:00')).timestamp()) - 1
        except (ValueError, TypeError):
            pass
    return int(time.time())


def _backfill_intraday_chunk(out, symbol, previous_bars):
    """Fetch an older block and write it directly into the 5m archive.

    Vietcap accepts a 5,000-bar ONE_MINUTE request in one call. Use that fast
    path first; fall back to smaller backwards pages if a symbol/provider
    rejects the larger request.
    """
    cursor = _intraday_backfill_cursor(out, symbol, previous_bars)
    direct_count = max(700, min(5000, int(os.environ.get('INTRADAY_BACKFILL_COUNT', '5000'))))
    try:
        rows = _history_page(symbol, 'ONE_MINUTE', cursor, direct_count, minute=True)
        if rows:
            return rows
    except Exception:
        pass
    page_size = min(700, max(100, int(os.environ.get('INTRADAY_PAGE_SIZE', '700'))))
    pages = max(1, min(6, int(os.environ.get('INTRADAY_BACKFILL_PAGES', '2'))))
    merged = {}
    for _ in range(pages):
        try:
            rows = _history_page(symbol, 'ONE_MINUTE', cursor, page_size, minute=True)
        except Exception:
            if merged:
                break
            raise
        before = len(merged)
        merged.update({bar['time']: bar for bar in rows})
        if not rows or len(merged) == before:
            break
        earliest = min(bar['time'] for bar in rows)
        try:
            cursor_next = int(datetime.fromisoformat(earliest.replace('Z', '+00:00')).timestamp()) - 1
        except (ValueError, TypeError):
            break
        if cursor_next >= cursor:
            break
        cursor = cursor_next
    return [merged[key] for key in sorted(merged)]


def _intraday_bucket(bar):
    """Return the HOSE auction/continuous bucket available after this bar.

    Continuous data are aggregated to five-minute end timestamps. Opening and
    closing auctions are kept as separate buckets because their volume process
    is structurally different from continuous matching.
    """
    stamp = timestamp(bar.get('time'))
    if not stamp:
        return None
    dt = datetime.fromisoformat(stamp).astimezone(VN)
    mins = dt.hour * 60 + dt.minute
    day = dt.date()
    session = None
    end_min = None
    if 9 * 60 <= mins < 9 * 60 + 15:
        session, end_min = 'ATO', 9 * 60 + 15
    elif 9 * 60 + 15 <= mins < 11 * 60 + 30:
        start = 9 * 60 + 15
        session, end_min = 'CONTINUOUS_AM', start + ((mins - start) // 5 + 1) * 5
    elif 13 * 60 <= mins < 14 * 60 + 30:
        start = 13 * 60
        session, end_min = 'CONTINUOUS_PM', start + ((mins - start) // 5 + 1) * 5
    elif 14 * 60 + 30 <= mins <= 14 * 60 + 45:
        session, end_min = 'ATC', 14 * 60 + 45
    else:
        return None
    end_local = datetime(day.year, day.month, day.day, end_min // 60, end_min % 60, tzinfo=VN)
    return end_local.astimezone(timezone.utc).isoformat(), session


def resample_intraday_5m(bars):
    buckets = {}
    for bar in sorted((bars or []), key=lambda x: str(x.get('time') or '')):
        key = _intraday_bucket(bar)
        if not key:
            continue
        end_time, session = key
        o, h, l, close, vol = [number(bar.get(k)) for k in ('open', 'high', 'low', 'close', 'volume')]
        if None in (o, h, l, close, vol):
            continue
        row = buckets.get(end_time)
        if row is None:
            buckets[end_time] = {
                'time': end_time, 'open': o, 'high': h, 'low': l, 'close': close,
                'volume': max(0, vol), 'session': session
            }
        else:
            row['high'] = max(row['high'], h)
            row['low'] = min(row['low'], l)
            row['close'] = close
            row['volume'] += max(0, vol)
    return [buckets[key] for key in sorted(buckets)]


def _write_intraday_5m_archive(out, symbol, minute_bars):
    path = out / 'intraday-5m' / (symbol + '.json')
    previous = read(path, {})
    prior = [bar for bar in previous.get('bars', []) if isinstance(bar, dict) and bar.get('time')]
    fresh = resample_intraday_5m(minute_bars)
    merged = {bar['time']: bar for bar in prior}
    merged.update({bar['time']: bar for bar in fresh})
    bars = [merged[key] for key in sorted(merged)]
    retain = max(500, int(os.environ.get('INTRADAY_5M_RETAIN_BARS', '6000')))
    if len(bars) > retain:
        bars = bars[-retain:]
    row = {
        'symbol': symbol, 'source': 'Vietcap 1m resampled by FinQuery', 'unit': 'VND',
        'interval': '5m', 'checkedAt': now(), 'status': 'ok', 'barCount': len(bars),
        'firstBar': bars[0]['time'] if bars else None,
        'lastBar': bars[-1]['time'] if bars else None,
        'sessions': ['ATO', 'CONTINUOUS_AM', 'CONTINUOUS_PM', 'ATC'],
        'bars': bars
    }
    write(path, row)
    return row


def _kbs_number(value):
    if isinstance(value, str):
        text = value.strip().replace(' ', '')
        if re.fullmatch(r'-?\d{1,3}(?:,\d{3})+(?:\.\d+)?', text):
            text = text.replace(',', '')
        elif re.fullmatch(r'-?\d+,\d+', text):
            text = text.replace(',', '.')
        return number(text)
    return number(value)


def _kbs_day(value):
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 1e12:
            n /= 1000
        try:
            return datetime.fromtimestamp(n, VN).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value or '').strip()
    for pattern in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(text[:10], pattern).date().isoformat()
        except ValueError:
            pass
    parsed = timestamp(value)
    return parsed[:10] if parsed else None


def normalize_kbs_history(payload, symbol):
    if isinstance(payload, dict):
        rows = payload.get('data_day') or payload.get('data') or []
        payload_symbol = str(payload.get('symbol') or symbol).upper()
        if payload_symbol and payload_symbol != symbol:
            raise ValueError(f'{symbol}: KBS returned {payload_symbol}')
    else:
        rows = payload if isinstance(payload, list) else []
    bars = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _kbs_day(row.get('t') or row.get('time') or row.get('date'))
        close = _kbs_number(row.get('c') if 'c' in row else row.get('close'))
        if not day or not trading_weekday(day) or close is None or close <= 0:
            continue
        open_ = _kbs_number(row.get('o') if 'o' in row else row.get('open')) or close
        high = _kbs_number(row.get('h') if 'h' in row else row.get('high')) or close
        low = _kbs_number(row.get('l') if 'l' in row else row.get('low')) or close
        volume = _kbs_number(row.get('v') if 'v' in row else row.get('volume')) or 0
        bars.append({'time': day, 'open': open_, 'high': high, 'low': low, 'close': close, 'volume': max(0, volume)})
    if not bars:
        raise RuntimeError(f'{symbol}: KBS returned no usable daily bars')
    sample = sorted(bar['close'] for bar in bars[-120:] if bar['close'] > 0)
    median = sample[len(sample)//2] if sample else bars[-1]['close']
    if median < 1000:
        for bar in bars:
            for field in ('open', 'high', 'low', 'close'):
                bar[field] *= 1000
    merged = {bar['time']: bar for bar in bars}
    return [merged[key] for key in sorted(merged)]


def _kbs_full_history(symbol):
    start = os.environ.get('HISTORY_START_DATE', '1998-01-01')
    end = datetime.now(VN).date().isoformat()
    start_date = datetime.fromisoformat(start).strftime('%d-%m-%Y')
    end_date = datetime.fromisoformat(end).strftime('%d-%m-%Y')
    raw = request_query(
        f'{KBS_API}/stocks/{symbol}/data_day',
        {'sdate': start_date, 'edate': end_date},
        'https://kbbuddywts.kbsec.com.vn/'
    )
    return normalize_kbs_history(json.loads(raw), symbol)


def _full_daily_history(symbol, target):
    """Fetch daily bars backwards in bounded pages so older years are not silently truncated."""
    merged = {}
    cursor = int(time.time())
    page_size = min(max(300, int(os.environ.get('HISTORY_PAGE_SIZE', '1600'))), 1600, target)
    for _ in range(max(1, math.ceil(target / page_size) + 2)):
        try:
            bars = _history_page(symbol, 'ONE_DAY', cursor, page_size, minute=False)
        except Exception:
            if merged:
                break
            raise
        before = len(merged)
        merged.update({bar['time']: bar for bar in bars})
        if len(merged) >= target or len(merged) == before:
            break
        earliest = min(bar['time'] for bar in bars)
        cursor_next = int(datetime.fromisoformat(earliest).replace(tzinfo=VN).timestamp()) - 1
        if cursor_next >= cursor:
            break
        cursor = cursor_next
    return [merged[key] for key in sorted(merged)][-target:]


def _normalize_vnstock_history(df, symbol, provider):
    if df is None or len(df) == 0:
        raise RuntimeError(f'{symbol}: {provider} returned no rows')
    cols = {str(col).strip().lower(): col for col in df.columns}
    time_col = cols.get('time') or cols.get('date') or cols.get('trading_date')
    if time_col is None or cols.get('close') is None:
        raise RuntimeError(f'{symbol}: unexpected {provider} columns {list(df.columns)}')
    bars = []
    for _, row in df.iterrows():
        raw_time = row.get(time_col)
        day = raw_time.date().isoformat() if hasattr(raw_time, 'date') else str(raw_time or '')[:10]
        close = number(row.get(cols['close']))
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day or '') or not trading_weekday(day) or close is None or close <= 0:
            continue
        open_ = number(row.get(cols.get('open'))) if cols.get('open') is not None else close
        high = number(row.get(cols.get('high'))) if cols.get('high') is not None else close
        low = number(row.get(cols.get('low'))) if cols.get('low') is not None else close
        volume = number(row.get(cols.get('volume'))) if cols.get('volume') is not None else 0
        bars.append({'time': day, 'open': open_ or close, 'high': high or close, 'low': low or close, 'close': close, 'volume': max(0, volume or 0)})
    if not bars:
        raise RuntimeError(f'{symbol}: {provider} returned no usable bars')
    sample = sorted(x['close'] for x in bars[-120:] if x['close'] > 0)
    median = sample[len(sample)//2] if sample else bars[-1]['close']
    if median < 1000:
        for bar in bars:
            for field in ('open', 'high', 'low', 'close'):
                bar[field] *= 1000
    merged = {bar['time']: bar for bar in bars}
    return [merged[key] for key in sorted(merged)]


def _vnstock_full_history(symbol):
    """Best-effort long daily history from free Vnstock routes, used only for a full backfill."""
    start = os.environ.get('HISTORY_START_DATE', '1998-01-01')
    end = (datetime.now(VN).date() + timedelta(days=1)).isoformat()
    errors = []
    try:
        from vnstock.ui import Market
        df = Market().equity(symbol).ohlcv(start=start, end=end, interval='1D', count=12000)
        bars = _normalize_vnstock_history(df, symbol, 'Vnstock Unified Market')
        if bars:
            return bars, 'Vnstock Unified Market'
    except Exception as e:
        errors.append('Unified Market: ' + str(e))
    try:
        from vnstock import Vnstock
        for source in ('VCI', 'KBS'):
            try:
                stock = Vnstock().stock(symbol=symbol, source=source)
                df = stock.quote.history(start=start, end=end, interval='1D')
                bars = _normalize_vnstock_history(df, symbol, f'Vnstock {source}')
                if bars:
                    return bars, f'Vnstock {source}'
            except Exception as e:
                errors.append(f'{source}: {e}')
    except Exception as e:
        errors.append('Vnstock import: ' + str(e))
    raise RuntimeError(' | '.join(errors) or 'Vnstock long-history routes returned no data')


def _refresh_one_history(out, symbol, minute=False):
    folder = 'intraday' if minute else 'history'
    path = out / folder / (symbol + '.json')
    previous = read(path, {})
    try:
        if minute:
            count = max(100, int(os.environ.get('INTRADAY_COUNT_BACK', '360')))
            backfill = os.environ.get('INTRADAY_BACKFILL', '0') == '1'
            previous_bars = [bar for bar in previous.get('bars', []) if isinstance(bar, dict) and bar.get('time')]
            fresh_bars = _history_page(symbol, 'ONE_MINUTE', int(time.time()), count, minute=True)
            older_bars = _backfill_intraday_chunk(out, symbol, previous_bars) if backfill else []
            archive_input = older_bars + previous_bars + fresh_bars
            if os.environ.get('INTRADAY_WRITE_ARCHIVE', '1') != '0':
                _write_intraday_5m_archive(out, symbol, archive_input)
            merged = {bar['time']: bar for bar in previous_bars}
            merged.update({bar['time']: bar for bar in fresh_bars})
            recent_bars = [merged[key] for key in sorted(merged)]
            retain_1m = max(360, int(os.environ.get('INTRADAY_RETAIN_1M_BARS', '3000')))
            bars = recent_bars[-retain_1m:]
        else:
            target = int(os.environ.get('HISTORY_COUNT_BACK', '6000'))
            recent_count = max(20, min(250, int(os.environ.get('HISTORY_RECENT_COUNT', '80'))))
            providers = []
            bars = []
            force_full = os.environ.get('HISTORY_KBS_FULL') == '1'
            previous_bars = [bar for bar in previous.get('bars', []) if isinstance(bar, dict) and bar.get('time') and trading_weekday(bar.get('time'))]
            previous_last = previous_bars[-1].get('time') if previous_bars else None
            recent_cutoff = (datetime.now(VN).date() - timedelta(days=180)).isoformat()
            # Normal EOD refresh is incremental: existing symbols only need the
            # recent daily window merged onto their retained long history. This
            # avoids re-downloading ~1,600 bars x 100 symbols every business day.
            if force_full:
                try:
                    bars = _kbs_full_history(symbol)
                    providers.append('KBS')
                except Exception as kbs_error:
                    providers.append('KBS error: ' + str(kbs_error)[:180])
            elif previous_bars and previous_last and previous_last >= recent_cutoff:
                bars = _history_page(symbol, 'ONE_DAY', int(time.time()), min(recent_count, target), minute=False)
                providers.append('Vietcap recent')
            if not bars:
                bars = _full_daily_history(symbol, target)
                providers.append('Vietcap full')
            if os.environ.get('HISTORY_VNSTOCK_FALLBACK') == '1':
                try:
                    extra, provider = _vnstock_full_history(symbol)
                    merged = {bar['time']: bar for bar in bars}
                    merged.update({bar['time']: bar for bar in extra})
                    bars = [merged[key] for key in sorted(merged)]
                    providers.append(provider)
                except Exception as vn_error:
                    providers.append('Vnstock fallback error: ' + str(vn_error)[:240])
            # Never discard older successful bars if the upstream returns only
            # the recent incremental window.
            if previous_bars:
                merged = {bar['time']: bar for bar in previous_bars}
                merged.update({bar['time']: bar for bar in bars})
                bars = [merged[key] for key in sorted(merged)]
        row = {
            'symbol': symbol, 'source': 'Vietcap' if minute else ' + '.join(providers or ['Vietcap']), 'unit': 'VND',
            'interval': '1m' if minute else '1D', 'collectedAt': now(),
            'checkedAt': now(), 'status': 'ok', 'barCount': len(bars),
            'firstBar': bars[0]['time'] if bars else None,
            'lastBar': bars[-1]['time'] if bars else None,
            'bars': bars
        }
        if not minute:
            row['sourceUrl'] = 'https://trading.vietcap.com.vn/'
        write(path, row)
        return symbol, True, None
    except Exception as e:
        if previous.get('bars'):
            write(path, {**previous, 'checkedAt': now(), 'status': 'retained', 'error': str(e)})
        return symbol, False, str(e)


def update_history_effective_status(out, symbols):
    """Summarize usable retained history separately from the latest upstream refresh result."""
    path = out / 'history-status.json'
    status = read(path, {})
    available = retained = 0
    last_dates = []
    for symbol in symbols:
        row = read(out / 'history' / (symbol + '.json'), {})
        bars = row.get('bars') or []
        if not bars:
            continue
        available += 1
        if row.get('status') == 'retained':
            retained += 1
        last = row.get('lastBar') or (bars[-1].get('time') if isinstance(bars[-1], dict) else None)
        if last:
            last_dates.append(str(last))
    latest = max(last_dates) if last_dates else None
    latest_coverage = sum(1 for value in last_dates if value == latest) if latest else 0
    status.update({
        'effectiveAvailable': available,
        'effectiveRetained': retained,
        'effectiveStatus': 'ok' if available >= max(1, int(len(symbols) * 0.95)) else 'partial',
        'latestBar': latest,
        'latestBarCoverage': latest_coverage,
        'effectiveUniverse': len(symbols),
    })
    write(path, status)
    return status


def intraday_archive_summary(out, symbols):
    day_counts = []
    available = 0
    latest = []
    first = []
    at_least_40 = 0
    for symbol in symbols:
        row = read(out / 'intraday-5m' / (symbol + '.json'), {})
        bars = [bar for bar in row.get('bars', []) if isinstance(bar, dict) and bar.get('time')]
        if not bars:
            day_counts.append(0)
            continue
        available += 1
        days = sorted({datetime.fromisoformat(str(bar['time']).replace('Z', '+00:00')).astimezone(VN).date().isoformat() for bar in bars})
        count = len(days)
        day_counts.append(count)
        if count >= 40:
            at_least_40 += 1
        first.append(days[0])
        latest.append(days[-1])
    ordered = sorted(day_counts)
    median_days = ordered[len(ordered)//2] if ordered else 0
    return {
        'archive5mAvailable': available,
        'archive5mUniverse': len(symbols),
        'archive5mMinDays': min(day_counts) if day_counts else 0,
        'archive5mMedianDays': median_days,
        'archive5mMaxDays': max(day_counts) if day_counts else 0,
        'archive5mAtLeast40Days': at_least_40,
        'archive5mEarliestDay': min(first) if first else None,
        'archive5mLatestDay': max(latest) if latest else None,
    }


def intraday_session_summary(out, symbols):
    """Compare minute bars with the current published quote generation.

    A successful HTTP/OHLC request is not enough to call intraday healthy:
    the newest minute bar must also be close to the current live quote for
    symbols that actually have a current-session trade.
    """
    quotes = read(out / 'quotes.json', {})
    quote_rows = quotes.get('quotes') if isinstance(quotes.get('quotes'), dict) else {}
    today = datetime.now(VN).date().isoformat()
    max_lag = max(1.0, float(os.environ.get('INTRADAY_MAX_QUOTE_LAG_MINUTES', '20')))
    expected_symbols, current_symbols, lagged = [], [], []
    lags = []
    retained_quotes = 0
    for symbol in symbols:
        quote = quote_rows.get(symbol) or {}
        quote_stamp = timestamp(quote.get('sourceTime') or quote.get('collectedAt'))
        if quote.get('status') == 'retained':
            retained_quotes += 1
            continue
        if not quote_stamp or source_day(quote_stamp) != today:
            continue
        expected_symbols.append(symbol)
        row = read(out / 'intraday' / (symbol + '.json'), {})
        last_bar = row.get('lastBar')
        if not last_bar:
            bars = row.get('bars') or []
            last_bar = bars[-1].get('time') if bars and isinstance(bars[-1], dict) else None
        bar_stamp = timestamp(last_bar)
        if not bar_stamp or source_day(bar_stamp) != today:
            lagged.append({'symbol': symbol, 'reason': 'no_current_session_bar'})
            continue
        try:
            q_dt = datetime.fromisoformat(quote_stamp).astimezone(timezone.utc)
            b_dt = datetime.fromisoformat(bar_stamp).astimezone(timezone.utc)
            lag = max(0.0, (q_dt - b_dt).total_seconds() / 60)
        except (ValueError, TypeError):
            lagged.append({'symbol': symbol, 'reason': 'invalid_timestamp'})
            continue
        lags.append(lag)
        if lag <= max_lag:
            current_symbols.append(symbol)
        else:
            lagged.append({'symbol': symbol, 'lagMinutes': round(lag, 1)})
    expected = len(expected_symbols)
    required = max(1, math.ceil(expected * .90)) if expected else 0
    current = len(current_symbols)
    return {
        'sessionQuoteSourceTime': quotes.get('latestSourceTime') or quotes.get('sourceTime'),
        'sessionQuoteCheckedAt': quotes.get('checkedAt'),
        'sessionQuoteExpected': int(quotes.get('expected') or 0),
        'sessionQuoteCoverage': int(quotes.get('coverage') or 0),
        'sessionExpected': expected,
        'sessionRequired': required,
        'sessionFresh': current,
        'sessionCoveragePct': round(current / expected * 100, 1) if expected else None,
        'sessionMaxQuoteLagMinutes': max_lag,
        'sessionMedianLagMinutes': round(sorted(lags)[len(lags)//2], 1) if lags else None,
        'sessionMaxObservedLagMinutes': round(max(lags), 1) if lags else None,
        'sessionLaggedCount': len(lagged),
        'sessionLaggedSymbols': lagged[:20],
        'sessionRetainedQuotes': retained_quotes,
    }


def refresh_history_group(out, companies, minute=False):
    all_symbols = [c['symbol'] for c in companies]
    only_missing = minute and os.environ.get('INTRADAY_ONLY_MISSING') == '1'
    forced = [s.strip().upper() for s in os.environ.get('INTRADAY_SYMBOLS', '').split(',') if s.strip()]
    if minute and forced:
        symbols = [s for s in all_symbols if s in forced]
    else:
        symbols = [s for s in all_symbols if not read(out / 'intraday' / (s + '.json'), {}).get('bars')] if only_missing else all_symbols
    errors, success, failed = [], 0, []
    # Intraday responses are heavier; use a smaller pool to avoid upstream read timeouts.
    workers = int(os.environ.get('INTRADAY_WORKERS', '2')) if minute else int(os.environ.get('HISTORY_WORKERS', '4'))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_refresh_one_history, out, symbol, minute) for symbol in symbols]
        for future in as_completed(futures):
            symbol, ok, error = future.result()
            if ok:
                success += 1
            else:
                failed.append((symbol, error))
    # A short second pass at lower concurrency recovers transient upstream read
    # timeouts without forcing a full backfill or discarding retained history.
    if failed:
        retry_workers = max(1, min(int(os.environ.get('INTRADAY_RETRY_WORKERS', '1') if minute else os.environ.get('HISTORY_RETRY_WORKERS', '2')), workers))
        retry_symbols = [symbol for symbol, _ in failed]
        time.sleep(1)
        failed = []
        with ThreadPoolExecutor(max_workers=retry_workers) as pool:
            futures = [pool.submit(_refresh_one_history, out, symbol, minute) for symbol in retry_symbols]
            for future in as_completed(futures):
                symbol, ok, error = future.result()
                if ok:
                    success += 1
                else:
                    failed.append((symbol, error))
    errors = [f'{symbol}{" intraday" if minute else ""}: {error}' for symbol, error in failed]
    name = 'intraday' if minute else 'history'
    required = max(1, math.ceil(len(symbols) * 0.90)) if symbols else 0
    status_payload = {
        'checkedAt': now(), 'status': 'ok' if success >= required else 'partial',
        'success': success, 'expected': len(symbols), 'required': required, 'universe': len(all_symbols),
        'coveragePct': round(success / len(symbols) * 100, 1) if symbols else 100.0,
        'onlyMissing': only_missing, 'forcedSymbols': forced, 'retryPass': True, 'errors': errors
    }
    session = None
    if minute:
        session = intraday_session_summary(out, all_symbols)
        status_payload.update(session)
        status_payload.update(intraday_archive_summary(out, all_symbols))
        if session.get('sessionExpected') and session.get('sessionFresh', 0) < session.get('sessionRequired', 0):
            status_payload['status'] = 'partial'
    write(out / f'{name}-status.json', status_payload)
    if not minute:
        update_history_effective_status(out, all_symbols)
        build_drivers(out, companies)
    print(f'{name}: {success}/{len(symbols)} target; universe {len(all_symbols)}', flush=True)
    # Retained data remain available, but low coverage must not look healthy.
    # The workflow publishes successful updates even when this step fails.
    if minute and success < required:
        raise RuntimeError(f'{name} refresh coverage {success}/{len(symbols)} below required {required}')
    if minute and session and session.get('sessionExpected') and session.get('sessionFresh', 0) < session.get('sessionRequired', 0):
        raise RuntimeError(
            f"{name} current-session bar coverage {session.get('sessionFresh')}/{session.get('sessionExpected')} "
            f"below required {session.get('sessionRequired')}"
        )
    if not minute and success == 0:
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
        official_host_ok = (publisher == 'Federal Reserve' and (link.hostname or '').endswith('federalreserve.gov')) or (publisher == 'ECB' and (link.hostname or '').endswith('ecb.europa.eu'))
        if link.scheme not in ('http', 'https') or (link.hostname != domain and not official_host_ok) or not title:
            continue
        try:
            dt = parsedate_to_datetime(item.findtext('pubDate'))
            dt = dt.replace(tzinfo=dt.tzinfo or VN).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if dt > current + timedelta(minutes=10) or dt < current - timedelta(days=30):
            continue
        body = clean(item.findtext('description'))
        article_text = title + ' ' + body
        matched = [c['symbol'] for c in companies if company_match(c, article_text)]
        topics = set(FEED_TOPICS.get(feed_url, ()))
        for topic, pattern in TOPIC_PATTERNS.items():
            if pattern.search(article_text):
                topics.add(topic)
        if matched:
            topics.add('company')
        origin_source = clean(item.findtext('source')) or publisher
        source_tier, source_priority = news_source_quality(origin_source, publisher)
        meta = classify_news_meta(title, body, origin_source, topics, dt.isoformat())
        origin_fold = origin_source.casefold()
        if not meta.get('officialSource') and source_tier == 'official':
            if 'ngân hàng nhà nước' in origin_fold or 'state bank of vietnam' in origin_fold:
                meta['officialSource'] = 'SBV'
            elif 'chính phủ' in origin_fold:
                meta['officialSource'] = 'GOV'
            elif any(x in origin_fold for x in ('stock exchange', 'chứng khoán', 'hose', 'hnx')):
                meta['officialSource'] = 'MARKET_DISCLOSURE'
        row = {
            'title': title, 'summary': body[:900],
            'url': urlunsplit((link.scheme, link.netloc, link.path, '', '')),
            'source': origin_source, 'publishedAt': dt.isoformat(),
            'symbols': matched, 'topics': sorted(topics),
            'sourceTier': source_tier, 'sourcePriority': source_priority, **meta
        }
        if origin_source != publisher:
            row['feedSource'] = publisher
        rows.append(row)
    return rows


def _vbma_cell(value):
    text = clean(value).strip()
    if not text:
        return None
    candidate = text.replace(' ', '').replace('%', '')
    if re.fullmatch(r'-?\d{1,3}(?:,\d{3}){2,}', candidate):
        return int(candidate.replace(',', ''))
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


def normalize_vbma_dataset(key, parsed):
    rows, columns = parsed.get('rows', []), parsed.get('columns', [])
    if key == 'money_supply':
        amount_columns = [c for c in columns[1:] if not str(c).strip().startswith('%')]
        for row in rows:
            for column in amount_columns:
                value = row.get(column)
                if isinstance(value, str) and re.fullmatch(r'-?\d{1,3}(?:,\d{3})+', value):
                    row[column] = int(value.replace(',', ''))
    if key == 'credit_sector':
        for row in rows:
            for column in columns[1:]:
                value = row.get(column)
                if isinstance(value, str) and re.fullmatch(r'-?\d{1,3}(?:,\d{3})+', value):
                    row[column] = int(value.replace(',', ''))
                elif isinstance(value, float) and abs(value) < 10000 and abs(value * 1000 - round(value * 1000)) < 1e-6:
                    row[column] = int(round(value * 1000))
    parsed['numericColumns'] = [name for name in columns if any(isinstance(row.get(name), (int, float)) and not isinstance(row.get(name), bool) for row in rows)]
    return parsed


def _world_bank_json(path, params=None):
    raw = request_query(WORLD_BANK_API + path, params or {}, 'https://databank.worldbank.org/')
    payload = json.loads(raw)
    if isinstance(payload, dict):
        message = payload.get('message') or payload.get('error') or payload
        raise ValueError(f'World Bank API error: {message}')
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError('Unexpected World Bank API response')
    meta = payload[0] if isinstance(payload[0], dict) else {}
    rows = payload[1] if isinstance(payload[1], list) else []
    return meta, rows


def _world_bank_indicator_chunks(codes, max_count=45, max_chars=2200):
    chunk, length = [], 0
    for code in codes:
        extra = len(code) + (1 if chunk else 0)
        if chunk and (len(chunk) >= max_count or length + extra > max_chars):
            yield chunk
            chunk, length = [], 0
        chunk.append(code)
        length += extra
    if chunk:
        yield chunk


def dataset_age_hours(dataset):
    raw = (dataset or {}).get('collectedAt') or (dataset or {}).get('checkedAt')
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw).replace('Z', '+00:00')).astimezone(timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600)
    except (ValueError, TypeError):
        return None


def world_bank_esg_vietnam():
    """Fetch every ESG series published in World Bank DataBank source 75 for Viet Nam.

    The source catalog is discovered dynamically, so newly added indicators become
    available without maintaining a hard-coded indicator list. All annual observations
    returned by the source are retained.
    """
    catalog_meta, catalog = _world_bank_json('/indicator', {
        'source': WORLD_BANK_ESG_SOURCE, 'format': 'json', 'per_page': '1000'
    })
    indicators = {}
    for item in catalog:
        code = str(item.get('id') or '').strip()
        name = clean(item.get('name') or code)
        if code and re.fullmatch(r'[A-Za-z0-9_.-]+', code):
            indicators[code] = {
                'name': name or code,
                'unit': clean(item.get('unit') or ''),
                'note': clean(item.get('sourceNote') or '')[:500]
            }
    if not indicators:
        raise ValueError('World Bank ESG source 75 returned no indicators')

    end_year = datetime.now(VN).year + 1
    observations, data_updates = {}, []
    codes = sorted(indicators)
    for chunk in _world_bank_indicator_chunks(codes):
        meta, rows = _world_bank_json('/country/VNM/indicator/' + ';'.join(chunk), {
            'source': WORLD_BANK_ESG_SOURCE, 'date': f'1960:{end_year}',
            'format': 'json', 'per_page': '20000'
        })
        if meta.get('lastupdated'):
            data_updates.append(str(meta.get('lastupdated')))
        for item in rows:
            indicator = item.get('indicator') if isinstance(item.get('indicator'), dict) else {}
            code = str(indicator.get('id') or '').strip()
            year = str(item.get('date') or '').strip()
            value = number(item.get('value'))
            if code not in indicators or not re.fullmatch(r'\d{4}', year) or value is None:
                continue
            observations.setdefault(year, {})[code] = value

    if not observations:
        raise ValueError('World Bank ESG source 75 returned no Viet Nam observations')
    active_codes = [code for code in codes if any(code in row for row in observations.values())]
    rows = [{'Year': int(year), **{code: observations[year][code] for code in active_codes if code in observations[year]}}
            for year in sorted(observations)]
    metric_labels = {code: indicators[code]['name'] for code in active_codes}
    metric_units = {code: indicators[code]['unit'] for code in active_codes if indicators[code]['unit']}
    return {
        'id': 'esg_world_bank',
        'title': 'ESG Việt Nam · World Bank',
        'source': 'World Bank Sovereign ESG / DataBank source 75',
        'sourceUrl': WORLD_BANK_ESG_PROFILE,
        'collectedAt': now(),
        'status': 'ok',
        'columns': ['Year'] + active_codes,
        'numericColumns': active_codes,
        'metricLabels': metric_labels,
        'metricUnits': metric_units,
        'rows': rows,
        'allYears': True,
        'metricTable': True,
        'indicatorCount': len(active_codes),
        'catalogCount': len(indicators),
        'firstYear': rows[0]['Year'],
        'lastYear': rows[-1]['Year'],
        'sourceLastUpdated': max(data_updates) if data_updates else catalog_meta.get('lastupdated')
    }


def macro(out, companies=None):
    path = out / 'macro.json'
    previous = read(path, {'datasets': {}})
    datasets, sources = {}, []
    for key, (slug, title) in VBMA_TABLES.items():
        url = f'https://vbma.org.vn/csv/markets/tables/vi/{slug}.csv'
        try:
            parsed = normalize_vbma_dataset(key, parse_vbma_table(request(url)))
            parsed.update({'id': key, 'title': title, 'source': 'VBMA', 'sourceUrl': url, 'collectedAt': now(), 'status': 'ok'})
            datasets[key] = parsed
            sources.append({'id': key, 'provider': 'VBMA', 'url': url, 'status': 'ok', 'rows': len(parsed['rows'])})
        except Exception as e:
            retained = previous.get('datasets', {}).get(key)
            if retained:
                datasets[key] = {**retained, 'status': 'retained', 'error': str(e)}
            sources.append({'id': key, 'provider': 'VBMA', 'url': url, 'status': 'error', 'error': str(e)})

    retained_esg = previous.get('datasets', {}).get('esg_world_bank')
    retained_age = dataset_age_hours(retained_esg)
    if retained_esg and retained_age is not None and retained_age < WORLD_BANK_ESG_REFRESH_HOURS:
        datasets['esg_world_bank'] = {
            **retained_esg,
            'status': 'cached',
            'cacheCheckedAt': now(),
            'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS,
        }
        sources.append({
            'id': 'esg_world_bank', 'provider': 'World Bank ESG', 'url': WORLD_BANK_ESG_PROFILE,
            'status': 'cached', 'rows': len(retained_esg.get('rows', [])),
            'indicators': retained_esg.get('indicatorCount', 0),
            'ageHours': round(retained_age, 1),
            'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS,
        })
    else:
        try:
            esg = world_bank_esg_vietnam()
            esg['refreshCadenceHours'] = WORLD_BANK_ESG_REFRESH_HOURS
            datasets['esg_world_bank'] = esg
            sources.append({
                'id': 'esg_world_bank', 'provider': 'World Bank ESG', 'url': WORLD_BANK_ESG_PROFILE,
                'status': 'ok', 'rows': len(esg['rows']), 'indicators': esg['indicatorCount'],
                'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS,
            })
        except Exception as e:
            if retained_esg:
                datasets['esg_world_bank'] = {
                    **retained_esg, 'status': 'retained', 'error': str(e),
                    'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS,
                }
            sources.append({'id': 'esg_world_bank', 'provider': 'World Bank ESG', 'url': WORLD_BANK_ESG_PROFILE,
                            'status': 'error', 'error': str(e),
                            'refreshCadenceHours': WORLD_BANK_ESG_REFRESH_HOURS})

    ok = any(x['status'] == 'ok' for x in sources)
    providers = sorted({x.get('provider') for x in sources if x.get('provider') and (x['status'] == 'ok' or x['id'] in datasets)})
    write(path, {
        'checkedAt': now(), 'lastSuccessAt': now() if ok else previous.get('lastSuccessAt'),
        'status': 'ok' if ok else 'retained', 'source': ' + '.join(providers) or 'Macro data',
        'sources': sources, 'datasets': datasets
    })
    esg_count = datasets.get('esg_world_bank', {}).get('indicatorCount', 0)
    print(f'Macro/ESG: {sum(x["status"] == "ok" for x in sources)}/{len(sources)} sources; '
          f'{sum(len(x.get("rows", [])) for x in datasets.values())} rows; ESG indicators {esg_count}', flush=True)
    if not datasets:
        raise RuntimeError('Macro and ESG collection failed and no retained data is available')


SBV_NEWS_URL = 'https://sbv.gov.vn/vi/web/sbv_portal/trang-chu'

def _fetch_sbv_news(current):
    try:
        raw = request(SBV_NEWS_URL)
        text = raw.decode('utf-8-sig', errors='ignore') if isinstance(raw, bytes) else str(raw)
        rows, seen = [], set()
        # SBV has migrated page templates several times. Do not tie health to the
        # legacy dDocName-only template: scan article-like anchors, then require
        # a nearby publication date and an sbv.gov.vn destination.
        pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
        for match in pattern.finditer(text):
            title = clean(match.group(2))
            if len(title) < 18:
                continue
            href = html.unescape(match.group(1))
            link = urljoin(SBV_NEWS_URL, href)
            if not (urlsplit(link).hostname or '').endswith('sbv.gov.vn'):
                continue
            context = clean(text[max(0, match.start()-420):min(len(text), match.end()+420)])
            date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', context)
            if not date_match:
                continue
            day, month, year = map(int, date_match.groups())
            try:
                dt = datetime(year, month, day, 1, 0, tzinfo=VN).astimezone(timezone.utc)
            except ValueError:
                continue
            if dt > current + timedelta(days=1) or dt < current - timedelta(days=30):
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            topics = {'vietnam','banking','macro','central_bank','sbv'}
            for topic, topic_pattern in TOPIC_PATTERNS.items():
                if topic_pattern.search(title):
                    topics.add(topic)
            meta = classify_news_meta(title, '', 'Ngân hàng Nhà nước Việt Nam', topics, dt.isoformat())
            meta['officialSource'] = 'SBV'
            meta['impactScore'] = max(meta['impactScore'], 52 if SBV_PATTERN.search(title) else 36)
            rows.append({
                'title': title, 'summary': '', 'url': link,
                'source': 'Ngân hàng Nhà nước Việt Nam',
                'publishedAt': dt.isoformat(), 'symbols': [], 'topics': sorted(topics),
                'sourceTier': 'official', 'sourcePriority': 100, **meta
            })
        rows.sort(key=lambda row: row['publishedAt'], reverse=True)
        status = 'ok' if rows else 'empty'
        return rows[:80], {
            'name': 'Ngân hàng Nhà nước Việt Nam', 'url': SBV_NEWS_URL,
            'status': status, 'items': len(rows[:80]), 'parser': 'sbv-anchor-date-v2',
            'lastItemAt': rows[0]['publishedAt'] if rows else None
        }
    except Exception as e:
        return [], {'name': 'Ngân hàng Nhà nước Việt Nam', 'url': SBV_NEWS_URL, 'status': 'error', 'error': str(e)}


def _fetch_news_feed(publisher, url, companies, current):
    try:
        items = parse_feed(request(url), publisher, url, companies, current)
        return items, {
            'name': publisher, 'url': url, 'status': 'ok' if items else 'empty',
            'items': len(items), 'lastItemAt': items[0]['publishedAt'] if items else None
        }
    except Exception as e:
        return [], {'name': publisher, 'url': url, 'status': 'error', 'error': str(e)}


def _news_story_key(row):
    title = clean((row or {}).get('title')).casefold()
    title = re.sub(r'\s+[-–—|]\s+(?:luatvietnam|vnexpress|vneconomy|cafef|vietnamnet|báo đầu tư|báo chính phủ)\s*$', '', title, flags=re.I)
    title = re.sub(r'[^\w\sÀ-ỹ]', ' ', title, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', title).strip()

def _unique_news(rows):
    unique, titles = {}, {}
    for row in sorted(rows, key=lambda r: r.get('publishedAt') or '', reverse=True):
        url = row.get('url')
        key = _news_story_key(row)
        if not url or not key:
            continue
        existing_url = unique.get(url)
        existing_key = titles.get(key)
        existing = existing_url or existing_key
        if existing:
            new_priority = int(row.get('sourcePriority') or 0)
            old_priority = int(existing.get('sourcePriority') or 0)
            if new_priority > old_priority:
                if existing.get('url') in unique:
                    del unique[existing['url']]
                unique[url] = row
                titles[key] = row
            continue
        unique[url] = row
        titles[key] = row
    return sorted(unique.values(), key=lambda r: r.get('publishedAt') or '', reverse=True)

def _balanced_news_snapshot(items):
    ordered = sorted(items or [], key=lambda r: r.get('publishedAt') or '', reverse=True)
    vietnam = [r for r in ordered if r.get('region') != 'global'][:140]
    global_rows = [r for r in ordered if r.get('region') == 'global'][:60]
    sbv_rows = [r for r in ordered if r.get('officialSource') == 'SBV' or 'sbv' in (r.get('topics') or [])][:50]
    impact = [r for r in ordered if int(r.get('impactScore') or 0) >= 48][:50]
    return _unique_news(vietnam + global_rows + sbv_rows + impact)

def _company_news_snapshot(items, per_symbol=15):
    ordered = sorted(items or [], key=lambda r: r.get('publishedAt') or '', reverse=True)
    counts, picked = {}, []
    seen = set()
    for row in ordered:
        symbols = [str(x).upper() for x in (row.get('symbols') or []) if x]
        wanted = [symbol for symbol in symbols if counts.get(symbol, 0) < per_symbol]
        if not wanted:
            continue
        key = row.get('url') or _news_story_key(row)
        if key not in seen:
            seen.add(key)
            picked.append(row)
        for symbol in wanted:
            counts[symbol] = counts.get(symbol, 0) + 1
    return picked, counts

def news(out, companies):
    path = out / 'news.json'
    previous = read(path, {'items': []})
    current = datetime.now(timezone.utc)
    rows, sources = [], []
    # RSS/discovery feeds are best-effort and concurrent so one slow publisher
    # cannot starve the 15-minute publisher heartbeat.
    workers = min(10, max(1, len(FEEDS)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_news_feed, publisher, url, companies, current)
                   for publisher, url in FEEDS]
        for future in as_completed(futures):
            items, source = future.result()
            rows.extend(items)
            sources.append(source)
    sbv_items, sbv_source = _fetch_sbv_news(current)
    rows.extend(sbv_items)
    sources.append(sbv_source)
    source_order = {url: i for i, (_, url) in enumerate(FEEDS)}
    sources.sort(key=lambda row: source_order.get(row.get('url'), 999))

    retained = []
    for row in previous.get('items', []):
        try:
            if datetime.fromisoformat(str(row.get('publishedAt')).replace('Z', '+00:00')).astimezone(timezone.utc) >= current - timedelta(days=30):
                retained.append(row)
        except (TypeError, ValueError, OverflowError):
            continue
    items = _unique_news(rows + retained)[:2500]
    healthy = sum(source.get('status') == 'ok' for source in sources)
    empty = sum(source.get('status') == 'empty' for source in sources)
    ok = healthy > 0
    checked_at = now()
    health = {'healthy': healthy, 'empty': empty, 'error': len(sources) - healthy - empty, 'total': len(sources)}
    payload = {
        'checkedAt': checked_at, 'lastSuccessAt': checked_at if ok else previous.get('lastSuccessAt'),
        'status': 'ok' if ok else 'retained', 'sources': sources, 'sourceHealth': health,
        'items': items
    }
    write(path, payload)

    latest_items = _balanced_news_snapshot(items)
    write(out / 'news-latest.json', {
        **payload, 'archiveFile': 'news.json', 'selection': 'balanced_vietnam_global_sbv_impact',
        'items': latest_items
    })

    company_items, company_counts = _company_news_snapshot(items)
    write(out / 'news-company-latest.json', {
        **payload, 'archiveFile': 'news.json', 'selection': 'per_symbol_latest',
        'perSymbolLimit': 15, 'companyCoverage': len(company_counts),
        'companyCounts': company_counts, 'items': company_items
    })
    drivers = build_drivers(out, companies) if (out / 'quotes.json').exists() else {}
    print(
        f'News: {len(rows)} fetched; {len(items)} unique; latest {len(latest_items)}; '
        f'company {len(company_items)} items/{len(company_counts)} symbols; '
        f'sources {healthy}/{len(sources)} healthy ({empty} empty); drivers: {len(drivers)}',
        flush=True
    )
    if not ok:
        raise RuntimeError('All news sources failed or returned no parseable items; previous news retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['prices', 'history', 'intraday', 'news', 'macro', 'scanner', 'all'], default='all')
    args = parser.parse_args()
    core_companies = read(ROOT / 'data/companies.json', [])
    if len({c['symbol'] for c in core_companies}) != 100:
        raise RuntimeError('Expected 100 unique VN100 Core symbols')
    companies, universe = load_market_companies(core_companies, args.output)
    if len({c['symbol'] for c in companies}) < 100:
        raise RuntimeError('Tiered HOSE market universe cannot be smaller than Core 100')
    universe = universe or fallback_market_universe(companies)
    if args.mode in {'prices', 'history', 'intraday', 'all'}:
        sync_market_universe(args.output, universe)
        seed_market_histories(args.output, universe, companies)
    errors = []
    for mode in (['prices', 'news', 'macro'] if args.mode == 'all' else [args.mode]):
        try:
            globals()[mode](args.output, companies)
        except Exception as e:
            errors.append(str(e))
    if errors:
        raise SystemExit('; '.join(errors))


