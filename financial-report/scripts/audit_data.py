"""Read-only coverage and accounting controls for a published VN100 snapshot."""
import argparse,json,pathlib,sys
from datetime import datetime,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from backend.data_validator import validate_dataset
from backend.metrics import decorate
from backend.vnstock_connector import normalized

def audit(directory):
    companies=json.loads((directory/'companies.json').read_text());errors=[];balance_checks=0;rows=0;quarterly=0;annual=0;source_periods=0;blocked_source_periods=0;details=[]
    if len({c['symbol'] for c in companies})!=100:errors.append('VN100 must contain exactly 100 unique members')
    for company in companies:
        symbol=company['symbol']
        try:data=validate_dataset(json.loads((directory/(symbol+'.json')).read_text()));data=decorate(data)
        except Exception as e:errors.append(f'{symbol}: {e}');continue
        annual+=bool(data['periods']);quarterly+=bool(data.get('quarterly',{}).get('periods'))
        details.append({'symbol':symbol,'years':data['periods'],'quarters':data.get('quarterly',{}).get('periods',[])})
        for d in [data,data.get('quarterly')]:
            if not d:continue
            rows+=sum(len(s['rows']) for s in d['sections'])
            sections={s['id']:s for s in d['sections']};bs=sections.get('balance_sheet',{}).get('rows',[])
            assets=next((r for r in bs if r['id']=='total_assets' or normalized(r['label']) in ('tong tai san','tong cong tai san')),None)
            funding=next((r for r in bs if r['id'] in ('total_resource','total_resources','liabilities_and_shareholders_equity','liabilities_and_shareholders_equities') or normalized(r['label']) in ('tong no phai tra va von chu so huu','tong cong nguon von','tong nguon von')),None)
            for p in d['periods']:
                if assets is None or funding is None:errors.append(f'{symbol} {p}: missing balance control');continue
                a,b=assets['values'].get(str(p)),funding['values'].get(str(p))
                if a is None or b is None:errors.append(f'{symbol} {p}: null balance control')
                elif abs(a-b)>1:errors.append(f'{symbol} {p}: assets/funding differ by {a-b} million VND')
                else:balance_checks+=1
            for p,c in sections.get('ratios',{}).get('periodChecks',{}).items():
                if c['accepted']:source_periods+=1
                else:blocked_source_periods+=1
    return {'checkedAt':datetime.now(timezone.utc).isoformat(),'members':len(companies),'annualCompanies':annual,'quarterlyCompanies':quarterly,'balanceChecks':balance_checks,'indicatorRows':rows,'acceptedQuarterRatioPeriods':source_periods,'quarantinedQuarterRatioPeriods':blocked_source_periods,'errors':errors,'companies':details}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path);a=p.parse_args();result=audit(a.directory)
    if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='companies'},ensure_ascii=False,indent=2));sys.exit(bool(result['errors']))
