'use strict';
const crypto=require('node:crypto');
const sec=require('../lib/ssi-session');
const oauth=require('../lib/ssi-oauth');
const adapter=require('../lib/ssi-transport');
const cache=new Map();
function queryValue(v){return typeof v==='string'?v:Array.isArray(v)?v[0]:'';}
function store(key,value,kind){
 if(cache.size>150)cache.clear();
 cache.set(key,{value,expires:Date.now()+(kind==='news'?120000:600000)});
}
async function handler(req,res){
 if(!sec.incomingMatches(req)){sec.json(res,503,{status:'disabled',source:'SSI MCP'});return;}
 if(req.method!=='GET'){sec.json(res,405,{error:'method_not_allowed'});return;}
 let ss=sec.session(req);
 if(!ss){sec.json(res,401,{status:'not_connected',source:'SSI MCP'});return;}
 let symbol,kind;
 try{
  symbol=adapter.normTicker(queryValue(req.query?.symbol));
  kind=queryValue(req.query?.kind)||'indicators';
  if(!Object.hasOwn(adapter.TOOLS,kind))throw Error('bad_kind');
 }catch{sec.json(res,400,{error:'invalid_request'});return;}
 try{
  if(ss.expiresAt<=Date.now()){
   ss=await oauth.renew(ss);
   sec.writeCookie(res,sec.SESSION,ss,7*24*3600);
  }
  const hashed=crypto.createHash('sha256').update(ss.token+'\0'+symbol+'\0'+kind).digest('hex');
  const item=cache.get(hashed);
  if(item&&item.expires>Date.now()){sec.json(res,200,item.value);return;}
  const answer=await adapter.research(symbol,kind,ss.token);
  if(answer.status==='ok')store(hashed,answer,kind);
  sec.json(res,200,answer);
 }catch{
  sec.json(res,503,{status:'unavailable',source:'SSI MCP',symbol,kind});
 }
}
module.exports=handler;
module.exports._test={queryValue,store,cache};
