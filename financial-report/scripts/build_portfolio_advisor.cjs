#!/usr/bin/env node
'use strict';
/* Build public, anonymous, read-only strategy portfolios from final EOD history.
 * Invocation: node financial-report/scripts/build_portfolio_advisor.cjs /tmp/market-publish/market
 * Must run AFTER completed daily candles are published; refuses an open session.
 */
const fs=require('node:fs'),path=require('node:path'),child=require('node:child_process');
const Core=require('./portfolio_advisor_core.cjs');
const Proxy=require('./portfolio_advisor_proxy.cjs');
function read(p,fallback=null){try{return JSON.parse(fs.readFileSync(p,'utf8'));}catch{return fallback;}}
function gitSha(dir){try{return child.execFileSync('git',['-C',dir,'rev-parse','HEAD'],{encoding:'utf8',timeout:6000}).trim();}catch{return null;}}
function main(){
 const dir=path.resolve(process.argv[2]||'financial-report/market');
 const historyDir=path.join(dir,'history');
 const now=new Date().toISOString();
 const quotes=read(path.join(dir,'quotes.json'),{});
 const risk=read(path.join(dir,'risk-monitor.json'),{});
 const status=read(path.join(dir,'history-status.json'),{});
 const date=Core.vnDate(quotes.latestSourceTime||quotes.checkedAt)?.date||null;
 const riskDate=String(risk.sourceDate||'');
 const asOf=riskDate||String(status.latestBar||'');
 const sectors=new Map();
 for(const s of risk.sectors||[]){
  for(const r of s.memberRows||[]){
   const symbol=String(r.symbol||'').toUpperCase();
   if(symbol&&s.id)sectors.set(symbol,String(s.id));
  }
 }
 const q=quotes.quotes||{},stocks=[];
 if(fs.existsSync(historyDir)){
  for(const file of fs.readdirSync(historyDir).filter(x=>/^[A-Z0-9]{2,12}\.json$/.test(x))){
   const symbol=path.basename(file,'.json'),quote=q[symbol];
   if(!quote||quote.status==='retained'||!sectors.has(symbol))continue;
   const doc=read(path.join(historyDir,file),{});
   if(doc.interval!=='1D'||!Array.isArray(doc.bars))continue;
   stocks.push({symbol,sectorId:sectors.get(symbol),bars:doc.bars});
  }
 }
 let result=Core.build({asOf,generatedAt:now,quoteDate:date,riskDate,stocks});
 const marketRisk=risk.overall?.score===null||risk.overall?.score===undefined?NaN:Number(risk.overall.score);
 const requiredQuotes=Math.ceil(Math.max(1,Number(quotes.expected)||0)*.90);
 const sourceQuality=quotes.status==='ok'&&risk.status==='ok'&&Number(quotes.coverage)>=requiredQuotes&&Number.isFinite(marketRisk);
 if(!sourceQuality){
  result={...result,status:'BLOCKED',reason:'MARKET_SOURCE_QUALITY',models:{},
   warnings:[...(result.warnings||[]),'Market data quality/coverage/risk status gate failed.']};
 }
 if(sourceQuality&&marketRisk>=85){
  result={...result,status:'BLOCKED',reason:'MARKET_STRESS_GATE',models:{},
   warnings:[...(result.warnings||[]),'Risk Monitor threshold >=85/100; new model allocation suppressed.']};
 }
 result.source={...result.source,marketRevision:gitSha(path.dirname(dir)),
  quoteSourceTime:quotes.latestSourceTime||null,riskMethod:risk.methodVersion||null};
 result.marketRiskScore=Number.isFinite(marketRisk)?marketRisk:null;
 result.researchEvaluation=stocks.length>=30?Proxy.calc(stocks,asOf,{windows:8,holdingSessions:20}):
  {status:'INSUFFICIENT_HISTORY',windows:0};
 // A snapshot is never an account-level instruction, an investment forecast or a trade.
 result.orderExecutionEnabled=false;
 result.personalizedRecommendation=false;
 result.updatedOn='AFTER_VALIDATED_EOD';
 const target=path.join(dir,'portfolio-advisor.json');
 fs.writeFileSync(target,JSON.stringify(result,null,2)+'\n');
 const audit=path.join(dir,'portfolio-advisor-audit');
 fs.mkdirSync(audit,{recursive:true});
 fs.writeFileSync(path.join(audit,asOf+'.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({version:result.version,status:result.status,reason:result.reason||null,
  asOf,coverage:result.coverage,models:Object.fromEntries(Object.entries(result.models||{}).map(([k,v])=>[k,{status:v.status,n:v.positions?.length||0,cashPct:v.cashPct}])),
  proxy:result.researchEvaluation?.status,marketRevision:result.source.marketRevision}));
}
if(require.main===module)main();
module.exports={main};
