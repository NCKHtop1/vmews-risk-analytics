from datetime import date, timedelta

import v12_source_capture as basecap
import v12_source_capture_methodfix as methodfix


def row(d, close, model_close=None):
    z={"date":d,"open":close,"high":close,"low":close,"close":close,"volume":1.0}
    if model_close is not None:z["modelClose"]=model_close
    return z


def smooth_rows(n, *, break_at=None, break_mult=1.35):
    d0=date(2020,1,1);px=100.0;out=[]
    for i in range(n):
        if i==break_at:px*=break_mult
        elif i:px*=1.001
        out.append(row((d0+timedelta(days=i)).isoformat(),px))
    return out


def audit(rows,yahoo=None,symbol='TST'):
    return basecap._candidate_audit(symbol,rows,{'providerCode':'UNIFIED'},yahoo or [],None,raw_reference_rows=[],raw_reference_audit=None,known_ca_dates=set(),event_reference_audit=None)


def main():
    methodfix.install()
    rows=smooth_rows(700,break_at=100);adjusted,a=audit(rows)
    assert a['eligible'] is True,a
    assert a['historyContinuityPolicy']=='TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK',a
    assert len(adjusted)==600,(len(adjusted),a)
    assert a['safeSuffixStartDate']==rows[100]['date'],a
    assert (a.get('corporateAction') or {}).get('verified') is True,a

    rows=smooth_rows(700,break_at=300);adjusted,a=audit(rows)
    assert a['eligible'] is False,a
    assert len(adjusted)==400,(len(adjusted),a)
    assert 'insufficient_rows' in ' '.join(a.get('ineligibleReasons') or []),a

    rows=smooth_rows(700,break_at=100,break_mult=.5);yh=[]
    for i,r in enumerate(rows):
        raw=float(r['close']);mc=raw*.5 if i<100 else raw;yh.append(row(r['date'],raw,mc))
    adjusted,a=audit(rows,yh)
    assert a['eligible'] is True,a
    assert a['historyContinuityPolicy']=='FULL_HISTORY_CERTIFIED',a
    assert len(adjusted)==700,(len(adjusted),a)

    rows=smooth_rows(700);adjusted,a=audit(rows)
    assert a['eligible'] is True,a
    assert a['historyContinuityPolicy']=='FULL_HISTORY_CERTIFIED',a
    assert len(adjusted)==700

    # Former-UPCOM symbols must not lose a long valid suffix merely because legal UPCOM
    # +/-15% moves exceed the current-HOSE 0.12 guard. The impossible 35% break is still
    # removed; a later +14%/-14% pair remains valid inside the retained UPCOM suffix.
    rows=smooth_rows(700,break_at=100)
    rows[200]=row(rows[200]['date'],rows[200]['close']*1.14)
    adjusted,a=audit(rows,symbol='ADP')
    assert a['eligible'] is True,a
    assert a['historyContinuityPolicy']=='TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK',a
    assert a['safeSuffixStartDate']==rows[100]['date'],a
    assert len(adjusted)==600,(len(adjusted),a)
    ca=a.get('corporateAction') or {}
    assert ca.get('marketRegimePolicy')=='CURRENT_HOSE_BASE_GUARD_WITH_OFFICIAL_PRE_TRANSFER_UPCOM_15PCT_BAND',ca
    assert ca.get('venueAwareGuardIntervalCount',0)>=2,ca

    # The same synthetic +14% observation is not exempted for an ordinary HOSE symbol.
    rows=smooth_rows(700,break_at=100)
    rows[200]=row(rows[200]['date'],rows[200]['close']*1.14)
    adjusted,a=audit(rows,symbol='FPT')
    assert a['eligible'] is False,a
    assert len(adjusted)<520,(len(adjusted),a)

    print('V12 STRICT CONTINUOUS-SUFFIX + HISTORICAL-VENUE SOURCE-CAPTURE TEST PASS')


if __name__=='__main__':main()
