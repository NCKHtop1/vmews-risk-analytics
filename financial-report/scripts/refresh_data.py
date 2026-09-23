"""Fair, bounded VN100 refresh; publish checkpoints and keep last good statements."""
import argparse,json,os,pathlib,subprocess,sys,time
from datetime import datetime,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from backend.vnstock_connector import VNStockConnector
from backend.data_validator import validate_dataset
ROOT=pathlib.Path(__file__).resolve().parents[1]

def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False));tmp.replace(path)

def manifest(directory,companies):
    items=[]
    for company in companies:
        p=directory/(company['symbol']+'.json')
        if not p.exists():continue
        try:
            data=validate_dataset(json.loads(p.read_text(encoding='utf-8')))
            q=data.get('quarterly',{})
            items.append({**company,'years':data['years'],'quarters':q.get('periods',[]),
                'reports':{s['id']:s['years'] for s in data['sections']},
                'quarterReports':{s['id']:s['periods'] for s in q.get('sections',[])},
                'updatedAt':data.get('updatedAt'),'quarterUpdatedAt':q.get('updatedAt'),
                'rows':sum(len(s['rows']) for s in data['sections']),
                'quarterRows':sum(len(s['rows']) for s in q.get('sections',[]))})
        except (ValueError,KeyError):continue
    value={'schemaVersion':2,'universe':'VN100','updatedAt':datetime.now(timezone.utc).isoformat(),
        'coverage':{'members':len(companies),'annual':sum(bool(x['years']) for x in items),'quarterly':sum(bool(x['quarters']) for x in items)},'companies':items}
    write(directory/'manifest.json',value)
    return value

def refresh_order(companies,status):
    # Every attempt, including failure, goes to the back of the queue. A failed
    # symbol or newly listed group cannot starve the remaining members.
    priority={'VIC':0,'MBB':1,'FPT':2,'VCB':3}
    return sorted([c['symbol'] for c in companies],key=lambda s:(status.get(s,{}).get('checkedAt',''),priority.get(s,4),s))

def publish(directory):
    if not (directory.parent/'.git').exists():raise ValueError('Publish requires the dedicated data worktree.')
    def git(*args):return subprocess.run(['git','-C',str(directory.parent),*args],check=True,capture_output=True,text=True)
    git('add','--sparse','data')
    changed=git('diff','--cached','--name-only').stdout.strip()
    if changed:
        git('commit','-m','Refresh VN100 annual and quarterly statements')
        git('push','origin','HEAD:refs/heads/financial-report-data')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'data'));parser.add_argument('--symbols');parser.add_argument('--budget-minutes',type=int,default=100);parser.add_argument('--manifest-only',action='store_true');parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    output=pathlib.Path(args.output);output.mkdir(parents=True,exist_ok=True)
    companies=json.loads((ROOT/'data/companies.json').read_text(encoding='utf-8'))
    if args.manifest_only:manifest(output,companies);return
    os.environ.setdefault('VNSTOCK_TELEMETRY','off')
    roster_status='retained'
    try:
        from vnstock import Listing
        listing=Listing(source='VCI');group=listing.symbols_by_group('VN100')
        symbols=list(group['symbol'] if hasattr(group,'columns') else group)
        if len(set(symbols))!=100:raise ValueError('VN100 source did not return exactly 100 unique members.')
        old={c['symbol']:c for c in companies}
        all_companies=listing.symbols_by_exchange()
        for _,r in all_companies.iterrows():
            old[str(r['symbol'])]={'symbol':str(r['symbol']),'name':str(r['organ_name']),'exchange':str(r['exchange']).replace('HSX','HOSE')}
        companies=[old.get(s,{'symbol':s,'name':s,'exchange':'HOSE'}) for s in sorted(symbols)]
        roster_status='updated'
    except Exception as e:print('VN100 catalog retained:',str(e)[:180],flush=True)
    if len({c['symbol'] for c in companies})!=100:raise ValueError('A validated 100-member VN100 roster is required.')
    write(output/'companies.json',companies)
    write(output/'universe.json',{'name':'VN100','source':'vnstock / VCI symbols_by_group','checkedAt':datetime.now(timezone.utc).isoformat(),'status':roster_status,'members':companies})
    status_path=output/'refresh-state.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {}
    symbols=args.symbols.split(',') if args.symbols else refresh_order(companies,status)
    metas={c['symbol']:c for c in companies}
    if any(s not in metas for s in symbols):raise ValueError('Only current VN100 members can be refreshed.')
    started=time.monotonic();audit=[];ok=0
    for i,symbol in enumerate(symbols):
        if time.monotonic()-started>args.budget_minutes*60:break
        connector=VNStockConnector(output)
        attempt={'checkedAt':datetime.now(timezone.utc).isoformat()}
        try:
            data=connector.fetch(symbol,refresh=True)
            data.update({k:v for k,v in metas[symbol].items() if k in ('name','exchange')})
            if data.get('quarterly'):data['quarterly'].update({k:data[k] for k in ('name','exchange') if k in data})
            if not data['years'] and not data.get('quarterly',{}).get('periods'):raise ValueError('No complete core-report period.')
            write(output/(symbol+'.json'),data);ok+=1
            attempt.update({'status':data.get('quarterly',{}).get('refreshStatus','unavailable'),'annualUpdatedAt':data.get('updatedAt'),'quarterUpdatedAt':data.get('quarterly',{}).get('updatedAt')})
            print(symbol,'OK year',data['years'],'quarter',data.get('quarterly',{}).get('periods',[]),flush=True)
        except Exception as e:
            attempt.update({'status':'retained' if (output/(symbol+'.json')).exists() else 'unavailable','error':str(e)[:250]});print(symbol,'not updated',str(e)[:180],flush=True)
        status[symbol]=attempt
        audit.append({'symbol':symbol,**attempt,'reports':connector.audit})
        write(status_path,status)
        summary=manifest(output,companies)
        write(output/'refresh-status.json',{'updatedAt':summary['updatedAt'],'coverage':summary['coverage'],'updated':ok,'attempts':audit})
        if args.publish and (i+1)%5==0:publish(output)
    summary=manifest(output,companies)
    if args.publish:publish(output)
    print('Coverage:',summary['coverage'],'Updated:',ok,flush=True)
if __name__=='__main__':main()
