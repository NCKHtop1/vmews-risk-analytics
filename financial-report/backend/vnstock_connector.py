"""Real vnstock adapter. Public methods only; respects the installed data entitlement."""
import copy
import json
import math
import os
import pathlib
import re
import time
import unicodedata
from datetime import datetime, timezone
from .data_validator import valid_ticker, validate_dataset, validate_period

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = {
    'balance_sheet': 'Bảng cân đối kế toán',
    'income_statement': 'Báo cáo kết quả kinh doanh',
    'cash_flow': 'Báo cáo lưu chuyển tiền tệ',
    'ratios': 'Chỉ số tài chính',
    'notes': 'Thuyết minh báo cáo tài chính',
    'off_balance': 'Chỉ tiêu ngoại bảng',
}

def text(value):
    if value is None or str(value).lower() in ('nan','none','<na>'): return ''
    return str(value).strip()


def number(value):
    if value is None or isinstance(value, bool): return None
    try:
        n = float(value)
        if not math.isfinite(n): return None
        return int(n) if n.is_integer() else n
    except (ValueError, TypeError): return None


def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', text(value).lower().replace('đ','d')).encode('ascii','ignore').decode()).strip()


def repair_legacy_units(data):
    for section in data.get('sections',[]):
        if section['id']=='ratios':continue
        for row in section['rows']:
            if row['unit']=='triệu đồng' and row['id'] in ('outstanding_shares_volume','treasury_stocks_volume','foreign_currencies'):
                row['unit']='nguyên tệ' if row['id']=='foreign_currencies' else 'cổ phiếu'
                row['values']={y:None if v is None else round(v*1_000_000,6) for y,v in row['values'].items()}
    return data


def normalize_frame(frame, kind, source):
    """Preserve every returned line, hierarchy, null and zero; reject ambiguous axes."""
    if frame is None or frame.empty: return {'id':kind,'name':REPORTS[kind],'rows':[],'source':source}
    df = frame.copy()
    if not df.columns.is_unique:
        raise ValueError("Nguồn trả cột năm trùng; không dùng nhầm số liệu quý cho năm.")
    # vnstock v4 / vnstock_data long report form (years in columns).
    period_cols = {c: str(c).replace('-Năm','') for c in df.columns if re.fullmatch(r'(19|20)\d{2}(?:-Năm)?', str(c))}
    rows = []
    if period_cols:
        for idx, r in df.iterrows():
            label = next((text(r.get(k)) for k in ('item','name','item_vi','full_name','item_en') if text(r.get(k))), str(idx))
            rid = next((text(r.get(k)) for k in ('item_id','id','field_name') if text(r.get(k))), f'row_{len(rows)}')
            unit = text(r.get('unit'))
            values = {y:number(r.get(c)) for c,y in period_cols.items()}
            level = number(r.get('level', r.get('levels', 0))) or 0
            rows.append({'id':rid,'label':label,'unit':unit,'level':int(level),'values':values})
    else:
        # Older vnstock time-series form. Year/quarter columns may be MultiIndex.
        cols = {c: ' / '.join(map(str,c)) if isinstance(c,tuple) else str(c) for c in df.columns}
        year_col = next((c for c,n in cols.items() if n.split(' / ')[-1] in ('yearReport','year','year_report')),None)
        quarter_col = next((c for c,n in cols.items() if n.split(' / ')[-1] in ('lengthReport','quarter','quarter_report')),None)
        if year_col is None: raise ValueError(f'{source}: không xác định được cột năm.')
        if quarter_col is not None:
            df = df[df[quarter_col].isin([0,5,12,'0','5','12'])]
        if df[year_col].duplicated().any(): raise ValueError('Nhiều bản ghi cùng năm; không tự chọn quý thay báo cáo năm.')
        excluded = {'ticker','symbol','yearReport','year','year_report','lengthReport','quarter','quarter_report','report_period'}
        for c,label in cols.items():
            if label.split(' / ')[-1] in excluded: continue
            rows.append({'id':label,'label':label,'unit':'','level':0,'values':{str(int(r[year_col])):number(r[c]) for _,r in df.iterrows()}})
    # Public vnstock financial statement values are VND. Ratios retain source units.
    used = {}
    for row in rows:
        rid = row['id'];used[rid]=used.get(rid,0)+1
        if used[rid]>1:row['id']=f'{rid}__{used[rid]}'
        label = normalized(row['label'])
        is_per_share = bool(re.search(r'\beps\b|\bbvps\b|tren (mot )?co phieu|moi co phieu|per share',label))
        is_share_count = row['id'] in ('outstanding_shares_volume','treasury_stocks_volume') or 'co phieu' in label and 'so luong' in label
        is_currency_amount = row['id']=='foreign_currencies'
        if kind not in ('ratios',):
            # KBS statement parser scales every row by 1000, including EPS.
            divisor = 1000 if source == 'KBS' and (is_per_share or is_share_count or is_currency_amount) else 1 if (is_per_share or is_share_count or is_currency_amount) else 1_000_000
            row['values']={y:(None if v is None else v/divisor) for y,v in row['values'].items()}
            row['unit']='cổ phiếu' if is_share_count else 'nguyên tệ' if is_currency_amount else 'đồng/cp' if is_per_share else 'triệu đồng'
        elif not row['unit']:
            row['unit']='đồng/cp' if is_per_share else '%' if '%' in row['label'] else ''
    return {'id':kind,'name':REPORTS[kind],'rows':rows,'source':source}


