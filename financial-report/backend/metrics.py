"""Transparent metrics computed exclusively from the selected financial statements."""
import copy,json,pathlib
DEFINITIONS=json.loads((pathlib.Path(__file__).resolve().parents[1]/'config/derived_metrics.json').read_text())
CHECKS=json.loads((pathlib.Path(__file__).resolve().parents[1]/'config/ratio_checks.json').read_text())
def previous(period,growth=False):
    if '-Q' not in str(period):return str(int(period)-1)
    y,q=int(period[:4]),int(period[-1])
    return f'{y-1}-Q{q}' if growth else f'{y if q>1 else y-1}-Q{q-1 if q>1 else 4}'
def decorate(data):
    d=copy.deepcopy(data);d['sections']=[s for s in d['sections'] if s['id']!='derived_ratios']
    sections={s['id']:s for s in d['sections']}
    periods=sorted({str(p) for s in d['sections'] for r in s['rows'] for p in r['values']})
    def value(ref,p):
        for r in sections.get(ref['section'],{}).get('rows',[]):
            if r['id'] in ref['ids']:return r['values'].get(str(p))
        return None
    source=sections.get('ratios')
    if d.get('periodType')=='quarter' and source and source.get('source')=='KBS':
        original=copy.deepcopy(source.get('rawRows',source['rows']))
        source['rawRows']=original
        source['rows']=copy.deepcopy(original)
        source_rows={r['id']:r for r in original}
        checks={}
        for p in periods:
            matched=0;failed=0
            for c in CHECKS:
                a=value({'section':c['section'],'ids':c['numerator']},p)
                b=value({'section':c['section'],'ids':c['denominator']},p)
                reported=source_rows.get(c['id'],{}).get('values',{}).get(p)
                if a is None or b is None or b<=0 or reported is None:continue
                if abs(a/b*c['scale']-reported)<=c['tolerance']:matched+=1
                else:failed+=1
            accepted=matched>=2 and failed==0
            checks[p]={'matched':matched,'mismatched':failed,'accepted':accepted}
            if not accepted:
                for row in source['rows']:
                    if p in row['values']:row['values'][p]=None
        source['periodChecks']=checks
        source['periods']=source['years']=sorted({p for r in source['rows'] for p,v in r['values'].items() if v is not None})
        source['qualityStatus']='periods_checked' if source['periods'] else 'periods_unverified'
    rows=[]
    for m in DEFINITIONS:
        values={}
        for p in periods:
            a=value(m['numerator'],p);result=None
            if a is not None:
                if m.get('add'):
                    b=value(m['add'],p)
                    if b is not None:result=a+b
                else:
                    b=value(m['denominator'],previous(p,True) if m.get('growth') else p)
                    if m.get('average'):
                        prior=value(m['denominator'],previous(p));b=(b+prior)/2 if b is not None and prior is not None else None
                    valid_basis=not m.get('cashBasis') or d.get('periodType')!='quarter' or sections.get('cash_flow',{}).get('basis')=='quarter'
                    if b is not None and b>0 and valid_basis:result=((a-b) if m.get('growth') else a)/b*m['scale']
            values[p]=result
        if any(v is not None for v in values.values()):rows.append({'id':'derived_'+m['id'],'label':m['label'],'unit':m['unit'],'values':values})
    if rows:
        p=sorted({p for r in rows for p,v in r['values'].items() if v is not None})
        if d.get('periodType')!='quarter':p=list(map(int,p))
        d['sections'].append({'id':'derived_ratios','name':'Chỉ số tính từ báo cáo tài chính','source':'calculated','rows':rows,'years':p,'periods':p})
    if d.get('quarterly'):d['quarterly']=decorate(d['quarterly'])
    return d
