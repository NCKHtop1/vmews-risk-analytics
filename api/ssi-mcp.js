'use strict';
// SSI MCP read-only adapter. Disabled unless explicitly configured in server environment.
// Never expose SSI bearer tokens or JSON-RPC transport in browser code.
const ENDPOINT='https://mcp.ssi.com.vn/mcp';
const ALLOWED=Object.freeze({
  income:'marketdata_list_finance_income_statement',
  balance:'marketdata_list_finance_balance_sheet',
  cashflow:'marketdata_list_finance_cash_flow',
  indicators:'marketdata_list_finance_indicator',
  industry:'marketdata_list_company_in_same_industry',
  news:'marketdata_list_company_news',
  events:'marketdata_list_corporate_actions'
});
const SAFE_SYMBOL=/^[A-Z]{3}$/;
function normalizeSymbol(s){const v=String(s||'').trim().toUpperCase();if(!SAFE_SYMBOL.test(v))throw new Error('invalid symbol');return v;}
function enabled(env=process.env){return env.SSI_MCP_ENABLED==='1'&&Boolean(env.SSI_MCP_ACCESS_TOKEN)&&Boolean(env.FINQUERY_SSI_GATE_KEY);}
async function rpc(method,params,options={}){
 const token=options.token||process.env.SSI_MCP_ACCESS_TOKEN;
 if(!token)throw new Error('ssi_not_connected');
 const timeoutMs=Math.min(Math.max(Number(options.timeoutMs)||4500,500),8000);
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
 try{
  const response=await fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json, text/event-stream','Authorization':'Bearer '+token,'MCP-Protocol-Version':'2025-03-26'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:controller.signal,redirect:'error'});
  if(!response.ok)throw new Error('ssi_http_'+response.status);
  const payload=await response.text();
  if(payload.length>250000)throw new Error('ssi_response_too_large');
  const ct=response.headers.get('content-type')||'';
  let data;
  if(ct.includes('text/event-stream')){
   const events=payload.split(/\r?\n/).filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim());
   const parsed=events.filter(x=>x&&x!=='[DONE]').map(x=>{try{return JSON.parse(x);}catch{return null;}}).filter(Boolean);
   data=parsed.findLast(x=>x.result||x.error);
  }else data=JSON.parse(payload);
  if(!data||data.error||!('result' in data))throw new Error('ssi_rpc_error');
  return data.result;
 }finally{clearTimeout(timer);}
}
async function availableTools(options={}){
 const response=await rpc('tools/list',{},options);
 return Array.isArray(response.tools)?response.tools.filter(t=>typeof t.name==='string'):[];
}
async function query(symbol,kind,options={}){
 const s=normalizeSymbol(symbol),tool=ALLOWED[kind];
 if(!tool)throw new Error('unapproved_tool');
 const tools=await availableTools(options);
 const actual=tools.find(t=>t.name===tool);
 if(!actual)return {status:'unsupported',symbol:s,kind,source:'SSI MCP',asOf:null};
 // Do not guess argument names: first check the MCP-advertised schema.
 const fields=actual.inputSchema?.properties||{};
 const key=['symbol','ticker','stockCode','stock_code'].find(k=>Object.prototype.hasOwnProperty.call(fields,k));
 const required=actual.inputSchema?.required||[];
 if(!key||required.some(k=>k!==key))return{status:'schema_unverified',symbol:s,kind,source:'SSI MCP',asOf:null};
 const result=await rpc('tools/call',{name:tool,arguments:{[key]:s}},options);
 if(result.isError)throw new Error('ssi_tool_error');
 return {status:'ok',symbol:s,kind,source:'SSI MCP',asOf:new Date().toISOString(),result};
}
async function handler(req,res){
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET'){res.status(405).json({error:'method_not_allowed'});return;}
 if(!enabled()){res.status(503).json({status:'disabled',source:'SSI MCP'});return;}
 const key=req.headers['x-finquery-ssi-key'];
 if(typeof key!=='string'||key!==process.env.FINQUERY_SSI_GATE_KEY){res.status(403).json({error:'forbidden'});return;}
 try{
  const symbol=normalizeSymbol(req.query?.symbol);
  const kind=String(req.query?.kind||'indicators');
  if(!Object.hasOwn(ALLOWED,kind)){res.status(400).json({error:'invalid_kind'});return;}
  const answer=await query(symbol,kind);
  res.status(200).json(answer);
 }catch(err){
  res.status(502).json({status:'unavailable',source:'SSI MCP',code:/invalid symbol/.test(String(err))?'invalid_symbol':'ssi_unavailable'});
 }
}
module.exports=handler;
module.exports._test={normalizeSymbol,enabled,query,availableTools,rpc,ALLOWED};
