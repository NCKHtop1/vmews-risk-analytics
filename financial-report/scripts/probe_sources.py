"""Read real provider schemas. No synthetic data or availability assumptions."""
import json, os, pathlib, time, traceback
os.environ['VNSTOCK_TELEMETRY']='off'
from vnstock import Finance, Listing
from vnstock.config import Config
Config.REQUEST_TIMEOUT=12
OUT=pathlib.Path(os.environ.get('PROBE_OUT','/tmp/financial-probe'))
OUT.mkdir(parents=True,exist_ok=True)
summary={}
for source in ['KBS','VCI']:
    for ticker in ['MBB','FPT','VCB']:
        try:
            finance=Finance(source=source,symbol=ticker,period='year',get_all=True,show_log=False)
        except Exception as e:
            summary[source+'/'+ticker]={'error':str(e)[:350]};continue
        for kind in ['balance_sheet','income_statement','cash_flow','ratio']:
            key=f'{source}_{ticker}_{kind}'
            try:
                time.sleep(3)
                kw={'period':'year','show_log':False}
                kw.update({'display_mode':'all'} if source=='KBS' else {'lang':'vi','dropna':False})
                df=getattr(finance,kind)(**kw)
                (OUT/(key+'.json')).write_text(df.to_json(orient='split',force_ascii=False),encoding='utf-8')
                summary[key]={'rows':len(df),'columns':[str(x) for x in df.columns],'attrs':df.attrs,'sample':df.head(2).to_dict(orient='records')}
            except Exception as e:
                summary[key]={'error':f'{type(e).__name__}: {e}'[:500]}
            print(key,json.dumps(summary[key],default=str,ensure_ascii=False)[:2000],flush=True)
try:
    df=Listing(source='VCI').symbols_by_exchange()
    (OUT/'companies.json').write_text(df.to_json(orient='records',force_ascii=False),encoding='utf-8')
    summary['listing']={'count':len(df),'columns':list(df.columns)}
except Exception as e:summary['listing']={'error':str(e)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
