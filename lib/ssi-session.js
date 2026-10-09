'use strict';
const crypto=require('node:crypto');
const SESSION='fq_ssi_session';
const PENDING='fq_ssi_pending';
const MAX_COOKIE=3900;
function enabled(env=process.env){return env.FINQUERY_SSI_ENABLED==='1'&&/^[a-f0-9]{64}$/i.test(env.FINQUERY_SSI_COOKIE_KEY||'')&&/^https:\/\//.test(env.FINQUERY_SSI_SITE_ORIGIN||'');}
function key(env=process.env){if(!enabled(env))throw Error('ssi_disabled');return Buffer.from(env.FINQUERY_SSI_COOKIE_KEY,'hex');}
function encode(value,env=process.env){
 const iv=crypto.randomBytes(12),cipher=crypto.createCipheriv('aes-256-gcm',key(env),iv);
 const encrypted=Buffer.concat([cipher.update(JSON.stringify(value),'utf8'),cipher.final()]);
 const result=Buffer.concat([iv,cipher.getAuthTag(),encrypted]).toString('base64url');
 if(result.length>MAX_COOKIE)throw Error('ssi_cookie_too_large');
 return result;
}
function decode(value,env=process.env){
 try{
  if(typeof value!=='string'||value.length>MAX_COOKIE||value.length<40)return null;
  const binary=Buffer.from(value,'base64url'),iv=binary.subarray(0,12),tag=binary.subarray(12,28),payload=binary.subarray(28);
  const cipher=crypto.createDecipheriv('aes-256-gcm',key(env),iv);cipher.setAuthTag(tag);
  return JSON.parse(Buffer.concat([cipher.update(payload),cipher.final()]).toString('utf8'));
 }catch{return null;}
}
function readCookie(req,name,env=process.env){
 const all=String(req.headers?.cookie||'').split(';');
 for(const part of all){const i=part.indexOf('=');if(i>=0&&part.slice(0,i).trim()===name)return decode(part.slice(i+1).trim(),env);}
 return null;
}
function writeCookie(res,name,data,maxAge,env=process.env){
 const value=data?encode(data,env):'';
 const parts=[name+'='+value,'HttpOnly','Secure','SameSite=Lax','Path=/','Max-Age='+Math.max(0,Math.trunc(maxAge||0))];
 const previous=res.getHeader?.('Set-Cookie');
 res.setHeader('Set-Cookie',[...(Array.isArray(previous)?previous:previous?[String(previous)]:[]),parts.join('; ')]);
}
function strictOrigin(env=process.env){
 if(!enabled(env))return null;
 try{
  const url=new URL(env.FINQUERY_SSI_SITE_ORIGIN);
  if(url.protocol!=='https:'||url.username||url.password||url.pathname!=='/'||url.search||url.hash)return null;
  if(url.hostname.endsWith('.github.io'))return null;
  return url.origin;
 }catch{return null;}
}
function incomingMatches(req,env=process.env){
 const origin=strictOrigin(env);if(!origin)return false;
 const host=String(req.headers?.host||'').toLowerCase();
 return host===new URL(origin).host.toLowerCase();
}
function json(res,status,data){res.setHeader('Cache-Control','private, no-store');res.setHeader('Content-Type','application/json; charset=utf-8');res.status(status).json(data);}
function session(req,env=process.env){const s=readCookie(req,SESSION,env);return s&&typeof s.token==='string'&&typeof s.clientId==='string'&&s.issuedAt>0?s:null;}
module.exports={SESSION,PENDING,enabled,strictOrigin,incomingMatches,encode,decode,readCookie,writeCookie,json,session};
