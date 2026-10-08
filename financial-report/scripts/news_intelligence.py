"""Semantic news intelligence helpers for FinQuery.

This module deliberately keeps deterministic, testable rules around ambiguous
Vietnamese tickers, story clustering, source lineage and user-facing news
priority. It is not a price-direction model.
"""
import hashlib
import html
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

VIETNAM_TZ = timezone(timedelta(hours=7))

STOPWORDS = {
    'va','cua','cho','voi','trong','ngoai','mot','nhung','cac','dang','duoc','tai','tu','den',
    'sau','truoc','khi','nay','nam','ngay','thang','the','la','co','ve','tren','duoi','theo',
    'thi','truong','cong','ty','tap','doan','co','phan','stock','shares','market','company',
    'the','and','for','with','from','into','after','before','says','said','new','latest'
}

AMBIGUOUS = {'HCM','VIX','VND','CEO','GAS','PET','POW'}

ISSUER_CUES = {
    'HCM': (
        r'chứng khoán\s+(?:tp\.?\s*hcm|hcm)|ho chi minh city securities|hcm securities|\bhsc\b',
        r'cổ phiếu\s+hcm|mã\s+hcm|hose\s*:\s*hcm'
    ),
    'VIX': (
        r'chứng khoán\s+vix|vix securities|ctcp\s+chứng khoán\s+vix',
        r'cổ phiếu\s+vix|mã\s+vix|hose\s*:\s*vix'
    ),
    'VND': (
        r'vndirect|chứng khoán\s+vndirect|ctcp\s+chứng khoán\s+vndirect',
        r'cổ phiếu\s+vnd|mã\s+vnd|hose\s*:\s*vnd'
    ),
    'CEO': (
        r'ceo\s+group|tập đoàn\s+c\.??e\.??o|ctcp\s+tập đoàn\s+ceo',
        r'cổ phiếu\s+ceo|mã\s+ceo|hnx\s*:\s*ceo'
    ),
    'GAS': (
        r'pv\s*gas|tổng công ty khí việt nam|petrovietnam gas',
        r'cổ phiếu\s+gas|mã\s+gas|hose\s*:\s*gas'
    ),
    'PET': (
        r'petrosetco|dịch vụ tổng hợp dầu khí',
        r'cổ phiếu\s+pet|mã\s+pet|hose\s*:\s*pet'
    ),
    'POW': (
        r'pv\s*power|điện lực dầu khí việt nam|petrovietnam power',
        r'cổ phiếu\s+pow|mã\s+pow|hose\s*:\s*pow'
    ),
}

NEGATIVE_CONTEXT = {
    'HCM': (
        r'tp\.?\s*hcm|tphcm|thành phố hồ chí minh|ho chi minh city',
    ),
    'VIX': (
        r'cboe|volatility|volatility index|fear gauge|s&p\s*500|\bspy\b|wall street|vix\s+(?:index|at|hits?|falls?|rises?|points?)',
    ),
    'VND': (
        r'vietnam(?:ese)?\s+dong|đồng việt nam|\b\d[\d.,]*\s*(?:tỷ|triệu|nghìn)?\s*vnd\b|vnd\s*(?:per|/)|tỷ giá|exchange rate',
    ),
    'CEO': (
        r'\bceo\b.{0,50}(?:said|says|resign|chief executive|giám đốc|tổng giám đốc|chủ tịch)',
    ),
    'GAS': (
        r'natural gas|gas price|gas futures|khí đốt|giá khí',
    ),
    'PET': (
        r'\bpet(?:s)?\b|thú cưng',
    ),
    'POW': (
        r'\bpow(?:er)?\b',
    ),
}

GOLD_EXPLICIT = re.compile(
    r'giá\s+vàng|vàng\s+(?:miếng|nhẫn|sjc|thế giới|giao ngay|kỳ hạn)|gold\s+(?:price|prices|futures|spot)|'
    r'\bxau(?:usd)?\b|bullion|ounce|oz\b|kim loại quý', re.I)
GOLD_IDIOM = re.compile(
    r'chọn mặt gửi vàng|cơ hội vàng|thời điểm vàng|tấm vé vàng|mỏ vàng|trứng vàng|chìa khóa vàng|giờ vàng', re.I)
