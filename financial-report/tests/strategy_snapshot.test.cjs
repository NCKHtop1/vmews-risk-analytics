const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process');
test('strategy snapshot falls back to canonical Discovery technical payload',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'finquery-strategy-'));
 fs.mkdirSync(path.join(dir,'history'),{recursive:true});
 fs.writeFileSync(path.join(dir,'universe.json'),JSON.stringify({symbols:{AAM:{tier:'DISCOVERY'}},counts:{scannerEligible:1}}));
 fs.writeFileSync(path.join(dir,'quotes.json'),JSON.stringify({latestSourceTime:null,quotes:{}}));
 const canonical=path.join(dir,'canonical.json');
 fs.writeFileSync(canonical,JSON.stringify({discoveryTechnical:{AAM:{symbol:'AAM',barDate:'2026-09-30',price:7800,rsi14:61,previousRsi14:55,macd:10,macdSignal:12,macdHistogram:-2,previousMacdHistogram:-3,volume:1000,averageVolume20:800,volumeRatio20:1.25}}}));
 const script=path.join(__dirname,'../scripts/build_strategy_snapshot.cjs');
 cp.execFileSync(process.execPath,[script,dir,canonical],{stdio:'pipe'});
 const out=JSON.parse(fs.readFileSync(path.join(dir,'strategy-indicators.json'),'utf8'));
 assert.equal(out.coverage,1);assert.equal(out.discoveryCoverage,1);assert.equal(out.symbols.AAM.cadence,'EOD');assert.equal(out.symbols.AAM.current.rsi14,61);assert.equal(out.symbols.AAM.previous.rsi14,55);assert.equal(out.symbols.AAM.partial,true);
 fs.rmSync(dir,{recursive:true,force:true});
});