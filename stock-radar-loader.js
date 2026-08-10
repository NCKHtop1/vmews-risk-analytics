(()=>{
const css=document.createElement('link');css.rel='stylesheet';css.href='./stock-radar.css';document.head.appendChild(css);const css2=document.createElement('link');css2.rel='stylesheet';css2.href='./stock-radar-v4.css';document.head.appendChild(css2);
function mount(){
 if(document.getElementById('stock-radar'))return;
 const rel=document.querySelector('#reliability h2');if(rel)rel.textContent='Chronological holdout validation.';
 const nav=document.querySelector('.topbar nav');if(nav&&!nav.querySelector('[href="#stock-radar"]')){const a=document.createElement('a');a.href='#stock-radar';a.textContent='Stock Radar';nav.prepend(a)}
 const sec=document.createElement('section');sec.id='stock-radar';sec.className='section shell radar-shell';sec.innerHTML=`
 <div class="section-head"><div><div class="eyebrow">00 · STOCK EARLY-WARNING RADAR</div><h2>Request a stock, a time window, and run the model on that exact data.</h2><p>Price and company-financial data are requested from Vnstock for the selected window. News and macro modules are fetched separately, timestamped, and excluded when unavailable. The current watchlist separates pre-crash warnings from stocks already in a deep drawdown.</p></div><button class="info-btn large" data-radar-info="request">i</button></div>
 <div class="radar-toolbar">
   <div class="radar-query">
     <label>SYMBOL<input id="symbolInput" value="FPT" maxlength="8"></label>
     <label>MODEL AS-OF<input id="asOfDate" type="date"></label>
     <label>FROM<input id="fromDate" type="date"></label>
     <label>TO<input id="toDate" type="date"></label>
     <button id="runStockBtn" class="radar-action primary">Run request</button>
     <button id="fptReplay" class="radar-action">FPT</button>
     <button id="pnjReplay" class="radar-action">PNJ</button>
   </div>
   <div><div id="radarStatus" class="radar-status">Ready</div><div id="radarAsOf" class="radar-status"></div></div>
 </div>
 <div class="scan-controls card"><label>WATCHLIST SYMBOLS<input id="scanSymbols" value="FPT,PNJ,VCB,HPG,MWG,VHM,SSI,DGC"></label><button id="radarRefresh" class="radar-action primary">Refresh watchlist</button><span>Up to 8 symbols/request to respect Vnstock request limits.</span></div>
 <div class="watch-summary four">
   <article class="card watch-box red-box"><header><b>RED</b><span>pre-crash high risk</span></header><div id="redList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box yellow-box"><header><b>YELLOW</b><span>elevated watch</span></header><div id="yellowList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box green-box"><header><b>GREEN</b><span>no threshold met</span></header><div id="greenList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box gray-box"><header><b>ACTIVE DRAWDOWN</b><span>already down ≥15%</span></header><div id="activeDrawdown" class="watch-chips"><span class="radar-empty">—</span></div></article>
 </div>
 <article class="card radar-table-card"><div class="card-head"><div><small>CURRENT WATCHLIST</small><h3>Pre-crash ranking</h3></div><span class="radar-status">Final color requires both score and trend confirmation.</span></div><div class="table-scroll"><table class="radar-table"><thead><tr><th>Stock</th><th>Color</th><th>Score</th><th>Close / live</th><th>5D</th><th>Technical</th><th>Analog</th><th>News</th><th>Fundamental</th><th>Coverage</th><th>Why</th></tr></thead><tbody id="radarRows"><tr><td colspan="11">Refresh watchlist to run.</td></tr></tbody></table></div><div id="macroTape" class="macro-tape"></div></article>
 <section id="detailPanel" class="stock-detail" hidden>
   <article class="card panel"><div class="detail-head"><div><small>REQUEST RESULT</small><h3 id="detailTitle">—</h3><p id="detailMeta">—</p></div><div id="detailState"></div></div><div id="detailReasons" class="detail-reasons"></div><div id="detailSnapshot" class="detail-snapshot"></div><div id="stockHorizons" class="stock-horizons"></div><div id="detailModules" class="module-grid"></div><div id="detailAudit" class="source-audit"></div></article>
   <div class="detail-grid"><article class="card detail-chart"><div class="card-head"><div><small>PRICE + TECHNICAL EWS</small><h3>Risk path inside the requested window</h3></div></div><canvas id="stockDetailChart"></canvas></article><div class="side-stack"><article class="card sub-card"><small>FINANCIAL FRAGILITY</small><h4>Latest point-in-time data available</h4><div id="fundMetrics" class="fund-grid"></div></article><article class="card sub-card"><small>NEWS SENTIMENT</small><h4>Headlines inside the request window</h4><div id="stockNews" class="news-list"></div></article></div></div>
   <article class="card panel" style="margin-top:12px"><div class="card-head"><div><small>HISTORICAL CRASH REPLAY</small><h3>Technical signals before ≥12% 20-session drawdowns</h3></div><span class="radar-status">Point-in-time technical replay; no future data used in the pre-signal snapshots.</span></div><div id="crashReplay" class="replay-list"></div></article>
 </section>`;
 const monitor=document.getElementById('monitor');(monitor?.parentNode||document.querySelector('main')).insertBefore(sec,monitor||null);
 const dialog=document.createElement('dialog');dialog.id='radarInfoDialog';dialog.className='radar-dialog';dialog.innerHTML='<form method="dialog"><button>×</button></form><div class="eyebrow">INFORMATION</div><h3 id="radarInfoTitle">—</h3><p id="radarInfoBody"></p>';document.body.appendChild(dialog);
 const s=document.createElement('script');s.src='./stock-radar.js';document.head.appendChild(s);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