FX_EXPLICIT = re.compile(
    r'tỷ\s+giá|exchange\s+rate|foreign\s+exchange|forex|dollar\s+index|\bdxy\b|usd\s*/\s*vnd|'
    r'vnd\s*/\s*usd|đồng\s+usd|đồng\s+đô\s+la|ngoại\s+hối|tỷ\s+giá\s+trung\s+tâm', re.I)
OIL_EXPLICIT = re.compile(
    r'giá\s+dầu|dầu\s+(?:brent|wti|thô)|oil\s+(?:price|prices|futures)|\bbrent\b|\bwti\b|crude\s+oil', re.I)
RATE_EXPLICIT = re.compile(
    r'lãi\s+suất|interest\s+rate|rate\s+(?:cut|hike)|fed\s+(?:rate|hike|cut)|fomc|'
    r'ngân hàng nhà nước|\bnhnn\b|\bsbv\b|thị trường mở|\bomo\b|bơm ròng|hút ròng', re.I)
MACRO_EXPLICIT = re.compile(
    r'\bcpi\b|inflation|lạm phát|\bgdp\b|\bpmi\b|payroll|unemployment|việc làm mỹ|tăng trưởng kinh tế', re.I)
GEOPOLITICAL_EXPLICIT = re.compile(
    r'war|conflict|sanction|missile|invasion|ceasefire|chiến tranh|xung đột|trừng phạt|tên lửa|tấn công quân sự', re.I)
CORPORATE_ACTION = re.compile(
    r'cổ tức|esop|phát hành|mua lại cổ phiếu|cp quỹ|đhđcđ|đại hội cổ đông|m&a|sáp nhập|thoái vốn|'
    r'kết quả kinh doanh|doanh thu|lợi nhuận|báo cáo tài chính|giao dịch cổ phiếu|đăng ký mua|đăng ký bán', re.I)

POSITIVE = re.compile(
    r'vượt kế hoạch|tăng trưởng mạnh|lợi nhuận tăng|doanh thu tăng|trúng thầu|ký hợp đồng|nâng khuyến nghị|'
    r'tăng giá mục tiêu|mở rộng|khởi công|hoàn thành|approved|beats? estimates?|upgrade|record profit', re.I)
NEGATIVE = re.compile(
    r'lỗ|giảm lợi nhuận|doanh thu giảm|hạ khuyến nghị|giảm giá mục tiêu|bị phạt|xử phạt|khởi tố|bắt tạm giam|'
    r'vỡ nợ|phá sản|hủy niêm yết|đình chỉ|miss(?:es|ed)? estimates?|downgrade|fraud|default|bankrupt', re.I)

FINANCIAL_NEWS_RE = re.compile(
    r'cổ phiếu|chứng khoán|thị trường|vn-?index|hose|hnx|upcom|ngân hàng|lãi suất|tỷ giá|'
    r'doanh thu|lợi nhuận|kết quả kinh doanh|báo cáo tài chính|trái phiếu|cổ tức|esop|'
    r'đầu tư|vốn hóa|khối ngoại|quỹ|mua ròng|bán ròng|hàng hóa|giá dầu|giá vàng|'
    r'fed|fomc|cpi|gdp|pmi|lạm phát|bất động sản|doanh nghiệp|ipo|m&a|'
    r'stock|shares|earnings|revenue|profit|bond|dividend|interest rate|exchange rate',
    re.I
)
FINANCIAL_TOPIC_ALLOW = {
    'stocks','finance','commodity','macro','realestate','business','rates','fx',
    'gold','oil','company','geopolitical'
}

TITLE_NOISE = re.compile(
    r'\s*[-–—|]\s*(?:luatvietnam|vnexpress|vneconomy|cafef|vietnamnet|báo đầu tư|báo chính phủ|24hmoney)\s*$',
    re.I
)


def fold(value):
    value = unicodedata.normalize('NFD', str(value or ''))
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    return value.replace('đ','d').replace('Đ','D').lower()


