import math,pathlib
from datetime import date,timedelta
ROOT=pathlib.Path(__file__).resolve().parent
parts=sorted((ROOT/'v12_train_parts').glob('*.pyinc'))
code='\n'.join(p.read_text(encoding='utf-8') for p in parts)
ns={'__name__':'v12_benchmark_unit','__file__':str(ROOT/'train_forecast_v12.py')};exec(compile(code,'v12-benchmark-unit-assembled.py','exec'),ns,ns)
start=date(2026,1,1);market_dates=[(start+timedelta(days=i)).isoformat() for i in range(40)]
index=[{'date':d,'close':1000+3*i,'modelClose':1000+3*i,'volume':0} for i,d in enumerate(market_dates)]
# Simulate a stock-specific non-trading date so T+5 maturity is not the fifth VNINDEX session.
stock_dates=[d for i,d in enumerate(market_dates) if i!=8]
rows=[{'date':d,'close':100+1.5*i,'modelClose':100+1.5*i,'volume':1000+i} for i,d in enumerate(stock_dates)]
pub=stock_dates[5]+'T08:00:00+07:00'
sentiment={'symbols':{'FPT':{'items':[{'id':'evt1','publishedAt':pub,'title':'FPT công bố kết quả kinh doanh kiểm thử','label':'POS','sourceQuality':.9,'materiality':.8,'confidence':.9,'event':'EARNINGS','publisher':'TEST','sourceClass':'MAINSTREAM','stream':'MAIN'}]}}}
articles,outcomes=ns['prepare_articles'](sentiment,{'FPT':rows},{'FPT':'Technology'},index);assert outcomes,outcomes;o=outcomes[0];rec=articles['FPT'][0];i=rec['availableIndex'];target=rows[i+5]['date'];assert target!=market_dates[market_dates.index(rec['availableDate'])+5],(target,rec['availableDate'])
assert o['matureDate5']==target and o['benchmarkTargetDate5']==target,o
origin_i=market_dates.index(rec['availableDate']);target_i=market_dates.index(target);expected=math.log(index[target_i]['modelClose']/index[origin_i]['modelClose']);assert abs(o['benchmarkR5']-expected)<1e-12,(o['benchmarkR5'],expected);assert abs(o['ar5']-(o['r5']-expected))<1e-12,o
assert o.get('preBenchmarkAvailable5') is True and isinstance(o.get('preAR5'),float),o
# Missing benchmark is abstention for both post- and pre-event abnormal return.
articles2,outcomes2=ns['prepare_articles'](sentiment,{'FPT':rows},{'FPT':'Technology'},[]);assert outcomes2;z=outcomes2[0];assert z.get('benchmarkAvailable5') is False and z.get('benchmarkR5') is None and z.get('ar5') is None,z;assert z.get('preBenchmarkAvailable5') is False and z.get('preBenchmarkR5') is None and z.get('preAR5') is None,z
print('V12 EXACT VNINDEX BENCHMARK UNIT PASS',{'origin':rec['availableDate'],'stockT5':target,'ordinalMarketT5':market_dates[origin_i+5],'benchmarkR5':o['benchmarkR5'],'ar5':o['ar5']})
