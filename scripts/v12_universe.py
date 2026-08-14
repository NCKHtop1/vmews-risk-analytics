import json
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
CURRENT_MANIFEST=ROOT/'data'/'hose-fallbacks'/'manifest.json'
DELIST_PATTERNS=('delist','delisted','huy niem yet','hủy niêm yết','inactive','cancelled listing','cancel listing')

def clean(v):return re.sub(r'[^A-Z0-9]','',str(v or '').upper())[:8]
def norm_exchange(v):
    x=str(v or '').upper().strip();return {'HSX':'HOSE','HOCHIMINH':'HOSE','HO CHI MINH':'HOSE'}.get(x,x)
def current_hose_symbols():
    z=json.loads(CURRENT_MANIFEST.read_text(encoding='utf-8'));return set((z.get('routes') or {}).keys())
def _is_delisted_status(v):
    s=str(v or '').strip().lower();return any(p in s for p in DELIST_PATTERNS)
def discover_vnstock_reference():
    out={};audit={}
    try:
        from vnstock import Listing
    except BaseException as e:return out,{'error':f'{type(e).__name__}: {e}'}
    for source in ('VCI','VND'):
        try:
            obj=Listing(source=source)
            try:df=obj.all_symbols(show_log=False)
            except TypeError:df=obj.all_symbols()
            cols={str(c).lower():c for c in df.columns};sc=cols.get('symbol');ec=cols.get('exchange') or cols.get('board');status_col=cols.get('status') or cols.get('listing_status') or cols.get('state');type_col=cols.get('type') or cols.get('instrument_type');found=0
            if sc is not None and ec is not None and status_col is not None:
                for _,r in df.iterrows():
                    sym=clean(r.get(sc));ex=norm_exchange(r.get(ec));typ=str(r.get(type_col,'STOCK')).upper() if type_col is not None else 'STOCK';status=str(r.get(status_col) or '')
                    if sym and ex=='HOSE' and ('STOCK' in typ or typ in {'','EQUITY'}) and _is_delisted_status(status):
                        out[sym]={'symbol':sym,'exchange':'HOSE','isListing':False,'status':status,'discovery':'VNSTOCK_'+source};found+=1
            audit[source]={'rows':len(df),'columns':list(map(str,df.columns)),'delistedHOSE':found}
        except BaseException as e:audit[source]={'error':f'{type(e).__name__}: {e}'}
    return out,audit

def _fireant_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 VMEWS-Research/12','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode('utf-8'))
def discover_fireant():
    base='https://api.fireant.vn/symbols/search';out={};errors=[];seen=0
    for keyword in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        try:
            q=urllib.parse.urlencode({'keywords':keyword,'type':'stock','offset':0,'limit':1000});rows=_fireant_json(base+'?'+q);seen+=len(rows) if isinstance(rows,list) else 0
            for x in rows if isinstance(rows,list) else []:
                sym=clean(x.get('symbol'));ex=norm_exchange(x.get('exchange'));is_listing=x.get('isListing')
                if sym and ex=='HOSE' and is_listing is False:out[sym]={'symbol':sym,'exchange':'HOSE','isListing':False,'name':x.get('name'),'discovery':'FIREANT_PUBLIC_API'}
        except BaseException as e:errors.append({'keyword':keyword,'error':f'{type(e).__name__}: {e}'[:300]})
    return out,{'searchRows':seen,'errors':errors,'delistedHOSE':len(out)}
def discover_candidates():
    current=current_hose_symbols();vn,va=discover_vnstock_reference();fa,faudit=discover_fireant();merged={**fa,**vn}
    for s in list(merged):
        if s in current:merged.pop(s,None)
    return merged,{'currentHOSE':len(current),'vnstockReference':va,'fireant':faudit,'uniqueHistoricalCandidates':len(merged)}
def validate_delisted_cohort(price_loader,current_cutoff,stale_days=20,min_rows=520,max_candidates=120):
    candidates,audit=discover_candidates();validated={};rejected={};cut=(datetime.fromisoformat(current_cutoff).date()-timedelta(days=stale_days)).isoformat()
    for sym,meta in sorted(candidates.items())[:max_candidates]:
        try:
            rows,src=price_loader(sym)
            last=rows[-1]['date'] if rows else ''
            if len(rows)>=min_rows and last<cut:validated[sym]={'symbol':sym,'rows':len(rows),'start':rows[0]['date'],'end':last,'metadata':meta,'priceAudit':src,'history':rows}
            else:rejected[sym]={'reason':'not_stale_delisted_history','rows':len(rows),'end':last,'metadata':meta}
        except BaseException as e:rejected[sym]={'reason':'price_unavailable','error':f'{type(e).__name__}: {e}'[:400],'metadata':meta}
    audit.update({'currentCutoff':current_cutoff,'staleBefore':cut,'validatedHistoricalOnly':len(validated),'rejected':len(rejected),'validatedSymbols':sorted(validated),'rejections':rejected})
    return validated,audit
