from freeze_v12_source_snapshot_resilient import _ca_cohort_stats

def main():
    payload={'currentHOSESymbols':['A','B','C','D'],'histories':{'A':[{}]*600,'B':[{}]*540,'C':[{}]*400,'D':[{}]*300},'audits':{'A':{'corporateAction':{'verified':True}},'B':{'corporateAction':{'verified':True}},'C':{'originalRows':700,'historyContinuityPolicy':'TRUNCATE_BEFORE_LAST_UNRESOLVED_GT_GUARD_BREAK','corporateAction':{'verified':True}},'D':{'originalRows':300,'corporateAction':{'verified':False}}}}
    z=_ca_cohort_stats(payload,520)
    assert z['cohort']==['A','B','C'],z
    assert z['verified']==['A','B','C'],z
    assert z['ratio']==1.0,z
    assert z['truncated']==['C'] and z['truncatedShort']==['C'],z
    payload['audits']['C']['corporateAction']['verified']=False
    z=_ca_cohort_stats(payload,520)
    assert z['cohort']==['A','B','C'] and len(z['verified'])==2,z
    assert abs(z['ratio']-2/3)<1e-12,z
    print('V12 ORIGINAL-DEEP CA DENOMINATOR PRESERVATION TEST PASS')

if __name__=='__main__':main()
