const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
const src=fs.readFileSync(path.join(root,'frontend/workspace-tabs.js'),'utf8');
const build=fs.readFileSync(path.join(root,'scripts/build_cdn.py'),'utf8');
function harness(){
 const nodes=new Map(),tabs={market:[],macro:[]};
 const make=(id)=>({id,hidden:false,dataset:{},tabIndex:0,classList:{toggle(){}},
  attrs:{},setAttribute(k,v){this.attrs[k]=v;},focus(){},addEventListener(k,fn){this['on_'+k]=fn;},
  querySelectorAll(){return[];}});
 const get=id=>nodes.get(id)||nodes.set(id,make(id)).get(id);
 for(const [group,ids]of Object.entries({market:['stocks','futures','ownership','news'],macro:['overview','on','vbma','swap','esg']})){
  for(const id of ids){const b=make(group+'-'+id);b.dataset[group==='market'?'marketSpace':'macroSpace']=id;tabs[group].push(b);}
  get(group==='market'?'market-primary-tabs':'macro-primary-tabs').querySelectorAll=()=>tabs[group];
 }
 const rootWindow={dispatchEvent(){},FinLiquidityDerivatives:{refresh(){}},FinDerivativeQuotes:{refresh(){}},FinOwnership:{refresh(){}}};
 const ctx={window:rootWindow,document:{getElementById:get},Event:class{},requestAnimationFrame:fn=>fn(),console};
 vm.createContext(ctx);vm.runInContext(src,ctx,{timeout:3000});
 return {api:rootWindow.FinWorkspaceTabs,get,tabs};
}
test('primary tab groups are present and separate from chart-level tabs',()=>{
 assert.match(html,/id="market-primary-tabs"/);
 assert.match(html,/id="macro-primary-tabs"/);
 assert.match(html,/data-macro-panel="on"/);
 assert.match(html,/id="market-futures-workspace"/);
 assert.match(html,/id="market-ownership-workspace"/);
 assert.match(html,/id="market-news-workspace"/);
 assert.match(html,/id="market-stock-view"/);
 assert.equal((html.match(/id="money-futures-live"/g)||[]).length,1);
 assert.match(build,/workspace-tabs\.js/);
 assert.ok(build.includes("(front / 'workspace-tabs.js').read_text()"));
});
test('navigation hides unrelated workspaces but does not destroy DOM',()=>{
 const {api,get,tabs}=harness();
 assert.equal(api.current().market,'stocks');
 assert.equal(api.openMarket('futures'),true);
 assert.equal(get('market').dataset.marketSpace,'futures');
 assert.equal(get('market-stock-view').hidden,true);
 assert.equal(get('market-futures-workspace').hidden,false);
 assert.equal(get('market-ownership-workspace').hidden,true);
 assert.equal(tabs.market[1].attrs['aria-selected'],'true');
 assert.equal(api.openMarket('ownership'),true);
 assert.equal(get('market-ownership-workspace').hidden,false);
 assert.equal(api.openMarket('news'),true);
 assert.equal(get('market-stock-view').hidden,false);
 assert.equal(api.openMarket('wrong'),false);
 assert.equal(api.openMacro('on'),true);
 assert.equal(get('macro-panel-overview').hidden,true);
 assert.equal(get('macro-panel-on').hidden,false);
 assert.equal(api.openMacro('vbma'),true);
 assert.equal(get('macro-panel-vbma').hidden,false);
 assert.equal(get('macro-panel-on').hidden,true);
});
test('multi-indicator chart caps secondary pane count while retaining all calculations',()=>{
 const src=fs.readFileSync(path.join(root,'frontend/chart-engine.js'),'utf8');
 assert.match(src,/visibleOscillators\(\)/);
 assert.match(src,/const osc=this\.visibleOscillators\(\)/);
 assert.match(src,/return \[all\[from\],all\[\(from\+1\)%all\.length\]\]/);
 assert.match(src,/this\.series\.price=this\.chart\.addSeries/);
 assert.match(src,/chartNode\.style\.height=required\+'px'/);
 assert.match(html,/id="chart-oscillator-focus"/);
});
