const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),M=require('../frontend/chart-math.js');
const p={sma:3,ema:3,wma:3,vwma:3,rsi:3,fast:2,slow:4,signal:3,bb:3,deviation:2,vma:3,atr:3,adx:3,stoch:3,stochSignal:2,cci:3,roc:2,willr:3,mfi:3,cmf:3,supertrend:3,supertrendFactor:2};
const rows=Array.from({length:20},(_,i)=>({time:`2026-09-${String(i+1).padStart(2,'0')}`,open:100+i,high:102+i,low:99+i,close:101+i,volume:100+i}));
test('Aggregation preserves first open, last close, high/low and total volume',()=>{const r=M.aggregate(rows,'1mo')[0];assert.equal(r.open,100);assert.equal(r.close,120);assert.equal(r.high,121);assert.equal(r.low,99);assert.equal(r.volume,2190);});
test('Minute groups respect Vietnam session boundaries, preserve distinct bars',()=>{const a=rows.slice(0,3).map((b,i)=>({...b,time:Date.parse('2026-09-25T02:00:00Z')/1000+i*60}));assert.equal(M.aggregate(a,'1m').length,3);assert.equal(M.aggregate(a,'5m').length,1);assert.equal(M.aggregate(a,'1h')[0].time,a[0].time);});
test('SMA RSI Bollinger volume MA known results',()=>{const r=M.indicators(rows,p);assert.equal(r[2].sma,102);assert.equal(r[2].vma,101);assert.equal(r[3].rsi,100);assert.ok(Math.abs(r[2].upper-(102+2*Math.sqrt(2/3)))<1e-10);assert.equal(r[1].sma,null);});
test('Expanded pandas-ta compatible indicators produce deterministic values',()=>{const r=M.indicators(rows,p);assert.equal(r[2].wma,(101+2*102+3*103)/6);assert.ok(r[2].vwma>102&&r[2].vwma<103);assert.ok(Math.abs(r[2].roc-200/101)<1e-12);assert.equal(r[1].obv,101);assert.ok(Number.isFinite(r[4].atr));assert.ok(Number.isFinite(r[4].stoch));assert.ok(Number.isFinite(r[4].cci));assert.ok(Number.isFinite(r[4].willr));assert.ok(Number.isFinite(r[4].mfi));assert.ok(Number.isFinite(r[4].cmf));assert.ok(Number.isFinite(r[4].supertrend));});
test('Replacing last candle gives same indicators as full recomputation',()=>{const before=M.indicators(rows,p);const changed=rows.map(b=>({...b}));changed[19].close=115;changed[19].low=114;const incremental=M.point(changed,19,p,before[18]);assert.deepEqual(incremental,M.indicators(changed,p)[19]);const appended=[...changed,{...rows[19],time:'2026-09-21',close:121}];assert.deepEqual(M.point(appended,20,p,incremental),M.indicators(appended,p)[20]);});
test('Bad OHLC dropped and duplicated timestamps deduplicated',()=>{assert.equal(M.cleanBars([rows[0],{...rows[0],close:102}, {...rows[1],low:999}],false).length,1);});

test('Liquidity interpretation distinguishes mild confirmation from average volume',()=>{
 const x=M.liquiditySignal(1.17);
 assert.equal(x.level,'mildly_elevated');
 assert.equal(x.confirmation,'light');
 assert.ok(Math.abs(x.deltaPct-17)<1e-9);
 assert.equal(M.liquiditySignal(1.2).level,'elevated');
 assert.equal(M.liquiditySignal(1.5).level,'surge');
 assert.equal(M.liquiditySignal(.82).level,'thin');
});
test('Money-flow interpretation requires CMF MFI OBV agreement instead of volume alone',()=>{
 assert.equal(M.moneyFlowSignal({cmf:.14,mfi:61,obv:120},{obv:100}).direction,'accumulation');
 assert.equal(M.moneyFlowSignal({cmf:-.16,mfi:38,obv:80},{obv:100}).direction,'distribution');
 assert.equal(M.moneyFlowSignal({cmf:.04,mfi:42,obv:120},{obv:100}).direction,'mixed');
});
test('Technical narrative no longer calls 0.7x-1.2x volume normal money flow',()=>{
 const src=fs.readFileSync(require('node:path').join(__dirname,'../frontend/chart-engine.js'),'utf8');
 assert.doesNotMatch(src,/dòng tiền ở mức bình thường/i);
 assert.match(src,/thanh khoản cải thiện nhẹ/i);
 assert.match(src,/chưa đồng thuận, chưa nên kết luận dòng tiền vào hoặc ra rõ/i);
 assert.match(src,/cao hơn.*SMA|thấp hơn.*SMA/i);
});
