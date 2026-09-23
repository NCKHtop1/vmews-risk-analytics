"""Refresh public statements for the CDN; retain last known good reports on failure."""
import argparse,json,os,pathlib,sys,time
from datetime import datetime,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from backend.vnstock_connector import VNStockConnector
from backend.data_validator import validate_dataset
ROOT=pathlib.Path(__file__).resolve().parents[1]
PRIORITY='MBB FPT VCB HPG VNM ACB TCB BID CTG VPB HDB STB TPB VIB SHB SSI VCI HCM VND MBS SHS BVH PVI BIC VIC VHM VRE MWG MSN PNJ GAS PLX DGC GVR SAB VJC POW REE DPM DCM FRT VHC KDH KBC NLG DXG BCM GMD DXP BSR'.split()

def manifest(directory,companies):
    items=[]
    for company in companies:
        p=directory/(company['symbol']+'.json')
        if not p.exists():continue
        try:
            data=validate_dataset(json.loads(p.read_text(encoding='utf-8')))
            if not data['years']:continue
            items.append({**company,'years':data['years'],'reports':{s['id']:s['years'] for s in data['sections']},'rows':sum(len(s['rows']) for s in data['sections'])})
        except (ValueError,KeyError):continue
    value={'schemaVersion':1,'updatedAt':datetime.now(timezone.utc).isoformat(),'companies':items}
    (directory/'manifest.json').write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')))
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'data'));parser.add_argument('--symbols');parser.add_argument('--budget-minutes',type=int,default=45);parser.add_argument('--manifest-only',action='store_true');args=parser.parse_args()
    output=pathlib.Path(args.output);output.mkdir(parents=True,exist_ok=True)
    companies=json.loads((ROOT/'data/companies.json').read_text(encoding='utf-8'))
    if args.manifest_only:
        manifest(output,companies);return
    os.environ.setdefault('VNSTOCK_TELEMETRY','off')
    try:
        from vnstock import Listing
        frame=Listing(source='VCI').symbols_by_exchange()
        fresh=[{'symbol':str(r['symbol']),'name':str(r['organ_name']),'exchange':{'HSX':'HOSE'}.get(str(r['exchange']),str(r['exchange']))} for _,r in frame.iterrows() if r.get('type')=='STOCK' and r.get('exchange') in ['HSX','HOSE','HNX','UPCOM']]
        if len(fresh)>100:companies=fresh
    except Exception as e:print('Company catalog retained:',str(e)[:180],flush=True)
    (output/'companies.json').write_text(json.dumps(companies,ensure_ascii=False,separators=(',',':')))
    symbols=args.symbols.split(',') if args.symbols else [s for s in PRIORITY if not (output/(s+'.json')).exists()]+[c['symbol'] for c in companies if c['symbol'] not in PRIORITY and not (output/(c['symbol']+'.json')).exists()]+[c['symbol'] for c in companies if (output/(c['symbol']+'.json')).exists()]
    metas={c['symbol']:c for c in companies};started=time.monotonic();audit=[];ok=0
    for symbol in symbols:
        if time.monotonic()-started>args.budget_minutes*60:break
        connector=VNStockConnector(output)
        try:
            data=connector.fetch(symbol,refresh=True)
            if not data['years']:raise ValueError('The three core reports do not share any year.')
            data.update({k:v for k,v in metas.get(symbol,{}).items() if k in ('name','exchange')})
            target=output/(symbol+'.json');temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False));temporary.replace(target);ok+=1
            audit.append({'symbol':symbol,'years':data['years'],'reports':connector.audit,'status':'updated'})
            print(symbol,'OK',data['years'],sum(len(s['rows']) for s in data['sections']),flush=True)
        except Exception as e:
            audit.append({'symbol':symbol,'error':str(e)[:250],'reports':connector.audit,'status':'retained' if (output/(symbol+'.json')).exists() else 'unavailable'});print(symbol,'not updated',str(e)[:180],flush=True)
        manifest(output,companies)
    summary=manifest(output,companies);(output/'refresh-status.json').write_text(json.dumps({'updatedAt':summary['updatedAt'],'updated':ok,'availableCompanies':len(summary['companies']),'attempts':audit},ensure_ascii=False,separators=(',',':')))
    print('Published datasets:',len(summary['companies']),'Updated:',ok,flush=True)
if __name__=='__main__':main()
