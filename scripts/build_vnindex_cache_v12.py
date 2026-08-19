import json,math,pathlib
from datetime import datetime,timezone
from v12_data_sources import get_index_history
ROOT=pathlib.Path('.');DATA=ROOT/'data'
rows,audit=get_index_history('VNINDEX')
assert len(rows)>=520,(len(rows),audit)
dates=[str(r.get('date'))[:10] for r in rows];assert dates==sorted(dates) and len(dates)==len(set(dates)),(dates[:3],dates[-3:])
prev=None;max_jump=0.0;max_date=None
for r in rows:
    c=float(r.get('modelClose',r.get('close')))
    assert math.isfinite(c) and c>0,r
    if prev:
        j=abs(math.log(c/prev));
        if j>max_jump:max_jump=j;max_date=r['date']
    prev=c
assert max_jump<=.12,(max_jump,max_date)
out={'version':'VMEWS-VNINDEX-CACHE-12.0.0','generatedAt':datetime.now(timezone.utc).isoformat(),'symbol':'VNINDEX','sourceAudit':audit,'rows':rows,'summary':{'rows':len(rows),'first':dates[0],'last':dates[-1],'duplicateDates':0,'maxAbsLogJump':max_jump,'maxJumpDate':max_date},'policy':'Last-good audited benchmark snapshot. Used only if live VNStock/Yahoo index routes fail; never synthesized from equity cross-section.'}
DATA.mkdir(exist_ok=True);(DATA/'vnindex-v12.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8');print(json.dumps({'vnindexCache':'PASS','summary':out['summary'],'route':audit.get('route')},ensure_ascii=False))
