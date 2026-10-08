'use strict';
const crypto=require('node:crypto');
const session=require('../lib/ssi-session');
const oauth=require('../lib/ssi-oauth');
function op(req){const raw=req.query?.op;return String(Array.isArray(raw)?raw[0]:raw||'status');}
function originOk(req){return session.incomingMatches(req);}
function restricted(){return process.env.FINQUERY_SSI_OAUTH_BLOCKED==='1';}
module.exports=async function handler(req,res){
 res.setHeader('Cache-Control','private, no-store');
 if(!originOk(req)){session.json(res,503,{enabled:false,connected:false});return;}
 if(op(req)==='status'&&req.method==='GET'){
  const s=session.session(req);
  session.json(res,200,{enabled:true,connected:Boolean(s&&(s.expiresAt>Date.now()||s.refresh)),loginAvailable:!restricted(),reason:restricted()?'ssi_redirect_domain_not_allowed':null,source:'SSI MCP',auth:'oauth'});
  return;
 }
 if(op(req)==='start'&&req.method==='GET'){
  if(restricted()){
   res.redirect(302,session.strictOrigin()+'/?ssi=domain_not_allowed');
   return;
  }
  try{
   const origin=session.strictOrigin(),redirectUri=origin+'/api/ssi-callback';
   const m=await oauth.discovery();
   const client=await oauth.clientId(redirectUri,m);
   const state=crypto.randomBytes(24).toString('base64url');
   const codeVerifier=oauth.verifier();
   session.writeCookie(res,session.PENDING,{client,state,codeVerifier,redirectUri,at:Date.now()},600);
   res.redirect(302,oauth.authorizeUrl(m,client,redirectUri,state,codeVerifier));
  }catch(error){
   if(error?.code==='ssi_redirect_domain_not_allowed'){
    // SSI restricts callback domains. Return to an explanatory screen; never suggest bypassing the allowlist.
    res.redirect(302,session.strictOrigin()+'/?ssi=domain_not_allowed');
   }else{
    session.json(res,502,{enabled:true,connected:false,error:'ssi_oauth_unavailable'});
   }
  }
  return;
 }
 if(op(req)==='logout'&&req.method==='POST'){
  if(String(req.headers?.origin||'')!==session.strictOrigin()){session.json(res,403,{error:'origin_mismatch'});return;}
  session.writeCookie(res,session.SESSION,null,0);
  session.writeCookie(res,session.PENDING,null,0);
  session.json(res,200,{enabled:true,connected:false});
  return;
 }
 session.json(res,405,{error:'invalid_operation'});
};
