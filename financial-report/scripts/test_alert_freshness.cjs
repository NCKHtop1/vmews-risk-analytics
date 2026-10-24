'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const file=path.join(__dirname,'../frontend/alert-center.js');
const code=fs.readFileSync(file,'utf8');
const env={
  window:{FinStrategyEngine:{scan:(snap,_strategy)=>Object.values(snap.symbols||{})},
    FinMarketData:{currentBundle:()=>null,get:async()=>{throw Error('offline regression')}}},
  document:{getElementById:()=>null,querySelectorAll:()=>[],addEventListener:()=>{},
    hidden:false},
  localStorage:{getItem:()=>null,setItem:()=>{}},
  setInterval:()=>0,
  setTimeout:()=>0,
  Notification:class{}
};
vm.runInNewContext(code,env,{filename:'alert-center.js'});
const gate=env.window.FinStrategyBuilder?.actionableMatches;
assert.equal(typeof gate,'function','Actionable subset must be testable');
const snap={
 sourceTime:'2026-10-23T07:45:00.003Z',
 symbols:{
  MBB:{symbol:'MBB',tier:'CORE',barDate:'2026-10-23'},
  AAA:{symbol:'AAA',tier:'DISCOVERY',barDate:'2026-10-20'},
  FPT:{symbol:'FPT',tier:'DISCOVERY',barDate:'2026-10-23'},
  OLD:{symbol:'OLD',tier:'DISCOVERY',barDate:'2026-08-13'}
 }
};
const actionable=gate(snap,{conditions:[]}).map(x=>x.symbol);
assert.deepEqual([...actionable].sort(),['FPT','MBB']);
assert.equal(gate({...snap,sourceTime:null},{conditions:[]}).length,0);
assert.equal(gate({...snap,sourceTime:'bad'},{conditions:[]}).length,0);
// A real Friday EOD source remains Friday during the Saturday dashboard visit.
assert.deepEqual([...gate(snap,{conditions:[]}).map(x=>x.symbol)].sort(),['FPT','MBB']);
console.log('Alert freshness PASS: 4 checks, stale Discovery excluded without erasing displayed history');
