const {test}=require('node:test'),assert=require('node:assert/strict');
const E=require('../frontend/strategy-engine.js');
function row(overrides={}){return{symbol:'AAA',tier:'CORE',current:{macd:2,macdSignal:1,rsi14:55,macdHistogram:.2,ema9:12,ema20:11,ema50:10,adx14:28,price:105,sma20:100,volumeRatio20:1.8,roc10:2},previous:{macd:.5,macdSignal:1,rsi14:48,macdHistogram:-.1,ema9:10,ema20:10.5,ema50:10,adx14:24,price:99,sma20:100,volumeRatio20:1.1,roc10:-1},...overrides};}
test('indicator catalog includes core TA groups',()=>{for(const id of ['rsi14','macd','macdSignal','ema9','adx14','bbPctB','volumeRatio20','cmf20'])assert.ok(E.MAP[id],id);});
test('cross above another indicator works',()=>{const c={left:'macd',op:'cross_up',rightType:'indicator',rightIndicator:'macdSignal'};assert.equal(E.evaluateCondition(row(),c),true);});
test('cross above fixed threshold works',()=>{const c={left:'macdHistogram',op:'cross_up',rightType:'value',rightValue:0};assert.equal(E.evaluateCondition(row(),c),true);});
test('AND strategy requires every condition',()=>{const s={join:'AND',scope:'LIVE',conditions:[{left:'macd',op:'cross_up',rightType:'indicator',rightIndicator:'macdSignal'},{left:'rsi14',op:'gte',rightType:'value',rightValue:50}]};assert.equal(E.evaluateStrategy(row(),s),true);assert.equal(E.evaluateStrategy(row({current:{...row().current,rsi14:45}}),s),false);});
test('LIVE scope excludes Discovery',()=>{const s={join:'OR',scope:'LIVE',conditions:[{left:'rsi14',op:'gte',rightType:'value',rightValue:50}]};assert.equal(E.evaluateStrategy(row({tier:'DISCOVERY'}),s),false);});
test('preset MACD RSI scans matching symbols',()=>{const p=E.PRESETS.macd_rsi,snap={symbols:{AAA:row(),BBB:row({symbol:'BBB',current:{...row().current,rsi14:40}})}};assert.deepEqual(E.scan(snap,p).map(x=>x.symbol),['AAA']);});

test('Strategy Intelligence keeps an explicitly selected supported ticker across refresh',()=>{
 const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
 const snapshot={symbols:{KDC:{symbol:'KDC'},HCM:{symbol:'HCM'}},sourceTime:'2026-10-09T07:45:00Z'};
 const sandbox={
  console,
  document:{getElementById:()=>null,addEventListener(){},hidden:false},
  location:{hash:'#strategy-builder'},
  CSS:{escape:x=>x},
  setTimeout:()=>1,setInterval:()=>1,
  addEventListener(){},
  FinStrategyIntelligenceCore:{
   rankStrategies:()=>({ranking:[],regime:{label:'Trung lập'}}),
   rankOpportunities:()=>[{symbol:'KDC'}],
   investmentView:()=>({symbol:'HCM'}),
   executionProfile:()=>({})
  },
  FinStrategyEngine:{},
  FinStrategyBuilder:{context:()=>({snapshot})}
 };
 sandbox.window=sandbox;
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/strategy-intelligence.js'),'utf8'),sandbox);
 const app=sandbox.FinStrategyIntelligence;
 assert.ok(app,'Strategy Intelligence did not register');
 app.refresh();
 app.selectSymbol('HCM');
 assert.equal(app.context().selected,'HCM');
 app.refresh();
 assert.equal(app.context().selected,'HCM','Refresh must not silently change selected HCM to top opportunity KDC');
 delete snapshot.symbols.HCM;
 app.refresh();
 assert.equal(app.context().selected,'KDC','Unsupported/delisted ticker should safely fall back to a ranked symbol');
});