def compact(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', html.unescape(str(value or '')))).strip()


def token_set(value):
    text = fold(TITLE_NOISE.sub('', compact(value)))
    tokens = re.findall(r'[a-z0-9]{2,}', text)
    return {x for x in tokens if x not in STOPWORDS and not x.isdigit()}


def _pattern_any(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


def _ticker_exact(text, symbol):
    return bool(re.search(r'(?<![A-Za-z0-9])' + re.escape(symbol) + r'(?![A-Za-z0-9])', text))


def _issuer_context(symbol, text):
    return _pattern_any(ISSUER_CUES.get(symbol, ()), text)


def _ambiguous_ok(symbol, text):
    if symbol not in AMBIGUOUS:
        return True, 0.88, 'ticker_exact'
    issuer = _issuer_context(symbol, text)
    negative = _pattern_any(NEGATIVE_CONTEXT.get(symbol, ()), text)
    if issuer:
        return True, 0.99, 'issuer_context'
    if negative:
        return False, 0.02, 'ambiguous_non_issuer_context'
    return False, 0.20, 'ambiguous_without_issuer_context'


def resolve_company_symbols(companies, title, body='', aliases=None):
    """Return deterministic symbol matches with confidence and reason.

    Short ticker mentions in prose are accepted only with issuer context for
    known ambiguous symbols. Company-name/long-alias matches remain available
    so recall does not depend on ticker text.
    """
    aliases = aliases or {}
    title = compact(title)
    body = compact(body)
    text = title + ' ' + body
    mentions = []
    for company in companies or []:
        symbol = str(company.get('symbol') or '').upper()
        if not symbol:
            continue
        name = compact(company.get('name') or '')
        long_aliases = [compact(x) for x in aliases.get(symbol, [])] + ([name] if name else [])
        long_aliases = [x for x in long_aliases if len(x) >= 5]

        name_hit = next((a for a in long_aliases if re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', text, re.I)), None)
        ticker_title = _ticker_exact(title, symbol)
        ticker_body = _ticker_exact(body, symbol)
        if symbol == 'FPT' and re.search(r'\bfpt\s+(?:retail|securities)\b', text, re.I) and not re.search(r'fpt\s+(?:corporation|corp)|tập đoàn\s+fpt|công ty cổ phần\s+fpt', text, re.I):
            ticker_title = False
            ticker_body = False

        if name_hit:
            mentions.append({'symbol':symbol,'confidence':0.98,'reason':'issuer_alias','evidence':name_hit[:80]})
            continue
        if ticker_title or ticker_body:
            ok, confidence, reason = _ambiguous_ok(symbol, text)
            if ok:
                mentions.append({'symbol':symbol,'confidence':confidence if ticker_title else max(0.78, confidence-0.08),'reason':reason,'evidence':symbol})
                continue
            if symbol not in AMBIGUOUS:
                cue = bool(re.search(r'cổ phiếu|mã\s+|hose|hnx|upcom|chứng khoán|doanh nghiệp|lợi nhuận|doanh thu|ctcp|tập đoàn', text, re.I))
                if ticker_title or cue:
                    mentions.append({'symbol':symbol,'confidence':0.90 if ticker_title else 0.78,'reason':'ticker_with_financial_context','evidence':symbol})
    # One row per symbol, highest-confidence match.
    best = {}
    for row in mentions:
        prior = best.get(row['symbol'])
        if not prior or row['confidence'] > prior['confidence']:
            best[row['symbol']] = row
    return sorted(best.values(), key=lambda x:(-x['confidence'], x['symbol']))


def classify_semantics(title, body='', existing_topics=None):
    text = compact((title or '') + ' ' + (body or ''))
    topics = set(existing_topics or [])
    evidence = []

    if RATE_EXPLICIT.search(text):
        topics.update({'rates','finance'})
        evidence.append('rates')
    if GOLD_EXPLICIT.search(text) and not (GOLD_IDIOM.search(text) and not re.search(r'giá\s+vàng|gold\s+price|xau', text, re.I)):
        topics.update({'commodity','gold','market'})
        evidence.append('gold')
    else:
        topics.discard('gold')
    if OIL_EXPLICIT.search(text):
        topics.update({'commodity','oil','market'})
        evidence.append('oil')
    if FX_EXPLICIT.search(text):
        topics.update({'fx','finance'})
        evidence.append('fx')
    else:
        # Bare USD/VND values are monetary units, not automatically an FX catalyst.
        topics.discard('fx')
    if MACRO_EXPLICIT.search(text):
        topics.add('macro')
        evidence.append('macro')
    if GEOPOLITICAL_EXPLICIT.search(text):
        topics.add('geopolitical')
        evidence.append('geopolitical')
    if CORPORATE_ACTION.search(text):
        topics.add('company')
        evidence.append('corporate')

    return sorted(topics), evidence


def classify_content_type(source='', title='', topics=None):
    source_fold = fold(source)
    title_fold = fold(title)
    topics = set(topics or [])
    if any(x in source_fold for x in ('ngan hang nha nuoc','chinh phu','stock exchange','so giao dich','uy ban chung khoan')):
        return 'official'
    if re.search(r'bao cao phan tich|khuyen nghi|gia muc tieu', title_fold) and ('ctck' in topics or 'research' in topics):
        return 'broker_research'
    if 'community' in topics or any(x in source_fold for x in ('cong dong','community')):
        return 'community'
    if 'expert' in topics or any(x in source_fold for x in ('chuyen gia','expert')):
        return 'expert_analysis'
    if 'event' in topics:
        return 'corporate_event'
    return 'news'


def expected_impact(title, body='', symbols=None):
    text = compact((title or '') + ' ' + (body or ''))
    pos = bool(POSITIVE.search(text))
    neg = bool(NEGATIVE.search(text))
    if pos and not neg:
        direction = 'positive'; confidence = 0.68
    elif neg and not pos:
        direction = 'negative'; confidence = 0.72
    elif pos and neg:
        direction = 'mixed'; confidence = 0.55
    else:
        direction = 'unknown'; confidence = 0.0
    return {
        'direction': direction,
        'confidence': confidence,
        'scope': 'symbol' if symbols else 'market',
        'model': 'deterministic_semantic_v1'
    }


def semantic_priority(row, now=None):
    """Priority is attention/relevance, not a price probability."""
    now = now or datetime.now(timezone.utc)
    base = 0
    tier = str(row.get('sourceTier') or '')
    base += {'official':28,'trusted_legal_direct':24,'trusted_legal':22,'financial_press':18,'trusted_discovery':14,'press':12,'global_discovery':10}.get(tier, 8)
    if row.get('contentType') == 'community':
        base -= 18
    elif row.get('contentType') == 'expert_analysis':
        base -= 6
    if row.get('symbols'):
        base += 14
    if row.get('marketMoving'):
        base += 14
    base += min(24, int(row.get('impactScore') or 0) // 4)
    try:
        stamp = datetime.fromisoformat(str(row.get('publishedAt')).replace('Z','+00:00')).astimezone(timezone.utc)
        age = max(0, (now-stamp).total_seconds()/3600)
        base += 18 if age <= 2 else (12 if age <= 8 else (7 if age <= 24 else 0))
    except Exception:
        pass
    source_count = int(row.get('sourceCount') or 1)
    if source_count >= 2:
        base += min(10, 3 + source_count)
    return max(0, min(100, base))


def story_similarity(a, b):
    ta, tb = token_set(a.get('title')), token_set(b.get('title'))
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / max(1, len(ta | tb))
    sa, sb = set(a.get('symbols') or []), set(b.get('symbols') or [])
    if sa and sb and sa == sb:
        overlap += 0.16
    if a.get('impactTag') and a.get('impactTag') == b.get('impactTag'):
        overlap += 0.08
    return min(1.0, overlap)


def _story_id(row):
    base = '|'.join([
        compact(row.get('title')).casefold(),
        ','.join(sorted(row.get('symbols') or [])),
        str(row.get('impactTag') or ''),
        str(row.get('publishedAt') or '')[:13],
    ])
    return 'story_' + hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]


def cluster_stories(rows, threshold=0.48, hours=18):
    """Cluster semantically similar rows without counting syndication as confirmation."""
    ordered = sorted(rows or [], key=lambda x:str(x.get('publishedAt') or ''), reverse=True)
    clusters = []
    for row in ordered:
        try:
            stamp = datetime.fromisoformat(str(row.get('publishedAt')).replace('Z','+00:00')).astimezone(timezone.utc)
        except Exception:
            stamp = None
        match = None
        best_score = 0.0
        for cluster in clusters[-180:]:
            head = cluster['head']
            try:
                head_stamp = datetime.fromisoformat(str(head.get('publishedAt')).replace('Z','+00:00')).astimezone(timezone.utc)
            except Exception:
                head_stamp = None
            if stamp and head_stamp and abs((head_stamp-stamp).total_seconds()) > hours*3600:
                continue
            score = story_similarity(row, head)
            if score > best_score and score >= threshold:
                match = cluster; best_score = score
        if match is None:
            clusters.append({'id':_story_id(row),'head':row,'rows':[row]})
        else:
            match['rows'].append(row)

    enriched = []
    story_rows = []
    for cluster in clusters:
        members = cluster['rows']
        original_publishers = []
        discovery = []
        for m in members:
            publisher = str(m.get('publisher') or m.get('source') or '').strip()
            via = str(m.get('discoveredVia') or m.get('feedSource') or '').strip()
            if publisher and publisher not in original_publishers:
                original_publishers.append(publisher)
            if via and via != publisher and via not in discovery:
                discovery.append(via)
        canonical = max(members, key=lambda x:(
            int(x.get('sourcePriority') or 0),
            1 if x.get('directSource') else 0,
            1 if x.get('detailTimestampVerified') else 0,
            str(x.get('publishedAt') or '')
        ))
        independent = len(set(original_publishers))
        story = {
            'storyId':cluster['id'],
            'title':canonical.get('title'),
            'canonicalUrl':canonical.get('url'),
            'canonicalSource':canonical.get('source'),
            'symbols':canonical.get('symbols') or [],
            'topics':canonical.get('topics') or [],
            'impactTag':canonical.get('impactTag'),
            'firstSeenAt':min((x.get('publishedAt') for x in members if x.get('publishedAt')), default=None),
            'lastSeenAt':max((x.get('publishedAt') for x in members if x.get('publishedAt')), default=None),
            'sourceCount':independent,
            'originalPublishers':original_publishers[:12],
            'discoveredVia':discovery[:12],
            'memberCount':len(members),
        }
        story_rows.append(story)
        for m in members:
            copy = dict(m)
            copy.update({
                'storyId':cluster['id'],
                'sourceCount':independent,
                'storyMemberCount':len(members),
                'canonicalSource':canonical.get('source'),
                'canonicalUrl':canonical.get('url'),
                'originalPublishers':original_publishers[:8],
            })
            copy['newsPriority'] = semantic_priority(copy)
            enriched.append(copy)
    enriched.sort(key=lambda x:str(x.get('publishedAt') or ''), reverse=True)
    story_rows.sort(key=lambda x:str(x.get('lastSeenAt') or ''), reverse=True)
    return enriched, story_rows


def _24hmoney_plain_context(text,start,end,radius=3200):
    marker='__FQ_ANCHOR__'
    raw=text[max(0,start-radius):start]+' '+marker+' '+text[end:min(len(text),end+radius)]
    plain=compact(raw)
    return plain,plain.find(marker),marker


def _marker_distance(match,anchor):
    if anchor<0:return 10**9
    if match.end()<=anchor:return anchor-match.end()
    if match.start()>=anchor:return match.start()-anchor
    return 0


def _24hmoney_context_category(context,anchor=-1,max_distance=140):
    text=compact(context)
    candidates=[]
    patterns=[
        (r'#?\s*Chuyên\s*gia',('expert_analysis',{'expert','stocks'})),
        (r'#?\s*Chứng\s*khoán',('news',{'stocks'})),
        (r'#?\s*Tài\s*chính',('news',{'finance'})),
        (r'#?\s*Hàng\s*hóa',('news',{'commodity'})),
        (r'#?\s*KT\s*vĩ\s*mô',('news',{'macro'})),
        (r'#?\s*Tin\s*quốc\s*tế',('news',{'global'})),
        (r'#?\s*Bất\s*Động\s*Sản',('news',{'realestate'})),
        (r'#?\s*Kinh\s*doanh',('news',{'business'})),
        (r'#?\s*Pháp\s*luật',('news',{'legal'})),
    ]
    for pattern,value in patterns:
        for m in re.finditer(pattern,text,re.I):
            distance=_marker_distance(m,anchor) if anchor>=0 else 0
            if distance<=max_distance:candidates.append((distance,m.start(),value))
    if not candidates:
        return 'news',set()
    candidates.sort(key=lambda x:(x[0],x[1]))
    return candidates[0][2]


def _24hmoney_timestamp(context,current,anchor=-1,max_distance=180):
    """Parse only the timestamp nearest the article card; never borrow a distant card time."""
    text=compact(context)
    candidates=[]

    for m in re.finditer(r'(?<!\d)(\d{1,3})\s*(phút|giờ|ngày)(?:\s+trước)?(?!\w)',text,re.I):
        distance=_marker_distance(m,anchor) if anchor>=0 else 0
        if distance>max_distance:continue
        n=int(m.group(1));unit=fold(m.group(2))
        if n<0 or (unit=='phut' and n>1440) or (unit=='gio' and n>168) or (unit=='ngay' and n>7):
            continue
        delta=timedelta(minutes=n) if unit=='phut' else (timedelta(hours=n) if unit=='gio' else timedelta(days=n))
        candidates.append((distance,0,m.start(),current-delta,'relative',False))

    for m in re.finditer(r'\bhôm\s+qua\b',text,re.I):
        distance=_marker_distance(m,anchor) if anchor>=0 else 0
        if distance>max_distance:continue
        local=current.astimezone(VIETNAM_TZ)
        day=(local-timedelta(days=1)).date()
        stamp=datetime(day.year,day.month,day.day,tzinfo=VIETNAM_TZ).astimezone(timezone.utc)
        candidates.append((distance,1,m.start(),stamp,'day',False))

    for m in re.finditer(r'(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?:\s+(?:lúc\s+)?(\d{1,2}):(\d{2}))?',text,re.I):
        distance=_marker_distance(m,anchor) if anchor>=0 else 0
        if distance>max_distance:continue
        d,mo,y,hh,mm=m.groups()
        try:
            stamp=datetime(int(y),int(mo),int(d),int(hh or 0),int(mm or 0),tzinfo=VIETNAM_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
        candidates.append((distance,2,m.start(),stamp,'minute' if hh is not None else 'day',bool(hh is not None)))

    if not candidates:return None,None,False
    candidates.sort(key=lambda x:(x[0],x[1],x[2]))
    _,_,_,stamp,precision,verified=candidates[0]
    return stamp,precision,verified

def count_24hmoney_article_anchors(raw):
    text=raw.decode('utf-8-sig',errors='ignore') if isinstance(raw,bytes) else str(raw or '')
    anchor_re=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',re.I|re.S)
    return sum(
        1 for m in anchor_re.finditer(text)
        if '/news/' in html.unescape(m.group(1)).lower() and len(compact(m.group(2)))>=24
    )


def _24hmoney_financial_relevance(title, symbols, topics, evidence, content_type):
    topic_set=set(topics or [])
    evidence_set=set(evidence or [])
    if symbols:
        return True,'symbol'
    if content_type=='expert_analysis':
        return True,'expert'
    if topic_set & FINANCIAL_TOPIC_ALLOW:
        # Broad categories such as business/real-estate are accepted because
        # they are explicit 24HMoney finance modules, not generic site chrome.
        return True,'source_category'
    if evidence_set & {'rates','gold','oil','fx','macro','geopolitical','corporate'}:
        return True,'semantic_evidence'
    if FINANCIAL_NEWS_RE.search(str(title or '')):
        return True,'financial_title'
    return False,'non_financial'


def parse_24hmoney_live(raw, current, companies, aliases=None, base_url='https://24hmoney.vn/news/live', financial_only=True):
    text=raw.decode('utf-8-sig',errors='ignore') if isinstance(raw,bytes) else str(raw or '')
    rows=[];seen=set()
    anchor_re=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',re.I|re.S)
    for match in anchor_re.finditer(text):
        href=html.unescape(match.group(1)).strip()
        title=compact(match.group(2))
        if len(title)<24 or '/news/' not in href.lower():
            continue
        url=urljoin(base_url,href)
        parsed=urlsplit(url)
        if not (parsed.hostname or '').endswith('24hmoney.vn'):
            continue
        clean_url=urlunsplit((parsed.scheme or 'https',parsed.netloc,parsed.path,'',''))
        if clean_url in seen:
            continue
        seen.add(clean_url)

        # Keep the article anchor as a sentinel in normalized plain text,
        # then choose the nearest timestamp/category marker. This prevents one
        # card from borrowing metadata from the previous/next card.
        context,anchor,_=_24hmoney_plain_context(text,match.start(),match.end())
        stamp,precision,verified=_24hmoney_timestamp(context,current,anchor)
        if stamp is None or stamp<current-timedelta(days=7) or stamp>current+timedelta(minutes=10):
            continue

        content_type,extra_topics=_24hmoney_context_category(context,anchor)
        base_topics={'vietnam','market'}|set(extra_topics)
        mentions=resolve_company_symbols(companies,title,'',aliases)
        topics,evidence=classify_semantics(title,'',base_topics)
        symbols=[x['symbol'] for x in mentions]
        relevant,relevance_reason=_24hmoney_financial_relevance(title,symbols,topics,evidence,content_type)
        if financial_only and not relevant:
            continue
        source_tier='expert' if content_type=='expert_analysis' else 'financial_press'
        source_priority=54 if content_type=='expert_analysis' else 78
        row={
            'title':title,'summary':'','url':clean_url,'source':'24HMoney',
            'publisher':'24HMoney','discoveredVia':'24HMoney Live',
            'publishedAt':stamp.isoformat(),'timePrecision':precision,
            'detailTimestampVerified':verified,
            'symbols':symbols,'entityMentions':mentions,
            'entityConfidence':max([x['confidence'] for x in mentions],default=None),
            'topics':topics,'topicEvidence':evidence,
            'sourceTier':source_tier,'sourcePriority':source_priority,
            'contentType':content_type,'directSource':True,
            'sourceCategory':next((x for x in ('stocks','finance','commodity','macro','realestate','business','global','legal','expert') if x in set(topics)), 'general'),
            'financialRelevance':relevant,'relevanceReason':relevance_reason,
        }
        row['expectedImpact']=expected_impact(title,'',symbols)
        rows.append(row)
    rows.sort(key=lambda x:x['publishedAt'],reverse=True)
    return rows[:120]

def enrich_row(row, companies, aliases=None):
    copy = dict(row or {})
    mentions = resolve_company_symbols(companies,copy.get('title',''),copy.get('summary',''),aliases)
    copy['entityMentions'] = mentions
    copy['symbols'] = [x['symbol'] for x in mentions]
    copy['entityConfidence'] = max([x['confidence'] for x in mentions],default=None)
    topics,evidence = classify_semantics(copy.get('title',''),copy.get('summary',''),copy.get('topics') or [])
    copy['topics'] = topics
    copy['topicEvidence'] = evidence
    copy.setdefault('publisher',copy.get('source'))
    copy.setdefault('discoveredVia',copy.get('feedSource') or copy.get('source'))
    copy['contentType'] = classify_content_type(copy.get('source',''),copy.get('title',''),topics)
    copy['expectedImpact'] = expected_impact(copy.get('title',''),copy.get('summary',''),copy.get('symbols'))
    topic_set=set(topics)
    current_tag=str(copy.get('impactTag') or '')
    if current_tag=='VÀNG' and 'gold' not in topic_set:
        copy['impactTag']='DOANH NGHIỆP' if copy.get('symbols') else ('THẾ GIỚI' if copy.get('region')=='global' else 'VĨ MÔ')
        copy['semanticCorrection']='gold_idiom_or_non_commodity'
    elif current_tag=='TỶ GIÁ' and 'fx' not in topic_set:
        copy['impactTag']='DOANH NGHIỆP' if copy.get('symbols') else ('THẾ GIỚI' if copy.get('region')=='global' else 'VĨ MÔ')
        copy['semanticCorrection']='currency_unit_not_fx'
    elif current_tag=='DẦU' and 'oil' not in topic_set:
        copy['impactTag']='DOANH NGHIỆP' if copy.get('symbols') else ('THẾ GIỚI' if copy.get('region')=='global' else 'VĨ MÔ')
        copy['semanticCorrection']='oil_word_without_market_context'
    return copy


def realized_reaction(row, bars, horizons=(15,30,60)):
    """Measure raw post-news return from the first bar at/after publication."""
    if not bars or len(row.get('symbols') or []) != 1:
        return None
    try:
        event = datetime.fromisoformat(str(row.get('publishedAt')).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:
        return None
    parsed=[]
    for bar in bars:
        try:
            stamp=datetime.fromisoformat(str(bar.get('time')).replace('Z','+00:00')).astimezone(timezone.utc)
            close=float(bar.get('close'))
        except Exception:
            continue
        if close>0:
            parsed.append((stamp,close))
    if not parsed:
        return None
    parsed.sort()
    base=next(((t,p) for t,p in parsed if t>=event),None)
    if not base or abs((base[0]-event).total_seconds())>45*60:
        return None
    out={'basis':'first_trade_at_or_after_news','baseTime':base[0].isoformat(),'basePrice':base[1]}
    for minutes in horizons:
        target=event+timedelta(minutes=minutes)
        hit=next(((t,p) for t,p in parsed if t>=target),None)
        if hit and hit[0].date()==base[0].date():
            out[f'return{minutes}mPct']=round((hit[1]/base[1]-1)*100,3)
            out[f'time{minutes}m']=hit[0].isoformat()
    same_day=[(t,p) for t,p in parsed if t.date()==base[0].date() and t>=base[0]]
    if same_day:
        out['returnEodPct']=round((same_day[-1][1]/base[1]-1)*100,3)
        out['eodTime']=same_day[-1][0].isoformat()
    return out


def semantic_violations(rows):
    """Return critical false-positive patterns that must never publish green."""
    violations=[]
    for row in rows or []:
        title=compact(row.get('title'))
        text=compact(title+' '+str(row.get('summary') or ''))
        symbols=set(str(x).upper() for x in (row.get('symbols') or []))
        if 'HCM' in symbols and _pattern_any(NEGATIVE_CONTEXT['HCM'],text) and not _issuer_context('HCM',text):
            violations.append({'code':'HCM_CITY_FALSE_POSITIVE','title':title,'symbols':sorted(symbols)})
        if 'VIX' in symbols and _pattern_any(NEGATIVE_CONTEXT['VIX'],text) and not _issuer_context('VIX',text):
            violations.append({'code':'VIX_INDEX_FALSE_POSITIVE','title':title,'symbols':sorted(symbols)})
        if 'VND' in symbols and _pattern_any(NEGATIVE_CONTEXT['VND'],text) and not _issuer_context('VND',text):
            violations.append({'code':'VND_CURRENCY_FALSE_POSITIVE','title':title,'symbols':sorted(symbols)})
        if row.get('impactTag')=='VÀNG' and GOLD_IDIOM.search(text) and not GOLD_EXPLICIT.search(text):
            violations.append({'code':'GOLD_IDIOM_FALSE_TOPIC','title':title,'symbols':sorted(symbols)})
        if row.get('impactTag')=='TỶ GIÁ' and not FX_EXPLICIT.search(text):
            violations.append({'code':'BARE_CURRENCY_FALSE_FX_TOPIC','title':title,'symbols':sorted(symbols)})
    return violations


def parse_24hmoney_symbol_page(raw, symbol, current, companies, aliases=None, base_url=None):
    """Parse public per-symbol article links with the same metadata-only policy."""
    base_url=base_url or f'https://24hmoney.vn/stock/{symbol}/news'
    rows=parse_24hmoney_live(raw,current,companies,aliases,base_url)
    out=[]
    for row in rows:
        syms=set(row.get('symbols') or [])
        if symbol not in syms:
            continue
        row['discoveredVia']='24HMoney Symbol'
        row['symbolDiscovery']=symbol
        if row.get('contentType')=='expert_analysis':
            row['sourceTier']='expert'
            row['sourcePriority']=52
        else:
            row['sourceTier']='trusted_discovery'
            row['sourcePriority']=68
        out.append(row)
    return out

