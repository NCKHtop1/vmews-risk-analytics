import gzip
import json
import tempfile
from pathlib import Path

import freeze_v12_source_snapshot_resilient as freeze


def main():
    payload={'currentHOSESymbols':['A','B','C','D'],'histories':{'A':[{}]*600,'B':[{}]*540,'C':[{}]*400,'D':[{}]*300},'audits':{'A':{'corporateAction':{'verified':True}},'B':{'corporateAction':{'verified':True}},'C':{'originalRows':700,'historyContinuityPolicy':'TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK','corporateAction':{'verified':True}},'D':{'originalRows':300,'corporateAction':{'verified':False}}}}
    z=freeze._ca_cohort_stats(payload,520)
    assert z['cohort']==['A','B','C'],z
    assert z['verified']==['A','B','C'],z
    assert z['ratio']==1.0,z
    assert z['truncated']==['C'] and z['truncatedShort']==['C'],z
    payload['audits']['C']['corporateAction']['verified']=False
    z=freeze._ca_cohort_stats(payload,520)
    assert z['cohort']==['A','B','C'] and len(z['verified'])==2,z
    assert abs(z['ratio']-2/3)<1e-12,z

    # Regression for the post-freeze gate itself. The production wrapper must read
    # MIN_ROWS from v12_source_capture.base; v12_source_capture has no MIN_ROWS attr.
    # The previous capture.MIN_ROWS reference failed only after the expensive capture
    # had already completed, wasting the entire source-freeze run.
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);snap=root/'snapshot.json.gz';man=root/'manifest.json';diag=root/'diag.json'
        payload2={'currentHOSESymbols':['A'],'histories':{'A':[{}]*520},'audits':{'A':{'corporateAction':{'verified':True}}}}
        snap.write_bytes(gzip.compress(json.dumps(payload2).encode(),mtime=0))
        man.write_text(json.dumps({'deepHistory':1}),encoding='utf-8')
        old=(freeze.SNAP,freeze.MAN,freeze.DIAG)
        freeze.SNAP,freeze.MAN,freeze.DIAG=snap,man,diag
        try:
            freeze._postvalidate_original_deep_ca_cohort()
            out=json.loads(man.read_text(encoding='utf-8'))
            assert out['corporateActionGateDenominator']==1,out
            assert out['corporateActionGateCohort']=='CURRENT_HOSE_ORIGINAL_DEEP_HISTORY_BEFORE_CONTINUITY_TRUNCATION',out
        finally:
            freeze.SNAP,freeze.MAN,freeze.DIAG=old

    print('V12 ORIGINAL-DEEP CA DENOMINATOR + POSTVALIDATE TEST PASS')

if __name__=='__main__':main()
