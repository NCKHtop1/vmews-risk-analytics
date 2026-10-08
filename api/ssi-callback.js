'use strict';
const crypto=require('node:crypto');
const session=require('../lib/ssi-session');
const oauth=require('../lib/ssi-oauth');
function equal(a,b){
 if(typeof a!=='string'||typeof b!=='string')return false;
 const x=Buffer.from(a),y=Buffer.from(b);
 return x.length===y.length&&crypto.timingSafeEqual(x,y);
}
module.exports=async function handler(req,res){
 res.setHeader('Cache-Control','private, no-store');
 if(req.method!=='GET'||!session.incomingMatches(req)){session.json(res,403,{error:'unauthorized_callback'});return;}
 const pending=session.readCookie(req,session.PENDING);
 session.writeCookie(res,session.PENDING,null,0);
 const state=String(req.query?.state||''),code=String(req.query?.code||'');
 const origin=session.strictOrigin();
 if(!pending||!equal(state,pending.state)||!pending.at||Date.now()-pending.at>600000||!code||code.length>5000){
  res.redirect(302,origin+'/?ssi=login_failed');return;
 }
 const expectedUri=origin+'/api/ssi-callback';
 if(pending.redirectUri!==expectedUri||typeof pending.client!=='string'||typeof pending.codeVerifier!=='string'){
  res.redirect(302,origin+'/?ssi=login_failed');return;
 }
 try{
  const connected=await oauth.exchangeCode(pending.client,code,expectedUri,pending.codeVerifier);
  session.writeCookie(res,session.SESSION,connected,7*24*3600);
  res.redirect(302,origin+'/?ssi=connected');
 }catch{
  res.redirect(302,origin+'/?ssi=login_failed');
 }
};
