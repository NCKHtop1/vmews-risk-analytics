'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {Writable}=require('node:stream');
const Module=require('node:module');
process.env.DATABASE_URL='postgresql://qa:qa@localhost/qa';
process.env.FINQUERY_SESSION_PEPPER='qa-only-streaming-secret-with-more-than-32-characters';
process.env.FINQUERY_GOOGLE_CLIENT_ID='qa-public-client-id';
const previous=Module._load;
Module._load=function(name) {
 if(name==='@neondatabase/serverless')return {neon:()=>async sql=>{
  if(String(sql).includes('SELECT u.id,u.email,u.full_name'))return [{
   id:'11111111-1111-4111-8111-111111111111',
   email:'ordinary@example.com',full_name:'Example',avatar_url:'',
   role:'user',status:'active',session_id:'22222222-2222-4222-8222-222222222222'
  }];
  throw Error('Unexpected SQL');
 }};
 return previous.apply(this,arguments);
};
const handler=require('../api/index');
Module._load=previous;
const cookie='finquery_session='+('a'.repeat(43));
const sizePerChunk=1024*1024,chunksToSend=6;
let upstreamCalls=0;
global.fetch=async url=>{
 upstreamCalls++;
 if(!String(url).endsWith('/data/flow-v12.json'))throw Error('Unexpected URL '+url);
 let sent=0;
 return {
  ok:true,url:String(url),headers:{get:name=>name==='content-type'?'application/json':null},
  body:new ReadableStream({pull(controller){
   if(sent>=chunksToSend){controller.close();return;}
   sent++;controller.enqueue(new Uint8Array(sizePerChunk).fill(49));
  }})
 };
};
function response(){
 let bytes=0;const body=[];
 const writable=new Writable({write(chunk,_encoding,callback){bytes+=chunk.length;body.push(Buffer.from(chunk));callback();}});
 writable.statusCode=200;writable.headers={};
 writable.writeHead=function(status,headers){this.statusCode=status;this.headers=Object.assign({},headers||{});this.headersSent=true;return this;};
 writable.getBytes=()=>bytes;
 writable.getBody=()=>Buffer.concat(body).toString();
 return writable;
}
test('Require a server-side session before large market data can be accessed',async()=>{
 const res=response();
 await handler({method:'GET',url:'/data/flow-v12.json',query:{route:'data/flow-v12.json'},headers:{host:'finquery.info.vn',cookie:''}},res);
 assert.equal(res.statusCode,401);
 assert.equal(upstreamCalls,0,'unauthenticated requests may not hit GitHub Pages');
});
test('Stream large market data, without buffering full 6MB payload in the API function',async()=>{
 const res=response();
 await handler({method:'GET',url:'/data/flow-v12.json',query:{route:'data/flow-v12.json'},headers:{host:'finquery.info.vn',cookie}},res);
 assert.equal(res.statusCode,200);
 assert.equal(res.getBytes(),chunksToSend*sizePerChunk);
 assert.equal(res.headers['Content-Type'],'application/json');
 assert.equal(upstreamCalls,1);
});
