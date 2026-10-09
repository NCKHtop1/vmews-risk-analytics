'use strict';
// Minimal MCP streamable HTTP client: initialize -> initialized -> tools/list -> tools/call.
const TARGET='https://mcp.ssi.com.vn/mcp',VERSION='2025-03-26';
const TOOLS=Object.freeze({
 profile:{name:'marketdata_list_company_profile',args:s=>({symbol:s,language:'VN'}),key:'companies'},
 indicators:{name:'marketdata_list_finance_indicator',args:s=>({symbol:s,orderBy:'YearReport',order:'DESC',pageSize:10}),key:'indicators'},
 news:{name:'marketdata_list_company_news',args:s=>({symbol:s,range:'1m',orderBy:'PublicDate',order:'DESC',pageSize:10}),key:'news'},
 peers:{name:'marketdata_list_company_in_same_industry',args:s=>({symbol:s,similarLevel:3,pageSize:10}),key:'companies'},
 events:{name:'marketdata_list_corporate_actions',args:s=>({symbol:s,range:'3m',dateType:'Publicdate',pageSize:10}),key:'corporate_actions'}
});
const normTicker=t=>{const s=String(t||'').trim().toUpperCase();if(!/^[A-Z]{3}$/.test(s))throw Error('bad_ticker');return s;};
function parseSseEvent(raw,id){
 const data=raw.split(/\r?\n/).filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trim()).join('\n');
 if(!data)return null;
 try{const obj=JSON.parse(data);return obj.id===id?obj:null;}catch{return null;}
}
async function payload(response,id){
 const type=response.headers.get('content-type')||'';
 if(type.includes('application/json')){
  const text=await response.text();if(text.length>350000)throw Error('ssi_payload_oversized');return JSON.parse(text);
 }
 if(!type.includes('text/event-stream'))throw Error('ssi_content_type_unsupported');
 if(!response.body?.getReader)throw Error('ssi_stream_unavailable');
 const reader=response.body.getReader(),decoder=new TextDecoder();let pending='',total=0;
 try{
  while(true){
   const {value,done}=await reader.read();if(done)break;
   total+=value.byteLength;if(total>350000)throw Error('ssi_sse_oversized');
   pending+=decoder.decode(value,{stream:true});
   let end;while((end=pending.search(/\r?\n\r?\n/))>=0){
    const event=pending.slice(0,end),separator=pending.slice(end).match(/^\r?\n\r?\n/)[0];
    pending=pending.slice(end+separator.length);
    const match=parseSseEvent(event,id);if(match)return match;
   }
  }
  const match=parseSseEvent(pending,id);if(match)return match;
  throw Error('ssi_sse_no_matching_response');
 }finally{await reader.cancel().catch(()=>{});}
}
class MCP{
 constructor(token){if(typeof token!=='string'||!token)throw Error('ssi_no_token');this.token=token;this.sessionId=null;this.id=0;this.version=VERSION;}
 async post(message,expectsResponse=true,timeoutMs=6500){
  const requestId=message.id,headers={'Accept':'application/json, text/event-stream','Content-Type':'application/json','Authorization':'Bearer '+this.token,'MCP-Protocol-Version':this.version};
  if(this.sessionId)headers['Mcp-Session-Id']=this.sessionId;
  const response=await fetch(TARGET,{method:'POST',headers,body:JSON.stringify(message),signal:AbortSignal.timeout(timeoutMs),redirect:'error'});
  if(!response.ok)throw Error('ssi_transport_'+response.status);
  const sessionId=response.headers.get('mcp-session-id');if(sessionId)this.sessionId=sessionId;
  if(!expectsResponse)return null;
  const reply=await payload(response,requestId);
  if(reply?.error||!Object.prototype.hasOwnProperty.call(reply||{},'result'))throw Error('ssi_rpc_error');
  return reply.result;
 }
 request(method,params,timeout){return this.post({jsonrpc:'2.0',id:++this.id,method,params},true,timeout);}
 async init(){
  const r=await this.request('initialize',{protocolVersion:VERSION,capabilities:{},clientInfo:{name:'finquery-ssi-enrichment',version:'1.0.0'}},6500);
  if(r.protocolVersion&&typeof r.protocolVersion==='string')this.version=r.protocolVersion;
  try{await this.post({jsonrpc:'2.0',method:'notifications/initialized'},false,2200);}catch{
   // Some servers do not require a separate initialized notification.
  }
  return r;
 }
 async tools(){
  const all=[];let cursor=null;
  for(let page=0;page<3;page++){
   const result=await this.request('tools/list',cursor?{cursor}:{},5500);
   if(!Array.isArray(result.tools))throw Error('ssi_missing_tool_list');
   all.push(...result.tools);
   if(!result.nextCursor)break;
   cursor=result.nextCursor;
  }
  return all;
 }
 async call(name,args){return this.request('tools/call',{name,arguments:args},8500);}
}
function unwrap(result){
 if(result?.isError)throw Error('ssi_tool_error');
 if(result?.structuredContent&&typeof result.structuredContent==='object')return result.structuredContent;
 const text=(result?.content||[]).filter(x=>x.type==='text'&&typeof x.text==='string').map(x=>x.text).join('\n');
 if(text.length>300000)throw Error('ssi_data_oversized');
 try{return JSON.parse(text);}catch{throw Error('ssi_data_invalid_json');}
}
function numeric(v){if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
function str(v,max=200){return typeof v==='string'?v.slice(0,max):null;}
function compact(kind,data,symbol){
 const rows=Array.isArray(data?.data?.[TOOLS[kind].key])?data.data[TOOLS[kind].key]:Array.isArray(data?.[TOOLS[kind].key])?data[TOOLS[kind].key]:null;
 if(!rows||data.status==='error')throw Error('ssi_unrecognized_data');
 const same=x=>!x.symbol||String(x.symbol).toUpperCase()===symbol;
 if(kind==='profile')return rows.filter(same).slice(0,1).map(x=>({symbol,companyName:str(x.company_name),industry:str(x.industry_name),sector:str(x.sector),exchange:str(x.exchange),charterCapital:numeric(x.charter_capital),employees:numeric(x.number_of_employee),freeFloat:numeric(x.free_float_rate)}));
 if(kind==='indicators')return rows.filter(same).sort((a,b)=>(Number(b.year_report)||0)-(Number(a.year_report)||0)||(Number(b.length_report)||0)-(Number(a.length_report)||0)).slice(0,10).map(x=>({year:Number(x.year_report),period:Number(x.length_report),revenue:numeric(x.revenue),profit:numeric(x.profit),eps:numeric(x.eps),pe:numeric(x.pe),pb:numeric(x.pb),roe:numeric(x.roe),roa:numeric(x.roa),netProfitMargin:numeric(x.net_profit_margin)}));
 if(kind==='news'){const seen=new Set();return rows.filter(x=>String(x.symbol||'').toUpperCase()===symbol).filter(x=>{const k=String(x.news_id||x.news_source_link||'');if(!k||seen.has(k))return false;seen.add(k);return true;}).slice(0,10).map(x=>({symbol,newsId:str(x.news_id,80),title:str(x.title,240),summary:str(x.short_content,300)?.replace(/<[^>]*>/g,'')||null,publicDate:str(x.public_date,30),publisher:str(x.news_source,80),url:/^https:\/\//i.test(x.news_source_link||'')?str(x.news_source_link,500):null}));}
 if(kind==='peers')return rows.slice(0,12).map(x=>({symbol:str(x.symbol,8),name:str(x.company_name),exchange:str(x.exchange),industryLevel:numeric(x.icb_level)}));
 if(kind==='events')return rows.filter(same).slice(0,10).map(x=>({symbol,eventCode:str(x.event_code,30),name:str(x.event_name||x.event_title),publicDate:str(x.public_date,30),exRightDate:str(x.exright_date,30),recordDate:str(x.record_date,30)}));
 return [];
}
async function research(symbol,kind,token){
 const s=normTicker(symbol),spec=TOOLS[kind];if(!spec)throw Error('ssi_tool_not_allowed');
 const mc=new MCP(token);await mc.init();
 const names=await mc.tools(),listed=names.find(x=>x.name===spec.name);
 if(!listed)return{status:'unsupported',symbol:s,kind,source:'SSI MCP',rows:[]};
 const args=spec.args(s),required=listed.inputSchema?.required||[];
 if(required.some(k=>args[k]===undefined)||!listed.inputSchema?.properties||Object.keys(args).some(k=>!Object.prototype.hasOwnProperty.call(listed.inputSchema.properties,k)))
  return{status:'schema_unverified',symbol:s,kind,source:'SSI MCP',rows:[]};
 const result=unwrap(await mc.call(spec.name,args));
 return{status:'ok',symbol:s,kind,source:'SSI MCP',retrievedAt:new Date().toISOString(),rows:compact(kind,result,s)};
}
module.exports={research,MCP,TOOLS,normTicker,compact,unwrap,parseSseEvent};
