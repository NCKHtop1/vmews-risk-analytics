(()=>{
'use strict';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
function corporateGuard(rows,threshold=.10){
  const out=(rows||[]).map(r=>({...r})),sus=[];if(!out.length)return{rows:out,suspects:sus};
  let model=+out[0].close;out[0].close=model;
  for(let i=1;i<out.length;i++){
    const raw=+rows[i].close,prev=+rows[i-1].close,lr=raw>0&&prev>0?Math.log(raw/prev):0,bad=Math.abs(lr)>threshold;
    if(bad)sus.push({date:rows[i].date,logReturn:lr,rawClose:raw,reason:'one-day discontinuity above HOSE research guard'});
    model=model*Math.exp(bad?0:lr);out[i].close=model;
  }
  return{rows:out,suspects:sus};
}
function hash(s,n=256){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return(h>>>0)%n}
function terms(text){const t=String(text||'').toLowerCase().match(/[\p{L}\p{N}]+/gu)||[],z=[...t];for(let i=0;i<t.length-1;i++)z.push(t[i]+'_'+t[i+1]);return z}
function vec(text,n=256){const x=new Float64Array(n);for(const t of terms(text))x[hash(t,n)]+=1;let norm=0;for(const v of x)norm+=v*v;norm=Math.sqrt(norm)||1;for(let i=0;i<n;i++)x[i]/=norm;return x}
const SEEDS=[
 ['company reports record profit and strong revenue growth',0],['earnings beat expectations and margin improves',0],['wins major contract and raises guidance',0],['debt declines and cash flow improves',0],['credit quality improves and provisions decline',0],['lợi nhuận tăng mạnh doanh thu tăng trưởng tích cực',0],['lợi nhuận kỷ lục vượt kế hoạch',0],['trúng thầu hợp đồng lớn mở rộng hoạt động',0],['dòng tiền cải thiện nợ vay giảm',0],['biên lợi nhuận cải thiện kết quả kinh doanh tích cực',0],
 ['company reports heavy loss and weak revenue',1],['regulatory investigation and fraud allegations',1],['earnings miss and margin pressure intensifies',1],['default risk rises and debt burden worsens',1],['downgrade after sharp profit decline',1],['lỗ ròng doanh thu giảm mạnh',1],['bị điều tra vi phạm và xử phạt',1],['nợ xấu tăng mạnh chất lượng tài sản suy giảm',1],['lợi nhuận sụt giảm biên lợi nhuận thu hẹp',1],['cảnh báo rủi ro thanh khoản và áp lực nợ vay',1]
];
function trainNLP(extra=[]){
  const data=SEEDS.map(([t,y])=>[vec(t),y]);
  const strongNeg=['khởi tố','điều tra','xử phạt','vi phạm','thua lỗ','lỗ ròng','nợ xấu tăng','fraud','investigation','penalty','default','downgrade'];
  const strongPos=['lợi nhuận kỷ lục','vượt kế hoạch','trúng thầu','lợi nhuận tăng','record profit','beats expectations','wins contract','upgrade'];
  for(const h of extra){const low=String(h.title||'').toLowerCase();let y=null;if(strongNeg.some(w=>low.includes(w)))y=1;else if(strongPos.some(w=>low.includes(w)))y=0;if(y!=null)data.push([vec(low),y])}
  const w=new Float64Array(257),sig=z=>1/(1+Math.exp(-Math.max(-20,Math.min(20,z))));
  for(let ep=0;ep<90;ep++)for(const[x,y]of data){let z=w[256];for(let j=0;j<256;j++)z+=w[j]*x[j];const e=sig(z)-y,lr=.16/(1+ep*.015);for(let j=0;j<256;j++)w[j]-=lr*(e*x[j]+.001*w[j]);w[256]-=lr*e}
  return text=>{const x=vec(text);let z=w[256];for(let j=0;j<256;j++)z+=w[j]*x[j];return sig(z)};
}
function enhanceNews(news){
  const items=(news?.items||[]).map(x=>({...x})),predict=trainNLP(items);let num=0,den=0;
  for(const x of items){const p=predict(x.title),age=Number.isFinite(+x.ageDays)?+x.ageDays:10,decay=Math.exp(-age/21),base=Number.isFinite(+x.risk)?clamp(+x.risk/Math.max(decay,.05)):0.5;x.nlpRisk=p;x.lexicalEventRisk=base;x.risk=(.70*p+.30*base)*decay;num+=x.risk;den+=decay}
  return{...news,items:items.sort((a,b)=>b.risk-a.risk),score:items.length?100*clamp(num/(den||1)):null,nlpModel:'hashed unigram/bigram logistic regression; labeled financial seed set + high-confidence distant supervision'};
}
function patch(){
  const R=window.VMEWSResearch;if(!R||R.__qualityPatched)return false;const base=R.run.bind(R);
  R.run=async(detail,onProgress)=>{
    const g=corporateGuard(detail.history||[],.10),copy={...detail,history:g.rows};
    const out=await base(copy,onProgress);out.news=enhanceNews(out.news);out.data=out.data||{};out.data.corporateActionSuspects=g.suspects;
    const m=detail.modules||{},ctx=[];
    if(m.market?.available!==false&&Number.isFinite(+m.market?.score))ctx.push([+m.market.score/100,.30]);
    if(m.macro?.available!==false&&Number.isFinite(+m.macro?.score))ctx.push([+m.macro.score/100,.20]);
    if(out.news.score!=null)ctx.push([out.news.score/100,.25]);
    if(m.fundamental?.available!==false&&Number.isFinite(+m.fundamental?.score))ctx.push([+m.fundamental.score/100,.25]);
    const wt=ctx.reduce((a,b)=>a+b[1],0);out.context=ctx.length?ctx.reduce((a,b)=>a+b[0]*b[1],0)/wt:null;out.currentRisk=out.context==null?out.current.ensemble:.8*out.current.ensemble+.2*out.context;out.quality={corporateActionThreshold:0.10,nlpModel:out.news.nlpModel};return out;
  };
  R.__qualityPatched=true;return true;
}
if(!patch())window.addEventListener('DOMContentLoaded',()=>{let n=0;const t=setInterval(()=>{if(patch()||++n>80)clearInterval(t)},50)});
})();
