'use strict';
const assert=require('node:assert/strict');
const t=require('node:test');
const { _test:s }=require('../api/ssi-mcp.js');
t('disabled without explicit opt-in and both keys',()=>{assert.equal(s.enabled({}),false);assert.equal(s.enabled({SSI_MCP_ENABLED:'1',SSI_MCP_ACCESS_TOKEN:'token'}),false);assert.equal(s.enabled({SSI_MCP_ENABLED:'1',SSI_MCP_ACCESS_TOKEN:'token',FINQUERY_SSI_GATE_KEY:'key'}),true);});
t('strict ticker input',()=>{assert.equal(s.normalizeSymbol(' fpt '),'FPT');assert.throws(()=>s.normalizeSymbol('FPT;DROP'));assert.throws(()=>s.normalizeSymbol('^VNINDEX'));});
t('only declared read-only tools',()=>{assert.ok(Object.values(s.ALLOWED).every(name=>name.startsWith('marketdata_')));assert.equal(s.ALLOWED.order,undefined);});
t('missing tool fails closed',async()=>{
 const old=global.fetch;
 global.fetch=async()=>({ok:true,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify({jsonrpc:'2.0',id:1,result:{tools:[]}})});
 try{const response=await s.query('FPT','indicators',{token:'test'});assert.equal(response.status,'unsupported');}finally{global.fetch=old;}
});
t('unverified input schema is not guessed',async()=>{
 const old=global.fetch;
 global.fetch=async()=>({ok:true,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify({jsonrpc:'2.0',id:1,result:{tools:[{name:s.ALLOWED.indicators,inputSchema:{required:['page','ticker'],properties:{ticker:{},page:{}}}}]}})});
 try{const response=await s.query('FPT','indicators',{token:'test'});assert.equal(response.status,'schema_unverified');}finally{global.fetch=old;}
});
