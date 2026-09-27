"""Merge curated insight seeds from main into the published data snapshot.

Dynamic metadata from financial-report-data wins for dates/rating/target/source.
Curated FinQuery fields (summary/highlights/catalysts/risks) from main are kept
when present, so a stale data snapshot cannot erase newly verified broker seeds.
"""
import argparse
import json
from pathlib import Path

CURATED=('summary','highlights','catalysts','risks')

def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def merge_reports(seed,published):
    by_id={x.get('id'):dict(x) for x in published if x.get('id')}
    by_source={x.get('sourceUrl'):x.get('id') for x in published if x.get('sourceUrl') and x.get('id')}
    for row in seed:
        key=row.get('id') or by_source.get(row.get('sourceUrl'))
        if key and key in by_id:
            merged=by_id[key]
            for field in CURATED:
                if row.get(field):merged[field]=row[field]
            for field in ('brokerName',):
                if row.get(field) and not merged.get(field):merged[field]=row[field]
        else:
            by_id[row['id']]=dict(row)
    return sorted(by_id.values(),key=lambda x:(x.get('publishedAt',''),x.get('broker',''),x.get('symbol','')),reverse=True)

def merge_events(seed,published):
    rows={x.get('id'):dict(x) for x in seed if x.get('id')}
    rows.update({x.get('id'):dict(x) for x in published if x.get('id')})
    return sorted(rows.values(),key=lambda x:(x.get('date',''),x.get('symbol','')),reverse=True)

def merge(seed_dir,target_dir):
    seed_dir=Path(seed_dir);target_dir=Path(target_dir)
    sr=read(seed_dir/'broker-research.json',{'version':2,'reports':[]})
    pr=read(target_dir/'broker-research.json',{'version':2,'reports':[]})
    reports=merge_reports(sr.get('reports') or [],pr.get('reports') or [])
    out={**sr,**pr,'version':max(int(sr.get('version',1)),int(pr.get('version',1)),2),'reports':reports}
    write(target_dir/'broker-research.json',out)

    se=read(seed_dir/'corporate-events.json',{'version':1,'events':[]})
    pe=read(target_dir/'corporate-events.json',{'version':1,'events':[]})
    events=merge_events(se.get('events') or [],pe.get('events') or [])
    eout={**se,**pe,'version':max(int(se.get('version',1)),int(pe.get('version',1))),'events':events}
    write(target_dir/'corporate-events.json',eout)
    print(json.dumps({'reports':len(reports),'events':len(events)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed-dir',required=True);p.add_argument('--target-dir',required=True);a=p.parse_args()
    merge(a.seed_dir,a.target_dir)
