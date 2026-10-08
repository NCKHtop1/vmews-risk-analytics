const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
test('strategy snapshot falls back to canonical Discovery technical payload',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'finquery-strategy-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 fs.writeFileSync(path.join(dir,'universe.json'),JSON.stringify({eodAsOf:'2026-09-30',scannerSymbols:['AAM'],symbols:{AAM:{tier:'DISCOVERY',scannerEligible:true}},counts:{scannerEligible:1}}));
 fs.writeFileSync(path.join(dir,'quotes.json'),JSON.stringify({latestSourceTime:null,quotes:{}}));
 const canonical=path.join(dir,'canonical.json');
 fs.writeFileSync(canonical,JSON.stringify({eodAsOf:'2026-09-30',scannerSymbols:['AAM'],symbols:{AAM:{tier:'DISCOVERY',scannerEligible:true}},discoveryTechnical:{AAM:{symbol:'AAM',barDate:'2026-09-30',price:7800,rsi14:61,previousRsi14:55,macd:10,macdSignal:12,macdHistogram:-2,previousMacdHistogram:-3,volume:1000,averageVolume20:800,volumeRatio20:1.25}}}));
 const script=path.join(__dirname,'../scripts/build_strategy_snapshot.cjs');
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const out=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8'));
 assert.equal(out.coverage,1);assert.equal(out.discoveryCoverage,1);assert.equal(out.symbols.AAM.cadence,'EOD');assert.equal(out.symbols.AAM.current.rsi14,61);assert.equal(out.symbols.AAM.previous.rsi14,55);assert.equal(out.symbols.AAM.partial,true);
 fs.rmSync(dir,{recursive:true,force:true});
});

test('strategy snapshot excludes stale Discovery rows from current EOD coverage',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'finquery-strategy-stale-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 const bars=[];for(let i=0;i<70;i++){const d=new Date(Date.UTC(2026,6,1+i)).toISOString().slice(0,10),close=9000+i*10;bars.push({time:d,open:close-10,high:close+20,low:close-20,close,volume:500000});}
 bars[bars.length-1]={...bars.at(-1),time:'2026-10-06'};
 fs.writeFileSync(path.join(dir,'history','AAM.json'),JSON.stringify({symbol:'AAM',bars}));
 fs.writeFileSync(path.join(dir,'universe.json'),JSON.stringify({eodAsOf:'2026-10-07',scannerSymbols:['AAM'],symbols:{AAM:{tier:'DISCOVERY',scannerEligible:true}}}));
 fs.writeFileSync(path.join(dir,'quotes.json'),JSON.stringify({latestSourceTime:null,quotes:{}}));
 const canonical=path.join(dir,'canonical.json');fs.writeFileSync(canonical,JSON.stringify({}));
 const script=path.join(__dirname,'../scripts/build_strategy_snapshot.cjs');
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const out=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8'));
 assert.equal(out.status,'partial');assert.equal(out.coverage,0);assert.equal(out.discoveryCoverage,0);assert.equal(out.eodAsOf,'2026-10-07');assert.equal(out.symbols.AAM,undefined);
 fs.rmSync(dir,{recursive:true,force:true});
});


test('live strategy snapshot preserves the prior market snapshot across repeated publisher runs',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'finquery-strategy-live-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 const bars=[];
 for(let i=0;i<90;i++){
  const d=new Date(Date.UTC(2026,6,1+i)).toISOString().slice(0,10),close=10000+i*20;
  bars.push({time:d,open:close-20,high:close+40,low:close-40,close,volume:1000000+i*1000});
 }
 fs.writeFileSync(path.join(dir,'history','AAA.json'),JSON.stringify({symbol:'AAA',bars}));
 fs.writeFileSync(path.join(dir,'universe.json'),JSON.stringify({symbols:{AAA:{tier:'CORE'}}}));
 const canonical=path.join(dir,'canonical.json');fs.writeFileSync(canonical,JSON.stringify({symbols:{AAA:{tier:'CORE'}}}));
 const script=path.join(__dirname,'../scripts/build_strategy_snapshot.cjs');
 const writeQuotes=(stamp,price)=>fs.writeFileSync(path.join(dir,'quotes.json'),JSON.stringify({latestSourceTime:stamp,quotes:{AAA:{symbol:'AAA',status:'ok',price,changePct:1,sourceTime:stamp}}}));
 const t1='2026-10-05T02:15:00.000Z',t2='2026-10-05T02:30:00.000Z';
 writeQuotes(t1,bars.at(-1).close);cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const first=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8')).symbols.AAA;
 bars[bars.length-1]={...bars.at(-1),close:bars.at(-1).close+500,high:bars.at(-1).close+540};
 fs.writeFileSync(path.join(dir,'history','AAA.json'),JSON.stringify({symbol:'AAA',bars}));
 writeQuotes(t2,bars.at(-1).close);cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const second=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8')).symbols.AAA;
 assert.equal(second.previous.price,first.current.price);
 assert.notEqual(second.current.price,second.previous.price);
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const third=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8')).symbols.AAA;
 assert.deepEqual(third.previous,second.previous);
 assert.equal(third.sourceTime,t2);
 fs.rmSync(dir,{recursive:true,force:true});
});


test('live strategy snapshot repairs a previously collapsed comparator',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'finquery-strategy-repair-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 const bars=[];
 for(let i=0;i<90;i++){
  const d=new Date(Date.UTC(2026,6,1+i)).toISOString().slice(0,10),close=10000+i*25;
  bars.push({time:d,open:close-20,high:close+50,low:close-50,close,volume:900000+i*2000});
 }
 fs.writeFileSync(path.join(dir,'history','AAA.json'),JSON.stringify({symbol:'AAA',bars}));
 fs.writeFileSync(path.join(dir,'universe.json'),JSON.stringify({symbols:{AAA:{tier:'CORE'}}}));
 const canonical=path.join(dir,'canonical.json');fs.writeFileSync(canonical,JSON.stringify({symbols:{AAA:{tier:'CORE'}}}));
 const stamp='2026-10-05T07:45:00.000Z';
 fs.writeFileSync(path.join(dir,'quotes.json'),JSON.stringify({latestSourceTime:stamp,quotes:{AAA:{symbol:'AAA',status:'ok',price:bars.at(-1).close,changePct:1,sourceTime:stamp}}}));
 const script=path.join(__dirname,'../scripts/build_strategy_snapshot.cjs');
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const first=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8'));
 const row=first.symbols.AAA;
 first.symbols.AAA.previous={...row.current};
 fs.writeFileSync(path.join(dir,'strategy-indicators.json'),JSON.stringify(first));
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const repaired=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8')).symbols.AAA;
 assert.notDeepEqual(repaired.previous,repaired.current);
 assert.notEqual(repaired.previous.price,repaired.current.price);
 assert.equal(repaired.sourceTime,stamp);
 fs.rmSync(dir,{recursive:true,force:true});
});
