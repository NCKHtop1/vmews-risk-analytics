import json
import pathlib
import re
from datetime import datetime, timedelta

ROOT=pathlib.Path(__file__).resolve().parents[1]
CURRENT_MANIFEST=ROOT/'data'/'hose-fallbacks'/'manifest.json'

def clean(v):return re.sub(r'[^A-Z0-9]','',str(v or '').upper())[:8]
def current_hose_symbols():
    z=json.loads(CURRENT_MANIFEST.read_text(encoding='utf-8'));return set((z.get('routes') or {}).keys())

def discover_vnstock_reference():
    out={};audit={}
    try:
        from vnstock import Listing
        df=Listing(source='VCI').symbols_by_exchange(show_log=False)
        stocks=df[df['type'].astype(str).str.upper()=='STOCK'].copy()
        current_map={'HSX':'STO','HNX':'STX','UPCOM':'UPX'}
        cross={}
        for ex,grp in current_map.items():
            q=stocks[stocks['exchange'].astype(str).str.upper()==ex]
            cross[ex]={'rows':len(q),'matchingProductGroup':int((q['product_grp_id'].astype(str).str.upper()==grp).sum()),'expectedProductGroup':grp}
        d=stocks[stocks['exchange'].astype(str).str.upper()=='DELISTED'].copy();groups=d['product_grp_id'].fillna('NULL').astype(str).str.upper().value_counts().to_dict()
        former_hsx=d[d['product_grp_id'].fillna('').astype(str).str.upper()=='STO']
        for _,r in former_hsx.iterrows():
            sym=clean(r.get('symbol'))
            if sym:out[sym]={'symbol':sym,'exchange':'DELISTED','formerExchange':'HOSE','formerProductGroup':'STO','isListing':False,'name':r.get('organ_name'),'shortName':r.get('organ_short_name'),'sid':None if str(r.get('sid'))=='nan' else r.get('sid'),'discovery':'VNSTOCK_VCI_PRODUCT_GROUP_LINEAGE'}
        audit={'version':'VMEWS-VNSTOCK-HISTORICAL-UNIVERSE-12.0.0','rows':len(df),'stockRows':len(stocks),'productGroupMappingEvidence':cross,'delistedStocks':len(d),'delistedProductGroups':groups,'confirmedFormerHOSE':len(out),'confirmedFormerHOSESymbols':sorted(out),'rule':'VCI current HSX stocks map 404/404 to product_grp_id=STO in this snapshot; therefore only DELISTED STOCK rows retaining product_grp_id=STO are accepted as former-HOSE. NULL/UPX/STX delisted rows are not assigned to HOSE.'}
        return out,audit
    except BaseException as e:return out,{'error':f'{type(e).__name__}: {e}'}

def discover_candidates():
    current=current_hose_symbols();vn,va=discover_vnstock_reference();merged={s:m for s,m in vn.items() if s not in current}
    return merged,{'currentHOSE':len(current),'vnstockReference':va,'uniqueHistoricalCandidates':len(merged),'externalUnauthenticatedFallback':'DISABLED: FireAnt probe returned HTTP 401; not used.'}

def validate_delisted_cohort(price_loader,current_cutoff,stale_days=20,min_rows=520,max_candidates=20):
    candidates,audit=discover_candidates();validated={};rejected={};cut=(datetime.fromisoformat(current_cutoff).date()-timedelta(days=stale_days)).isoformat()
    for sym,meta in sorted(candidates.items())[:max_candidates]:
        try:
            rows,src=price_loader(sym);last=rows[-1]['date'] if rows else ''
            if len(rows)>=min_rows and last<cut:validated[sym]={'symbol':sym,'rows':len(rows),'start':rows[0]['date'],'end':last,'metadata':meta,'priceAudit':src,'history':rows}
            else:rejected[sym]={'reason':'not_stale_delisted_history','rows':len(rows),'end':last,'metadata':meta}
        except BaseException as e:rejected[sym]={'reason':'price_unavailable','error':f'{type(e).__name__}: {e}'[:400],'metadata':meta}
    audit.update({'currentCutoff':current_cutoff,'staleBefore':cut,'validatedHistoricalOnly':len(validated),'rejected':len(rejected),'validatedSymbols':sorted(validated),'rejections':rejected})
    return validated,audit
