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


def normalize_frame(frame, kind, source, period='year'):
    """Preserve every returned line, hierarchy, null and zero; reject ambiguous axes."""
    if frame is None or frame.empty: return {'id':kind,'name':REPORTS[kind],'rows':[],'source':source}
    df = frame.copy()
    if not df.columns.is_unique:
        raise ValueError("Nguồn trả cột năm trùng; không dùng nhầm số liệu quý cho năm.")
    # vnstock v4 / vnstock_data long report form (years in columns).
    pattern = r'(19|20)\d{2}-Q[1-4]' if period == 'quarter' else r'(19|20)\d{2}(?:-Năm)?'
    period_cols = {c: str(c).replace('-Năm','') for c in df.columns if re.fullmatch(pattern, str(c))}
    ambiguous = {re.sub(r'_\d+$','',str(c)) for c in df.columns if re.fullmatch(pattern+r'_\d+',str(c))}
    period_cols = {c:p for c,p in period_cols.items() if p not in ambiguous}
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
            allowed = [1,2,3,4,'1','2','3','4'] if period == 'quarter' else [0,5,12,'0','5','12']
            df = df[df[quarter_col].isin(allowed)]
        elif period == 'quarter': raise ValueError('Thiếu cột quý.')
        period_keys = [f'{int(r[year_col])}-Q{int(r[quarter_col])}' if period == 'quarter' else str(int(r[year_col])) for _,r in df.iterrows()]
        if len(period_keys)!=len(set(period_keys)): raise ValueError('Nguồn trả kỳ báo cáo trùng.')
        excluded = {'ticker','symbol','yearReport','year','year_report','lengthReport','quarter','quarter_report','report_period'}
        for c,label in cols.items():
            if label.split(' / ')[-1] in excluded: continue
            rows.append({'id':label,'label':label,'unit':'','level':0,'values':{p:number(r[c]) for p,(_,r) in zip(period_keys,df.iterrows())}})
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
    basis = 'year_to_date' if period == 'quarter' and kind == 'cash_flow' and source == 'KBS' else 'quarter' if period == 'quarter' and kind in ('income_statement','cash_flow') else 'point_in_time' if kind == 'balance_sheet' else period
    name = REPORTS[kind] + (' (lũy kế từ đầu năm)' if basis == 'year_to_date' else '')
    return {'id':kind,'name':name,'rows':rows,'source':source,'basis':basis}


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
        from vnstock.config import Config
        Config.REQUEST_TIMEOUT=15
        now=datetime.now(timezone.utc).isoformat()
        clients={}
        failures={}
        for source in ('VCI','KBS'):
            try:clients[source]=Finance(source=source,symbol=ticker,period='quarter',get_all=True,show_log=False)
            except Exception as e:failures[source]=str(e)[:240]
        results={}
        for period in ('quarter','year'):
            old=(cached or {}).get('quarterly',{}) if period=='quarter' else (cached or {})
            # Annual statements change much less often. Refresh them daily and all
            # quarter statements on every sweep; a newly added symbol is always fetched.
            if period=='year' and old.get('updatedAt'):
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(old['updatedAt'])).total_seconds()
                if age<86400 and old.get('sections'):
                    results[period]=validate_dataset(copy.deepcopy(old))
                    results[period].pop('quarterly',None)
                    continue
            old_sections={s['id']:s for s in old.get('sections',[])}
            sections={}
            for source in ('VCI','KBS'):
                if source not in clients:
                    self.audit.append({'period':period,'source':source,'error':failures[source]});continue
                # VCI ratio currently returns 2018 rows irrespective of current periods.
                # KBS exposes all usable ratio categories through display_mode=all.
                methods=[(k,k) for k in ('balance_sheet','income_statement','cash_flow') if k not in sections]
                if source=='KBS':methods.append(('ratios','ratio'))
                for kind,method in methods:
                    try:
                        time.sleep(float(os.environ.get('FINANCIAL_REQUEST_INTERVAL','3')))
                        kwargs={'period':period,'show_log':False}
                        kwargs.update(({'display_mode':'all'} if kind=='ratios' else {}) if source=='KBS' else {'lang':'vi','dropna':False})
                        frame=getattr(clients[source],method)(**kwargs)
                        section=normalize_frame(frame,kind,source,period)
                        validate_dataset({'symbol':ticker,'periodType':period,'sections':[section]})
                        if not section['periods']:raise ValueError('Không có kỳ báo cáo hợp lệ.')
                        section['updatedAt']=now
                        sections[kind]=section
                        self.audit.append({'period':period,'source':source,'report':kind,'rows':len(section['rows']),'periods':section['periods']})
                    except Exception as e:self.audit.append({'period':period,'source':source,'report':kind,'error':str(e)[:240]})
            fresh=set(sections)
            for kind,section in old_sections.items():
                if kind not in sections:sections[kind]=copy.deepcopy(section)
                elif sections[kind].get('basis')==section.get('basis',sections[kind].get('basis')):
                    sections[kind]=merge_sections(sections[kind],section)
            audited_path=ROOT/'verified'/(ticker+'.json')
            audited=json.loads(audited_path.read_text(encoding='utf-8')) if period=='year' and audited_path.exists() else None
            if audited:
                for section in audited['sections']:
                    if section['id']=='ratios':continue
                    extra=sections.get(section['id'])
                    future={int(y) for r in extra['rows'] for y,v in r['values'].items() if v is not None}-set(audited['years']) if extra else set()
                    sections[section['id']]=copy.deepcopy(section)
                    sections[section['id']]['updatedAt']=now if section['id'] in fresh else old.get('updatedAt')
                    if future:
                        clipped=copy.deepcopy(extra)
                        for row in clipped['rows']:row['values']={y:v for y,v in row['values'].items() if int(y) in future}
                        sections[section['id']]=merge_sections(sections[section['id']],clipped)
            if not sections:continue
            core_dates=[sections[k].get('updatedAt',old.get('updatedAt','')) for k in ('balance_sheet','income_statement','cash_flow') if k in sections]
            result={'schemaVersion':2,'symbol':ticker,'name':(audited or cached or {}).get('name',ticker),'periodType':period,
                    'updatedAt':min(core_dates) if core_dates and all(core_dates) else old.get('updatedAt'),
                    'checkedAt':now,'refreshStatus':'ok' if all(k in fresh for k in ('balance_sheet','income_statement','cash_flow','ratios')) else 'partial' if fresh else 'retained',
                    'sections':[sections[k] for k in REPORTS if k in sections]}
            results[period]=validate_dataset(result)
        if 'year' not in results:
            raise ValueError(f'{ticker}: chưa lấy được dữ liệu năm từ nguồn công bố.')
        data=results['year']
        if 'quarter' in results:data['quarterly']=results['quarter']
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
