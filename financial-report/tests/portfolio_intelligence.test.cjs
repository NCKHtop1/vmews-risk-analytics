'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'portfolio.html'),'utf8');
const client=fs.readFileSync(path.join(root,'portfolio.js'),'utf8');
const server=fs.readFileSync(path.resolve(root,'..','finquery-access/api/index.js'),'utf8');
const schema=fs.readFileSync(path.resolve(root,'..','finquery-access/migrations/003_portfolio_ledger.sql'),'utf8');
test('portfolio isolated navigation and complete UI controls',()=>{
 for(const x of ['id="nav"','id="positions"','id="trades"','id="form"','id="sectors"','portfolio.js','id="concentration"'])
 assert.ok(html.includes(x),'Missing '+x);
});
test('server identity comes from verified session, no client userId',()=>{
 assert.match(server,/if \(route === 'api\/user\/portfolio'\) return userPortfolio\(req,res,user\)/);
 assert.match(server,/const user = await session\(req\)/);
 assert.match(server,/user\.id,key,kind,symbol,q,p,f,amount,date/);
 assert.doesNotMatch(server,/data\.userId/);
});
test('server writes protected by strict same-origin and cookie',()=>{
 assert.match(server,/if\(!originAllowed\(req\)\)return json\(res,403/);
 assert.match(server,/FINQUERY_IDEMPOTENCY_CONFLICT/);
 assert.match(server,/FINQUERY_INSUFFICIENT_CASH/);
});
test('ledger is append-only and idempotent at DB level',()=>{
 assert.match(schema,/UNIQUE\(user_id,request_key\)/);
 assert.match(schema,/pg_advisory_xact_lock/);
 assert.match(schema,/FINQUERY_INSUFFICIENT_SHARES/);
 assert.doesNotMatch(schema,/DROP TABLE/);
});
test('frontend no fabricated score, explicit missing valuation',()=>{
 assert.match(client,/missing\.length\?null:cash\+invested/);
 assert.match(client,/không phải sức mạnh tương đối/);
 assert.doesNotMatch(client,/35\/100|GMD.*3000/);
});
test('frontend is parseable JavaScript',()=>{
 new vm.Script(client);
});
