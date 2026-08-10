(()=>{
for(const href of ['./stock-radar.css','./stock-radar-v4.css','./qtrr-final.css']){
  if(!document.querySelector(`link[href="${href}"]`)){const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l)}
}
function mount(){
 if(document.getElementById('stock-radar'))return;
 const sec=document.createElement('section');sec.id='stock-radar';sec.className='section shell radar-shell qtrr-console';sec.innerHTML=`
 <div class="section-head qtrr-console-head"><div><div class="eyebrow">RISK MANAGER CONSOLE</div><h2>Detect → Explain → Validate → Act</h2><p>Start with the current risk radar. Investigate only the names that need attention, validate the warning on point-in-time history, then map it into a documented risk-control response.</p></div><div id="radarStatus" class="radar-status">Initializing…</div></div>

 <div class="qtrr-flow-strip">
  <a href="#detect"><b>01</b><span>DETECT</span><small>Market + watchlist</small></a>
  <a href="#analyze"><b>02</b><span>EXPLAIN</span><small>Drivers + evidence</small></a>
  <a href="#validate"><b>03</b><span>VALIDATE</span><small>Replay + holdout</small></a>
  <a href="#act"><b>04</b><span>ACT</span><small>Risk controls</small></a>
 </div>

 <section id="detect" class="qtrr-step">
  <div class="qtrr-step-head"><div><small>STEP 01 · DETECT</small><h3>What requires attention now?</h3></div><p>RED and YELLOW are pre-drawdown warning states. ACTIVE DRAWDOWN is separated because loss containment is operationally different from early warning.</p></div>
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
  <article class="card radar-table-card"><div class="card-head"><div><small>CURRENT RISK RANKING</small><h3>Escalation queue</h3></div><span class="radar-status">Risk score ≠ crash probability</span></div><div class="table-scroll"><table class="radar-table qtrr-table"><thead><tr><th>Security</th><th>Status</th><th>Risk</th><th>Close / live</th><th>5D move</th><th>Technical</th><th>Analog</th><th>Market</th><th>Module coverage</th><th>Escalation evidence</th></tr></thead><tbody id="radarRows"><tr><td colspan="10">Starting risk radar…</td></tr></tbody></table></div><div id="macroTape" class="macro-tape"></div></article>
 </section>

 <section id="analyze" class="qtrr-step qtrr-analysis">
  <div class="qtrr-step-head"><div><small>STEP 02 · EXPLAIN</small><h3>Investigate one security</h3></div><p>Use current data or freeze the model at a historical as-of date. Historical requests exclude current fundamentals when publication timing cannot be verified.</p></div>
  <div class="radar-toolbar qtrr-querybar"><div class="radar-query"><label>SYMBOL<input id="symbolInput" value="FPT" maxlength="8"></label><label>MODEL AS-OF<input id="asOfDate" type="date"></label><label>FROM<input id="fromDate" type="date"></label><label>TO<input id="toDate" type="date"></label><button id="runStockBtn" class="radar-action primary">Run risk analysis</button><button id="fptReplay" class="radar-action">FPT case</button><button id="pnjReplay" class="radar-action">PNJ case</button></div></div>
  <section id="detailPanel" class="stock-detail" hidden>
   <article class="card panel qtrr-risk-header"><div class="detail-head"><div><small>RISK ASSESSMENT</small><h3 id="detailTitle">—</h3><p id="detailMeta">—</p></div><div id="detailState"></div></div><div id="detailReasons" class="detail-reasons"></div><div id="detailSnapshot" class="detail-snapshot"></div></article>
   <article class="card panel qtrr-evidence-card"><div class="card-head"><div><small>WHY IS RISK ELEVATED?</small><h3>Independent evidence modules</h3></div><span class="radar-status">Unavailable modules are excluded, not imputed.</span></div><div id="detailModules" class="module-grid"></div></article>

   <section id="validate" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>STEP 03 · VALIDATE</small><h3>Forward-risk context and out-of-sample evidence</h3></div><p>Analog tail-event rates are matched-history frequencies. Predictive quality is tested separately with chronological holdout validation.</p></div>
    <div id="stockHorizons" class="stock-horizons qtrr-horizons"></div>
    <div class="qtrr-validation-grid"><article class="card detail-chart"><div class="card-head"><div><small>RISK PATH</small><h3>Price and technical warning history</h3></div></div><canvas id="stockDetailChart"></canvas></article><article class="card qtrr-validation-summary"><small>DESCRIPTIVE REPLAY</small><h3 id="validationHeadline">—</h3><div id="validationSummary"></div></article></div>
    <article class="card panel"><div class="card-head"><div><small>POINT-IN-TIME REPLAY</small><h3>Signals before historical ≥12% 20-session drawdowns</h3></div><span class="radar-status">T-20 / T-10 / T-5 / event start</span></div><div id="crashReplay" class="replay-list"></div></article>
    <article class="card panel"><div class="qtrr-validation-toolbar"><div><small>MODEL VALIDATION</small><h3>Chronological holdout test</h3><p>Calibrate the structural EWS threshold on the earlier sample, then measure Precision, Recall, F1, false-alarm rate and AUC only on the later holdout.</p></div><button id="runValidationBtn" class="radar-action primary">Run holdout validation</button></div><div id="holdoutValidation"><div class="radar-empty">Run after selecting a security.</div></div><div class="qtrr-model-risk-note"><b>Model-risk scope:</b> the holdout validates the structural technical + point-in-time analog engine. It deliberately does not claim a full historical six-module test because reliable dated news and fundamental vintages are not consistently available.</div></article>
   </section>

   <section id="act" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>STEP 04 · ACT</small><h3>Risk-control response</h3></div><p>The system proposes controls for review. It does not place trades and does not convert a risk score into an automatic sell decision.</p></div>
    <article id="riskActionPanel" class="card qtrr-action-panel"></article>
    <div class="qtrr-governance-matrix">
      <article class="qtrr-policy-card green"><small>GREEN</small><h4>Normal monitoring</h4><p>No escalation threshold currently met.</p><ul><li>Maintain approved limits</li><li>Normal daily monitoring</li><li>Reassess after material deterioration</li></ul></article>
      <article class="qtrr-policy-card yellow"><small>YELLOW</small><h4>Enhanced watch</h4><p>Deterioration detected; evidence not yet sufficient for RED.</p><ul><li>Daily review</li><li>Check concentration and liquidity</li><li>Define RED escalation trigger</li></ul></article>
      <article class="qtrr-policy-card red"><small>RED</small><h4>Formal escalation</h4><p>Multi-factor deterioration requires exposure review.</p><ul><li>No passive risk increase</li><li>-10% / -15% stress review</li><li>Assign owner and review date</li></ul></article>
      <article class="qtrr-policy-card gray"><small>ACTIVE DRAWDOWN</small><h4>Loss containment</h4><p>Already in deep drawdown; no longer an early-warning state.</p><ul><li>Review remaining loss capacity</li><li>Liquidity / exit-capacity assessment</li><li>Escalate limit breaches</li></ul></article>
    </div>
   </section>

   <section id="governance" class="qtrr-inner-step">
    <div class="qtrr-step-head"><div><small>GOVERNANCE</small><h3>Data, assumptions and audit trail</h3></div><p>Verify what the model actually saw, which modules were unavailable, and whether the selected as-of date prevents look-ahead.</p></div>
    <div class="detail-grid"><article class="card sub-card"><small>FINANCIAL FRAGILITY</small><h4>Available fundamentals</h4><div id="fundMetrics" class="fund-grid"></div></article><article class="card sub-card"><small>NEWS SENTIMENT</small><h4>Evidence in request window</h4><div id="stockNews" class="news-list"></div></article></div><article class="card panel"><div id="detailAudit" class="source-audit"></div></article>
   </section>
  </section>
 </section>`;
 const host=document.getElementById('radarMount')||document.querySelector('main');host.appendChild(sec);
 const dialog=document.createElement('dialog');dialog.id='radarInfoDialog';dialog.className='radar-dialog';dialog.innerHTML='<form method="dialog"><button>×</button></form><div class="eyebrow">MODEL EVIDENCE</div><h3 id="radarInfoTitle">—</h3><p id="radarInfoBody"></p>';document.body.appendChild(dialog);
 const s=document.createElement('script');s.src='./qtrr-final.js';s.defer=true;document.head.appendChild(s);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();