def merge_sections(primary, fallback):
    """Fill only exact label/unit matches; preserve additional indicators, never overwrite."""
    if not primary or not primary.get('rows'):return copy.deepcopy(fallback)
    result=copy.deepcopy(primary)
    index={}
    for r in result['rows']:
        index.setdefault((normalized(r['label']),r['unit']),[]).append(r)
    ids={r['id'] for r in result['rows']}
    for r in fallback.get('rows',[]):
        matches=index.get((normalized(r['label']),r['unit']),[])
        if len(matches)==1:
            for y,v in r['values'].items():
                if matches[0]['values'].get(y) is None and v is not None: matches[0]['values'][y]=v
        elif not matches:
            new=copy.deepcopy(r);new['id']=fallback.get('source','extra')+'__'+r['id']
            while new['id'] in ids:new['id']+='_' 
            result['rows'].append(new);ids.add(new['id'])
    return result


class VNStockConnector:
    def __init__(self, data_dir=None):
        self.data_dir=pathlib.Path(data_dir or ROOT/'data')
        self.audit=[]

    def load_cache(self,ticker):
        path=self.data_dir/(valid_ticker(ticker)+'.json')
        return repair_legacy_units(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else None

    def fetch(self,ticker,refresh=False):
        ticker=valid_ticker(ticker)
        cached=self.load_cache(ticker)
        if cached and not refresh:return validate_dataset(cached)
        os.environ.setdefault('VNSTOCK_TELEMETRY','off')
        from vnstock import Finance
        sections={}
        for source in ('VCI','KBS'):
            try: finance=Finance(source=source,symbol=ticker,period='year',get_all=True,show_log=False)
            except Exception as e:
                self.audit.append({'source':source,'error':str(e)[:240]});continue
            methods = [('balance_sheet','balance_sheet'),('income_statement','income_statement'),('cash_flow','cash_flow')] if source=='VCI' else [(k,k) for k in ('balance_sheet','income_statement','cash_flow') if k not in sections] + [('ratios','ratio')]
            for kind,method in methods:
                try:
                    time.sleep(float(os.environ.get('FINANCIAL_REQUEST_INTERVAL','3')))
                    kwargs={'period':'year','show_log':False}
                    kwargs.update(({'display_mode':'all'} if kind=='ratios' else {}) if source=='KBS' else {'lang':'vi','dropna':False})
                    frame=getattr(finance,method)(**kwargs)
                    section=normalize_frame(frame,kind,source)
                    self.audit.append({'source':source,'report':kind,'rows':len(section['rows'])})
                    if section['rows']: sections[kind]=merge_sections(sections.get(kind),section)
                except Exception as e:self.audit.append({'source':source,'report':kind,'error':str(e)[:240]})
        if cached:
            for old in cached['sections']:
                sections[old['id']]=merge_sections(sections.get(old['id']),old)
        # Explicitly verified local annual reports have priority over provider restatements.
        audited_path=ROOT/'verified'/(ticker+'.json')
        audited=json.loads(audited_path.read_text(encoding='utf-8')) if audited_path.exists() else None
        if audited:
            for section in audited['sections']:
                if section['id']!='ratios':
                    # Keep the reviewed row structure for its historical years.
                    extra=sections.get(section['id'])
                    future_years={int(y) for r in extra['rows'] for y,v in r['values'].items() if v is not None} - set(audited['years']) if extra else set()
                    sections[section['id']]=copy.deepcopy(section)
                    if future_years:
                        clipped=copy.deepcopy(extra)
                        for row in clipped['rows']:row['values']={y:v for y,v in row['values'].items() if int(y) in future_years}
                        sections[section['id']]=merge_sections(sections[section['id']],clipped)
        if not sections:
            if cached:return validate_dataset(cached)
            raise ValueError(f'{ticker}: chưa lấy được dữ liệu báo cáo từ nguồn công bố.')
        data={'schemaVersion':1,'symbol':ticker,'name':(audited or cached or {}).get('name',ticker),'updatedAt':datetime.now(timezone.utc).isoformat(),'sections':[sections[k] for k in REPORTS if k in sections]}
        return validate_dataset(data)

    def get_financial_data(self,ticker,start_year,end_year):
        data=self.fetch(ticker)
        years=validate_period(data,list(range(int(start_year),int(end_year)+1)))
        for section in data['sections']:
            for row in section['rows']:row['values']={y:v for y,v in row['values'].items() if int(y) in years}
        data['years']=years
        return data

    def available_period(self,ticker):
        data=self.fetch(ticker)
        years=data['years']
        return {'years':years,'start':min(years) if years else None,'end':max(years) if years else None}
