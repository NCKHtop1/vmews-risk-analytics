(function(root){'use strict';
const VERSION='FINQUERY_RESEARCH_AGENT_V1';
const MAX_AUDIT_ITEMS=12;
const STOP=new Set(['bao','nhieu','hien','tai','the','nao','giai','thich','phan','tich','danh','gia','cho','toi','cua','nay','ma','co','phieu','doanh','nghiep','ky','gan','nhat']);
let lastRun=null;
function norm(v){return String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();}
function finite(v){const n=Number(v);return Number.isFinite(n)?n:null;}
function iso(v){const t=Date.parse(v||'');return Number.isFinite(t)?new Date(t).toISOString():null;}
function ageMin(v){const t=Date.parse(v||'');return Number.isFinite(t)?Math.max(0,(Date.now()-t)/60000):null;}
function clone(v){try{return JSON.parse(JSON.stringify(v));}catch{return null;}}
function pick(obj,keys){const out={};for(const k of keys)if(obj&&obj[k]!==undefined)out[k]=obj[k];return out;}
function trimArray(v,n=8){return Array.isArray(v)?v.slice(0,n):[];}
function summarizeNews(items,n=6){return trimArray(items,n).map(x=>pick(x,['title','source','publisher','publishedAt','date','url','summary','symbols','topics']));}
function activeSymbol(){return String(root.FinancialMarket?.context?.()?.symbol||root.FinancialReportContext?.raw?.()?.symbol||'').toUpperCase();}
function marketCompanies(){try{return root.FinancialMarket?.alertContext?.()?.companies||[];}catch{return[];}}
function resolveTargetSymbol(question){
 try{const f=String(root.FinancialReportContext?.resolveSymbol?.(question)||'').toUpperCase();if(f)return f;}catch{}
 const raw=String(question||''),upper=raw.toUpperCase(),companies=marketCompanies(),symbols=new Set(companies.map(x=>String(x.symbol||'').toUpperCase()).filter(Boolean));
 const tokens=upper.match(/(^|[^A-Z0-9])([A-Z]{3})(?=[^A-Z0-9]|$)/g)||[];
 for(const token of tokens){const symbol=token.replace(/[^A-Z]/g,'');if(symbols.has(symbol))return symbol;}
 const q=norm(raw);const hit=companies.find(x=>{const name=norm(x.name||'');return name.length>=6&&q.includes(name);});
 return String(hit?.symbol||'').toUpperCase();
}
async function prepare(question){
 const requestedSymbol=resolveTargetSymbol(question),before=activeSymbol();
 if(!requestedSymbol||requestedSymbol===before)return{requestedSymbol:requestedSymbol||before,beforeSymbol:before,activeSymbol:before,switched:false,status:'ok',financialAvailable:Boolean(root.FinancialReportContext?.raw?.()?.symbol===before)};
 let marketSwitched=false,financialAvailable=false;
 if(root.FinancialMarket?.select){
  try{marketSwitched=Boolean(root.FinancialMarket.select(requestedSymbol));}catch{}
 }
 const financialCompanies=typeof root.FinancialReportContext?.companies==='function'?root.FinancialReportContext.companies():[];
 const financialSupported=financialCompanies.some(x=>String(x.symbol||'').toUpperCase()===requestedSymbol);
 if(financialSupported&&root.FinancialReportContext?.select){
  try{const loaded=await root.FinancialReportContext.select(requestedSymbol);financialAvailable=String(loaded?.symbol||'').toUpperCase()===requestedSymbol;}catch{financialAvailable=false;}
 }
 const after=activeSymbol();
 if(after!==requestedSymbol&&!marketSwitched){const error=new Error('Khong nap duoc du lieu thi truong '+requestedSymbol+' theo yeu cau.');error.code='SYMBOL_SWITCH_FAILED';throw error;}
 return{requestedSymbol,beforeSymbol:before,activeSymbol:requestedSymbol,switched:true,status:'ok',marketSwitched,financialAvailable};
}
function classify(question){
 const s=norm(question);
 if(/la gi|nghia la gi|cong thuc|cach tinh|do cai gi|the hien gi/.test(s))return'concept';
 if(/phan tich sau|phan tich chuyen sau|phan tich toan dien|ho so nghien cuu|danh gia tong the|tong hop|deep dive/.test(s))return'memo';
 if(/chien luoc|strategy|quet ma|scanner|technical|ky thuat|macd|rsi|bollinger|supertrend|adx|stochastic|volume/.test(s))return'technical';
 if(/nhnn|ngan hang nha nuoc|lai suat|omo|ty gia|lam phat|gdp|pmi|fdi|vi mo|esg/.test(s))return'macro';
 if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';
 if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';
 if(/tai sao|vi sao|phien hom nay|phien nay|bien dong|tang|giam/.test(s))return'movement';
 if(/doanh thu|loi nhuan|dong tien|roe|roa|bien loi nhuan|fcf|ocf|phai thu|ton kho|suc khoe tai chinh/.test(s))return'financial';
 return'general';
}
function plan(question){
 const intent=classify(question),tools=new Set();
 if(['movement','technical','memo','general'].includes(intent))tools.add('market');
 if(['financial','risk','compare','memo','general','concept'].includes(intent))tools.add('financial');
 if(['movement','technical','memo'].includes(intent))tools.add('scanner');
 if(['technical','memo'].includes(intent))tools.add('strategy');
 if(['movement','financial','risk','memo','general'].includes(intent))tools.add('insights');
 if(['movement','memo','general'].includes(intent))tools.add('news');
 if(['macro','movement','memo'].includes(intent))tools.add('macro');
 const s=norm(question);
 if(/co ban|tai chinh|doanh thu|loi nhuan|dong tien|roe|roa/.test(s))tools.add('financial');
 if(/tin|su kien|ctck|bao cao chung khoan/.test(s)){tools.add('insights');tools.add('news');}
 if(/du bao|forecast|t\+3|t\+4|t\+5/.test(s)){tools.add('forecast');tools.add('market');tools.add('scanner');tools.add('financial');}
 return{intent,tools:[...tools],targetSymbol:resolveTargetSymbol(question)};
}
function marketTool(targetSymbol=null){
 let m={},a={};
 try{m=root.FinancialMarket?.context?.()||{};}catch{}
 try{a=root.FinancialMarket?.alertContext?.()||{};}catch{}
 const requested=String(targetSymbol||'').toUpperCase(),symbol=requested||String(m.symbol||a.symbol||'').toUpperCase();
 const same=!symbol||String(m.symbol||'').toUpperCase()===symbol;
 const q=(same?m.quote:null)||a.quotes?.[symbol]||null,d=same?m.driver:null,t=same?m.technical:null;
 return{symbol,quote:q?pick(q,['symbol','price','reference','change','changePct','volume','value','sourceTime','collectedAt','status']):null,driver:d?pick(d,['relativeStrengthPct','volumeRatio20','momentum5dPct','factors']):null,technical:t?pick(t,['timeframe','snapshot','indicators','sourceTime','checkedAt']):null,market:pick(m.market||{},['index','indexChangePct','breadth','sourceTime']),newsCheckedAt:m.newsCheckedAt||null};
}
function financialTool(base,targetSymbol=null){
 if(base?.localFinancialData)return clone(base.localFinancialData);
 const raw=root.FinancialReportContext?.raw?.()||null;if(!raw)return null;
 const expected=String(targetSymbol||activeSymbol()||'').toUpperCase(),actual=String(raw?.symbol||'').toUpperCase();
 if(expected&&actual&&expected!==actual)return null;
 const compact=data=>{if(!data)return null;const ps=(data.periods||data.years||[]).map(String).slice(-8);const rs=(data.sections||[]).flatMap(s=>(s.rows||[]).slice(0,8).map(r=>({label:r.label,unit:r.unit||'',section:s.id||'',values:Object.fromEntries(ps.filter(p=>Number.isFinite(Number(r.values?.[p]))).map(p=>[p,Number(r.values[p])]))}))).slice(0,30);return{periods:ps,updatedAt:data.updatedAt||null,checkedAt:data.checkedAt||null,rows:rs};};
 return{annual:compact(raw.annual||(!raw.quarterly?raw.data:null)),quarterly:compact(raw.quarterly||null)};
}
function scannerTool(){
 const s=root.FinTechnicalScanner?.context?.()||null;if(!s)return null;
 return{checkedAt:s.checkedAt||null,sourceTime:s.sourceTime||null,aligned:s.aligned!==false,current:s.current?pick(s.current,['symbol','tier','cadence','price','changePct','priority','bias','macd','macdSignal','macdHistogram','rsi14','volumeRatio20','signals','sourceTime','barDate']):null,evidence:s.evidence?pick(s.evidence,['signal','sample','horizons','updatedAt']):null,liveCoverage:s.liveCoverage,discoveryCoverage:s.discoveryCoverage};
}
function strategyTool(){
 const s=root.FinStrategyBuilder?.context?.()||null,intel=root.FinStrategyIntelligence?.context?.()||null;
 if(!s&&!intel)return null;
 const m=intel?.model||null;
 return{
  strategy:s?.strategy?pick(s.strategy,['name','join','scope','conditions']):null,
  snapshot:s?.snapshot?pick(s.snapshot,['checkedAt','sourceTime','coverage','liveCoverage','discoveryCoverage']):null,
  matches:trimArray(s?.matches||[],12).map(x=>pick(x,['symbol','tier','cadence','sourceTime','barDate','current'])),
  intelligence:m?{
   selected:intel.selected||null,
   regime:m.regime?pick(m.regime,['id','label','confidence','coverage','metrics']):null,
   topStrategies:trimArray(m.ranking||[],5).map(x=>pick(x,['id','label','family','horizon','risk','score','status','regimeFit','confirmation','selectivity','matchesCount','matchSymbols'])),
   opportunities:trimArray(m.opportunities||[],12).map(x=>({symbol:x.symbol,score:x.score,stance:x.stance,riskScore:x.riskScore,primary:x.primary?pick(x.primary,['id','label','score','strength']):null,strategies:trimArray(x.strategies||[],5).map(y=>pick(y,['id','label','score','strength'])),current:x.row?.current||null})),
   execution:intel.execution||null
  }:null
 };
}
function insightTool(){
 const i=root.FinInsights?.context?.()||null;if(!i)return null;
 return{updatedAt:i.updatedAt||null,consensus:i.consensus||null,brokerResearch:trimArray(i.brokerResearch||[],8).map(x=>pick(x,['broker','title','publishedAt','recommendation','targetPrice','summary','catalysts','risks','sourceUrl'])),corporateEvents:trimArray(i.corporateEvents||[],10).map(x=>pick(x,['id','type','title','date','summary','details','source'])),businessPlans:trimArray(i.businessPlans||[],12).map(x=>pick(x,['year','metric','plan','actual','completionPct','unit','sourceUrl','provider']))};
}
function newsTool(){
 const m=root.FinancialMarket?.context?.()||{};
 return{checkedAt:m.newsCheckedAt||null,company:summarizeNews(m.news||[],8),sector:summarizeNews(m.sectorNews||m.marketNews||[],6),liveFallback:Boolean(m.newsLiveFallback)};
}
function macroTool(question){
 const m=root.FinMacro?.context?.()||null;if(!m)return null;
 const datasets=m.datasets||{},generic=new Set(['macro','kinh','hien','tai','phan','tich','boi','canh','tong','quan']);
 const terms=norm(question).split(' ').filter(x=>x.length>2&&!STOP.has(x)&&!generic.has(x));let selected=[];
 for(const [id,ds] of Object.entries(datasets)){const hay=norm(id+' '+(ds?.name||'')+' '+(ds?.title||''));const score=terms.reduce((n,t)=>n+(hay.includes(t)?1:0),0);if(score)selected.push({id,score,ds});}
 if(!selected.length){
  const canonical=['gdp_growth','pmi','money_supply','fdi'];
  selected=canonical.filter(id=>datasets[id]).map(id=>({id,score:0,ds:datasets[id]}));
  if(!selected.length)selected=Object.entries(datasets).slice(0,3).map(([id,ds])=>({id,score:0,ds}));
 }
 selected.sort((a,b)=>b.score-a.score);
 return{checkedAt:m.checkedAt||null,datasets:selected.slice(0,4).map(({id,ds})=>({id,name:ds?.name||ds?.title||id,source:ds?.source||null,qualityStatus:ds?.qualityStatus||'ok',qualityWarnings:trimArray(ds?.qualityWarnings||[],6),numericColumns:ds?.numericColumns||[],rows:trimArray((ds?.rows||[]).slice(-6),6)})),externalAssessments:trimArray(m.corporateEsg?.externalAssessments||[],6)};
}
function forecastTool(){
 const m=root.FinancialMarket?.context?.()||{};const f=m.forecast||root.FinForecast?.context?.()||null;
 return f?clone(f):{available:false,reason:'Forecast context chua duoc nap trong financial-report.'};
}
const TOOL_REGISTRY={market:({targetSymbol})=>marketTool(targetSymbol),financial:({baseContext,targetSymbol})=>financialTool(baseContext,targetSymbol),scanner:({})=>scannerTool(),strategy:({})=>strategyTool(),insights:({})=>insightTool(),news:({})=>newsTool(),macro:({question})=>macroTool(question),forecast:({})=>forecastTool()};
async function execute(name,args){
 const started=performance?.now?.()??Date.now();try{const result=await TOOL_REGISTRY[name](args);return{name,status:result?'ok':'missing',durationMs:Math.round((performance?.now?.()??Date.now())-started),result};}catch(error){return{name,status:'error',durationMs:Math.round((performance?.now?.()??Date.now())-started),error:String(error?.message||error).slice(0,240),result:null};}
}
function validate(question,intent,results,baseContext){
 const warnings=[],checks=[];const market=results.market?.result||null,scanner=results.scanner?.result||null,news=results.news?.result||null,financial=results.financial?.result||null;
 const current=/hom nay|phien nay|moi nhat|hien tai|live|realtime/.test(norm(question));
 const mt=market?.quote?.sourceTime||market?.quote?.collectedAt||null,st=scanner?.sourceTime||scanner?.checkedAt||null;
 if(mt&&st){const gap=Math.abs(Date.parse(mt)-Date.parse(st))/60000;checks.push({id:'market_scanner_alignment',ok:scanner?.aligned!==false&&gap<=20,gapMinutes:Number.isFinite(gap)?Math.round(gap):null});if(scanner?.aligned===false||gap>20)warnings.push('Technical Scanner khong dong bo voi snapshot gia; bo qua current scanner khi tong hop.');}
 if(current&&mt){const age=ageMin(mt);checks.push({id:'market_freshness',ok:age===null||age<=35,ageMinutes:age===null?null:Math.round(age)});if(age!==null&&age>35)warnings.push('Snapshot gia co the da cu hon nguong phien hien tai.');}
 if(current&&news?.checkedAt){const age=ageMin(news.checkedAt);checks.push({id:'news_freshness',ok:age===null||age<=45,ageMinutes:age===null?null:Math.round(age)});if(age!==null&&age>45)warnings.push('Tin tuc da qua nguong freshness 45 phut.');}
 if(['financial','risk','compare','memo'].includes(intent)){const ok=Boolean(financial&&(financial.annualSummary||financial.quarterSummary||financial.annual||financial.quarterly));checks.push({id:'financial_available',ok});if(!ok)warnings.push('Chua co du du lieu BCTC cho yeu cau nay.');}
 if(['movement','technical','memo'].includes(intent)){const ok=Boolean(market?.quote&&finite(market.quote.price)!==null);checks.push({id:'market_available',ok});if(!ok)warnings.push('Chua co snapshot gia hop le.');}
 const requiredMissing=checks.some(x=>x.ok===false&&['financial_available','market_available'].includes(x.id));
 return{status:requiredMissing?'partial':warnings.length?'warn':'ok',warnings,checks,checkedAt:new Date().toISOString(),baseContextPresent:Boolean(baseContext)};
}
function buildContext(question,planInfo,results,validation,baseContext,sources){
 const scanner=results.scanner?.result;const scannerSafe=scanner&&validation.checks.find(x=>x.id==='market_scanner_alignment'&&x.ok===false)?{...scanner,current:null,discardedCurrent:true}:scanner;
 const evidence={};for(const [name,record] of Object.entries(results)){if(record.status==='ok')evidence[name]=name==='scanner'?scannerSafe:record.result;}
 const cleanBase={...(baseContext||{})};
 if(scannerSafe?.discardedCurrent)cleanBase.technicalScanner=null;
 return{...cleanBase,agent:{version:VERSION,intent:planInfo.intent,targetSymbol:planInfo.targetSymbol||cleanBase.symbol||null,plan:planInfo.tools,validation,evidence,sourceHints:trimArray(sources||[],12),policy:{numbers:'FINQUERY_ANCHORED_ONLY',staleScanner:'EXCLUDE_CURRENT',missing:'STATE_MISSING_DO_NOT_INVENT',recommendations:'NO_BUY_SELL_ADVICE'}}};
}
async function run(question,options={}){
 const q=String(question||'').trim(),prepared=options.prepared||await prepare(q),planInfo=plan(q),startedAt=new Date().toISOString(),scratchpad=[];
 scratchpad.push({type:'symbol',requestedSymbol:prepared.requestedSymbol||null,beforeSymbol:prepared.beforeSymbol||null,activeSymbol:prepared.activeSymbol||null,switched:Boolean(prepared.switched)});
 scratchpad.push({type:'plan',intent:planInfo.intent,tools:planInfo.tools,targetSymbol:planInfo.targetSymbol||prepared.activeSymbol||null});
 const targetSymbol=planInfo.targetSymbol||prepared.activeSymbol||null;
 const calls=await Promise.all(planInfo.tools.map(name=>execute(name,{question:q,baseContext:options.baseContext||null,targetSymbol})));
 const results=Object.fromEntries(calls.map(x=>[x.name,x]));
 for(const call of calls)scratchpad.push({type:'tool',name:call.name,status:call.status,durationMs:call.durationMs,error:call.error||null});
 const validation=validate(q,planInfo.intent,results,options.baseContext||null);scratchpad.push({type:'validate',status:validation.status,warnings:validation.warnings});
 const context=buildContext(q,planInfo,results,validation,options.baseContext||null,options.sources||[]);
 const audit={version:VERSION,intent:planInfo.intent,targetSymbol:planInfo.targetSymbol||prepared.activeSymbol||null,symbol:prepared,plan:planInfo.tools,iterations:2,tools:calls.map(x=>({name:x.name,status:x.status,durationMs:x.durationMs,error:x.error||null})),validation,scratchpad:scratchpad.slice(-MAX_AUDIT_ITEMS),startedAt,completedAt:new Date().toISOString()};
 lastRun={context,audit};try{sessionStorage.setItem('finquery_research_agent_last',JSON.stringify(audit));}catch{}
 return lastRun;
}
function status(){return{version:VERSION,tools:Object.keys(TOOL_REGISTRY),lastRun:lastRun?.audit||null};}
root.FinResearchAgent={version:VERSION,run,prepare,resolveTargetSymbol,plan,classify,status,lastRun:()=>lastRun,tools:()=>Object.keys(TOOL_REGISTRY)};
})(typeof window==='undefined'?globalThis:window);
