import json, pathlib, importlib.util, statistics
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]
core_path=ROOT/'api'/'stocks.py'
spec=importlib.util.spec_from_file_location('vmews_market_core',core_path)
core=importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

# Never use an unrelated mutual-fund/index proxy as VNINDEX. Try only explicit index symbols;
# otherwise fall back to a transparent HOSE cross-sectional market state.
CANDIDATES=['^VNINDEX.VN','VNINDEX.VN']

def scan_fallback():
    p=ROOT/'data/market-scan.json'
    if not p.exists():return None
    z=json.loads(p.read_text(encoding='utf-8'));rows=[x for x in (z.get('ranking') or []) if x.get('exchange')=='HOSE' and not x.get('stale') and x.get('historyReady') is not False]
    if len(rows)<100:return None
    def vals(k):
        a=[]
        for x in rows:
            try:a.append(float(x.get(k)))
            except:pass
        return a
    mom=vals('mom20');tech=vals('score');trend=vals('trend50');liq=[x for x in rows if x.get('liquid') is not False]
    breadth=sum(x>0 for x in mom)/len(mom) if mom else None;trendBreadth=sum(x>0 for x in trend)/len(trend) if trend else None;riskShare=sum(x>=50 for x in tech)/len(tech) if tech else None
    score=50
    if breadth is not None:score+=25*(.5-breadth)
    if trendBreadth is not None:score+=15*(.5-trendBreadth)
    if riskShare is not None:score+=20*(riskShare-.35)
    score=max(0,min(100,score))
    return {'score':score,'available':True,'date':z.get('dataDate') or z.get('asOf'),'source':'VMEWS HOSE cross-section','provider':'market-scan','rows':len(rows),'liquidRows':len(liq),'breadth20':breadth,'trend50Breadth':trendBreadth,'riskShare':riskShare,'medianMom20':statistics.median(mom) if mom else None,'method':'Cross-sectional HOSE breadth/risk state; no synthetic index price is claimed.'}

def main():
    errors=[]; market=None
    for ticker in CANDIDATES:
        try:
            rows,meta,host=core.yahoo_chart(ticker,'10y',15)
            if len(rows)<500:raise RuntimeError('insufficient direct index history')
            cur,hz,_=core.technical_state(rows);a=hz['20'];score=.65*cur['technical']+.35*(a['score'] if a.get('available') else 50)
            market={'score':score,'available':True,'technical':cur['technical'],'analog20':a,'date':cur['date'],'ticker':ticker,'rows':len(rows),'source':'Direct VNINDEX EOD','provider':host,'audit':[{'provider':host,'symbol':ticker,'rows':len(rows),'ok':True}]}
            break
        except Exception as e:errors.append({'ticker':ticker,'error':str(e)[:300]})
    if not market:market=scan_fallback()
    payload={'generatedAt':datetime.now(timezone.utc).isoformat(),'market':market,'candidates':CANDIDATES,'errors':errors,'method':'Direct VNINDEX if explicitly resolved; otherwise transparent full-HOSE cross-sectional breadth/risk fallback. No unrelated proxy ticker.'}
    p=ROOT/'data/market-context.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    if not market:raise SystemExit('No direct VNINDEX or HOSE cross-sectional context available')

if __name__=='__main__':main()
