'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const core=require(path.resolve(__dirname,'../frontend/strategy-intelligence-core.js'));
const engine=require(path.resolve(__dirname,'../frontend/strategy-engine.js'));

function row(symbol,{price=30000,sma20=29000,sma50=27000,ema9=30500,ema20=29500,ema50=27500,rsi14=58,macd=.8,macdSignal=.4,macdHistogram=.4,adx14=30,volumeRatio20=1.6,roc10=4,bbPctB=.65,atr14=600,changePct=1.2,tier='CORE'}={}){
 return{symbol,tier,cadence:'LIVE_15M',current:{price,sma20,sma50,ema9,ema20,ema50,rsi14,macd,macdSignal,macdHistogram,adx14,volumeRatio20,roc10,bbPctB,atr14,changePct},previous:{price:price*.99,sma20:sma20*.998,sma50:sma50*.998,ema9:ema9*.995,ema20:ema20*.998,ema50:ema50*.998,rsi14:rsi14-3,macd:macd-.4,macdSignal,macdHistogram:macdHistogram-.5,adx14:adx14-1,volumeRatio20:1.1,roc10:roc10-1,bbPctB:bbPctB-.05,atr14,changePct:.2}};
}
const symbols={};
for(let i=0;i<30;i++)symbols['A'+String(i).padStart(2,'0')]=row('A'+String(i).padStart(2,'0'),{tier:i<20?'CORE':'LIQUID'});
symbols.MEAN=row('MEAN',{price:9500,sma20:10000,sma50:10100,ema9:9700,ema20:9900,ema50:10000,rsi14:28,macd:-.4,macdSignal:-.2,macdHistogram:-.2,adx14:18,volumeRatio20:.9,roc10:-3,bbPctB:.02,atr14:350,changePct:-1});
const snapshot={coverage:Object.keys(symbols).length,sourceTime:'2026-10-07T07:00:00Z',symbols};
const risk={overall:{score:38},marketCounts:{advancing:25,declining:4,unchanged:2},topRisk:[{symbol:'A00',score:42}]};

const regime=core.inferRegime(snapshot,risk);
assert.equal(regime.id,'UPTREND_STRONG');
assert.ok(regime.confidence>=50&&regime.confidence<=94);
const ranked=core.rankStrategies(snapshot,risk,engine);
assert.equal(ranked.regime.id,'UPTREND_STRONG');
assert.ok(ranked.ranking.length>=5);
assert.ok(['breakout_volume','ema_adx'].includes(ranked.ranking[0].id));
assert.ok(ranked.ranking.every(x=>!Object.hasOwn(x,'sharpe')&&!Object.hasOwn(x,'oos')));
const opps=core.rankOpportunities(ranked.ranking,snapshot,risk);
assert.ok(opps.length>0);
assert.ok(opps[0].score>=0&&opps[0].score<=100);
const view=core.investmentView(opps[0].symbol,opps,ranked.regime);
assert.ok(view.positives.length>0);
assert.ok(view.cautions.length>0);
assert.ok(/mất hiệu lực|Theo dõi mất hiệu lực/i.test(view.invalidation));

assert.equal(core.tickSize(9990),10);
assert.equal(core.tickSize(10000),50);
assert.equal(core.tickSize(49950),50);
assert.equal(core.tickSize(50000),100);
assert.equal(core.normalizeOrderQuantity(3765),3700);
assert.equal(core.normalizeOrderQuantity(99),0);
const band=core.priceBand(50000);
assert.equal(band.floor,46500);
assert.equal(band.ceiling,53500);
const exec=core.executionProfile();
assert.equal(exec.exchange,'HOSE');
assert.equal(exec.boardLot,100);
assert.equal(exec.settlement,'T+2');
assert.equal(exec.priceBandPct,7);

console.log(JSON.stringify({status:'ok',version:core.VERSION,regime:regime.id,top:ranked.ranking[0].id,opportunities:opps.length,execution:{boardLot:exec.boardLot,priceBandPct:exec.priceBandPct}},null,2));
