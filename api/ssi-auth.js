'use strict';
const crypto=require('node:crypto');
const session=require('../lib/ssi-session');
const oauth=require('../lib/ssi-oauth');
function op(req){const raw=req.query?.op;return String(Array.isArray(raw)?raw[0]:raw||'status');}
function originOk(req){return session.incomingMatches(req);}
module.exports=async function handler(req,res){
 res.setHeader('Cache-Control','private, no-store');
 if(!originOk(req)){session.json(res,503,{enabled:false,connected:false});return;}
 if(op(req)==='status'&&req.method==='GET'){
  const s=session.session(req);
  session.json(res,200,{enabled:true,connected:Boolean(s&&(s.expiresAt>Date.now()||s.refresh)),source:'SSI MCP',auth:'oauth'});
  return;
 }
 if(op(req)==='start'&&req.method==='GET'){
  try{
   const origin=session.strictOrigin(),redirectUri=origin+'/api/ssi-callback';
   const m=await oauth.discovery();
   const client=await oauth.clientId(redirectUri,m);
   const state=crypto.randomBytes(24).toString('base64url');
   const codeVerifier=oauth.verifier();
   session.writeCookie(res,session.PENDING,{client,state,codeVerifier,redirectUri,at:Date.now()},600);
   res.redirect(302,oauth.authorizeUrl(m,client,redirectUri,state,codeVerifier));
  }catch{session.json(res,502,{enabled:true,connected:false,error:'ssi_oauth_unavailable'});}
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
