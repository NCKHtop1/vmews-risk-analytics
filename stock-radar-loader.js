(()=>{
const css=document.createElement('link');css.rel='stylesheet';css.href='./stock-radar.css';document.head.appendChild(css);
const css2=document.createElement('link');css2.rel='stylesheet';css2.href='./stock-radar-v4.css';document.head.appendChild(css2);
function mount(){
 if(document.getElementById('stock-radar'))return;
 const sec=document.createElement('section');sec.id='stock-radar';sec.className='section shell radar-shell qtrr-console';sec.innerHTML=`
 <div class="section-head qtrr-console-head"><div><div class="eyebrow">RISK MANAGER CONSOLE</div><h2>Detect → Explain → Validate → Act</h2><p>Start with the current risk radar. Select a security only when it requires investigation, then move from evidence to forward-risk context, historical validation and risk-control actions.</p></div><div id="radarStatus" class="radar-status">Initializing…</div></div>

 <div class="qtrr-flow-strip">
  <a href="#detect"><b>01</b><span>DETECT</span><small>Market + watchlist</small></a>
  <a href="#analyze"><b>02</b><span>EXPLAIN</span><small>Drivers + evidence</small></a>
  <a href="#validate"><b>03</b><span>VALIDATE</span><small>5/20/60D + replay</small></a>
  <a href="#act"><b>04</b><span>ACT</span><small>Risk controls</small></a>
 </div>

 <section id="detect" class="qtrr-step">
  <div class="qtrr-step-head"><div><small>STEP 01 · DETECT</small><h3>What requires attention now?</h3></div><p>RED and YELLOW are pre-drawdown warning states. ACTIVE DRAWDOWN is deliberately separated because loss containment is different from early warning.</p></div>
  <div class="qtrr-market-grid">
   <article class="card qtrr-market-card"><small>VNINDEX RISK REGIME</small><div class="qtrr-market-score"><strong id="marketRiskScore">—</strong><span>/100</span></div><h3 id="marketRiskState">LOADING</h3><p id="marketRiskDetail">Requesting point-in-time market regime…</p><div id="marketRiskMeta" class="qtrr-market-meta"></div></article>
   <article class="card qtrr-priority-card"><small>RISK PRIORITY</small><h3 id="priorityHeadline">Waiting for watchlist</h3><p id="priorityText">The radar will surface the highest-risk names first.</p><div id="priorityCounts" class="qtrr-counts"></div></article>
  </div>
  <div class="scan-controls card"><label>MONITORED NAMES<input id="scanSymbols" value="FPT,PNJ,VCB,HPG,MWG,VHM,SSI,DGC"></label><button id="radarRefresh" class="radar-action primary">Refresh risk radar</button><span id="radarAsOf">Up to 8 names/request · Vnstock request protection</span></div>
  <div class="watch-summary four">
   <article class="card watch-box red-box"><header><b>RED · ESCALATE</b><span>high pre-drawdown risk</span></header><div id="redList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box yellow-box"><header><b>YELLOW · WATCH</b><span>deterioration detected</span></header><div id="yellowList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box green-box"><header><b>GREEN · NORMAL</b><span>no escalation threshold</span></header><div id="greenList" class="watch-chips"><span class="radar-empty">—</span></div></article>
   <article class="card watch-box gray-box"><header><b>ACTIVE DRAWDOWN</b><span>loss containment mode</span></header><div id="activeDrawdown" class="watch-chips"><span class="radar-empty">—</span></div></article>
  </div>
  <article class="card radar-table-card"><div class="card-head"><div><small>CURRENT RISK RANKING</small><h3>Escalation queue</h3></div><span class="radar-status">Risk score ≠ crash probability</span></div><div class="table-scroll"><table class="radar-table qtrr-table"><thead><tr><th>Security</th><th>Status</th><th>Risk</th><th>Close / live</th><th>5D move</th><th>Technical</th><th>Analog</th><th>Market</th><th>Module coverage</th><th>Escalation evidence</th></tr></thead><tbody id="radarRows"><tr><td colspan="10">Running risk radar…</td></tr></tbody></table></div><div id="macroTape" class="macro-tape"></div></article>
 </section>

 <section id="analyze" class="qtrr-step qtrr-analysis">
  <div class="qtrr-step-head"><div><small>STEP 02 · EXPLAIN</small><h3>Investigate one security</h3></div><p>Use current data or freeze the model at a historical as-of date. Historical requests exclude current fundamentals when publication timing cannot be verified.</p></div>
  <div class="radar-toolbar qtrr-querybar"><div class="radar-query"><label>SYMBOL<input id="symbolInput" value="FPT" maxlength="8"></label><label>MODEL AS-OF<input id="asOfDate" type="date"></label><label>FROM<input id="fromDate" type="date"></label><label>TO<input id="toDate" type="date"></label><button id="runStockBtn" class="radar-action primary">Run risk analysis</button><button id="fptReplay" class="radar-action">FPT case</button><button id="pnjReplay" class="radar-action">PNJ case</button></div></div>
  <section id="detailPanel" class="stock-detail" hidden>
   <article class="card panel qtrr-risk-header"><div class="detail-head"><div><small>RISK ASSESSMENT</small><h3 id="detailTitle">—</h3><p id="detailMeta">—</p></div><div id="detailState"></div></div><div id="detailReasons" class="detail-reasons"></div><div id="detailSnapshot" class="detail-snapshot"></div></article>
   <article class="card panel qtrr-evidence-card"><div class="card-head"><div><small>WHY IS RISK ELEVATED?</small><h3>Independent evidence modules</h3></div><span class="radar-status">Unavailable modules are excluded, not imputed.</span></div><div id="detailModules" class="module-grid"></div></article>

   <section id="validate" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>STEP 03 · VALIDATE</small><h3>Forward-risk context and historical evidence</h3></div><p>Analog tail-event rates summarize matched past states. They are empirical historical frequencies, not calibrated probabilities.</p></div>
    <div id="stockHorizons" class="stock-horizons qtrr-horizons"></div>
    <div class="qtrr-validation-grid"><article class="card detail-chart"><div class="card-head"><div><small>RISK PATH</small><h3>Price and technical warning history</h3></div></div><canvas id="stockDetailChart"></canvas></article><article class="card qtrr-validation-summary"><small>VALIDATION SUMMARY</small><h3 id="validationHeadline">—</h3><div id="validationSummary"></div></article></div>
    <article class="card panel"><div class="card-head"><div><small>POINT-IN-TIME REPLAY</small><h3>Signals before historical ≥12% 20-session drawdowns</h3></div><span class="radar-status">T-20 / T-10 / T-5 / event start</span></div><div id="crashReplay" class="replay-list"></div></article>
   </section>

   <section id="act" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>STEP 04 · ACT</small><h3>Risk-control response</h3></div><p>The system proposes controls for review. It does not place trades and does not convert a risk score into an automatic sell decision.</p></div>
    <article id="riskActionPanel" class="card qtrr-action-panel"></article>
   </section>

   <section id="governance" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>GOVERNANCE</small><h3>Data, assumptions and audit trail</h3></div><p>Use this section to verify what the model actually saw before relying on a warning.</p></div>
    <div class="detail-grid"><article class="card sub-card"><small>FINANCIAL FRAGILITY</small><h4>Available fundamentals</h4><div id="fundMetrics" class="fund-grid"></div></article><article class="card sub-card"><small>NEWS SENTIMENT</small><h4>Evidence in request window</h4><div id="stockNews" class="news-list"></div></article></div><article class="card panel"><div id="detailAudit" class="source-audit"></div></article>
   </section>
  </section>
 </section>`;
 const mount=document.getElementById('radarMount')||document.querySelector('main');mount.appendChild(sec);
 const dialog=document.createElement('dialog');dialog.id='radarInfoDialog';dialog.className='radar-dialog';dialog.innerHTML='<form method="dialog"><button>×</button></form><div class="eyebrow">MODEL EVIDENCE</div><h3 id="radarInfoTitle">—</h3><p id="radarInfoBody"></p>';document.body.appendChild(dialog);
 const s=document.createElement('script');s.src='./stock-radar.js';document.head.appendChild(s);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
