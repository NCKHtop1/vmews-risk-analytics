'use strict';
const crypto=require('node:crypto');
const METADATA='https://mcp.ssi.com.vn/.well-known/oauth-authorization-server';
const ORIGIN='https://mcp.ssi.com.vn';
let cache=null;
function issuerUrl(s){const u=new URL(s);if(u.protocol!=='https:'||u.origin!==ORIGIN||u.username||u.password)throw Error('ssi_invalid_issuer_endpoint');return u.href;}
async function readJson(url,options={},limit=30000){
 const timer=AbortSignal.timeout(7000),resp=await fetch(issuerUrl(url),{...options,redirect:'error',signal:timer});
 const raw=await resp.text();
 if(raw.length>limit)throw Error('ssi_oauth_response_too_large');
 if(!resp.ok)throw Error('ssi_oauth_http_'+resp.status);
 let data;try{data=JSON.parse(raw);}catch{throw Error('ssi_oauth_invalid_json');}
 if(!data||typeof data!=='object')throw Error('ssi_oauth_invalid_response');
 return data;
}
async function discovery(){
 if(cache&&Date.now()-cache.at<600000)return cache.metadata;
 const m=await readJson(METADATA);
 if(m.issuer!==ORIGIN)throw Error('ssi_oauth_issuer_mismatch');
 for(const k of ['authorization_endpoint','token_endpoint','registration_endpoint'])issuerUrl(m[k]);
 if(!Array.isArray(m.grant_types_supported)||!m.grant_types_supported.includes('authorization_code'))throw Error('ssi_oauth_unsupported');
 if(!Array.isArray(m.token_endpoint_auth_methods_supported)||!m.token_endpoint_auth_methods_supported.includes('none'))throw Error('ssi_oauth_confidential_client_required');
 cache={at:Date.now(),metadata:m};
 return m;
}
function verifier(){return crypto.randomBytes(32).toString('base64url');}
function challenge(v){return crypto.createHash('sha256').update(v).digest('base64url');}
async function clientId(redirectUri,metadata=undefined){
 if(process.env.FINQUERY_SSI_CLIENT_ID)return process.env.FINQUERY_SSI_CLIENT_ID;
 const m=metadata||await discovery();
 const payload={client_name:'FinQuery SSI Research',redirect_uris:[redirectUri],grant_types:['authorization_code','refresh_token'],response_types:['code'],token_endpoint_auth_method:'none',scope:'market-data:read'};
 const registration=await readJson(m.registration_endpoint,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(payload)},20000);
 if(typeof registration.client_id!=='string'||registration.client_id.length>400||registration.client_id.length<3)throw Error('ssi_oauth_registration_no_client_id');
 return registration.client_id;
}
function authorizeUrl(m,client,redirectUri,state,codeVerifier){
 const url=new URL(issuerUrl(m.authorization_endpoint));
 const params=url.searchParams;
 params.set('response_type','code');params.set('client_id',client);
 params.set('redirect_uri',redirectUri);params.set('state',state);
 params.set('scope','market-data:read');params.set('code_challenge',challenge(codeVerifier));params.set('code_challenge_method','S256');
 return url.href;
}
async function tokenRequest(fields){
 const m=await discovery();
 const data=await readJson(m.token_endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},body:new URLSearchParams(fields)},24000);
 if(typeof data.access_token!=='string'||!data.access_token||data.access_token.length>10000)throw Error('ssi_oauth_missing_access_token');
 const validFor=Math.max(60,Math.min(86400,Math.trunc(Number(data.expires_in)||3600)));
 return {token:data.access_token,refresh:typeof data.refresh_token==='string'?data.refresh_token:null,expiresAt:Date.now()+validFor*1000-30000};
}
async function exchangeCode(client,code,redirectUri,codeVerifier){
 const session=await tokenRequest({grant_type:'authorization_code',client_id:client,code,redirect_uri:redirectUri,code_verifier:codeVerifier});
 return {...session,clientId:client,issuedAt:Date.now()};
}
async function renew(s){
 if(!s?.refresh)throw Error('ssi_oauth_refresh_unavailable');
 const changed=await tokenRequest({grant_type:'refresh_token',client_id:s.clientId,refresh_token:s.refresh});
 return {...changed,refresh:changed.refresh||s.refresh,clientId:s.clientId,issuedAt:Date.now()};
}
module.exports={discovery,clientId,authorizeUrl,exchangeCode,renew,verifier,challenge,_reset:()=>{cache=null;}};
