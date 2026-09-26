(function(){'use strict';
const $=id=>document.getElementById(id);
const state={symbol:''};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1});
const pct=n=>Number.isFinite(n)?`${n>0?'+':''}${nf.format(n)}%`:'—';
const num=n=>Number.isFinite(n)?nf.format(n):'—';
const tone=n=>!Number.isFinite(n)?'neutral':n>0?'positive':n<0?'negative':'neutral';
const raw=()=>{try{return window.FinancialReportContext?.raw?.()||null;}catch{return null;}};
const market=()=>{try{return window.FinancialMarket?.context?.()||{};}catch{return{};}};
function periods(data){return[...new Set((data?.periods||data?.years||[]).map(String))].sort((a,b)=>{const f=x=>{const m=String(x).match(/^(\d{4})(?:-Q([1-4]))?$/);return m?Number(m[1])*4+(Number(m[2]||4)-1):-1};return f(a)-f(b);});}
function sections(data){return data?.sections||[];}
function rows(data){return sections(data).flatMap(s=>(s.rows||[]).map(r=>({...r,section:s.id,basis:s.basis||null})));}

const ALIASES={
 revenue:[/^doanh thu thuan$/,/^thu nhap lai thuan$/,/^tong thu nhap hoat dong$/,/doanh thu bao hiem thuan/],
 grossProfit:[/^loi nhuan gop$/],
 profit:[/lai lo thuan sau thue/,/loi nhuan sau thue/],
 parentProfit:[/loi nhuan cua co dong cua cong ty me/,/loi nhuan sau thue cua cd cong ty me/],
 assets:[/^tong cong tai san$/,/^tong tai san$/],
 currentAssets:[/^tai san ngan han$/],
 liabilities:[/^no phai tra$/,/^tong no phai tra$/],
 equity:[/^von chu so huu$/,/^tong von chu so huu$/],
 cash:[/^tien va tuong duong tien$/],
 receivables:[/^cac khoan phai thu$/,/^phai thu khach hang$/],
 inventory:[/^hang ton kho rong$/,/^hang ton kho$/],
 ocf:[/luu chuyen tien te rong tu cac hoat dong san xuat kinh doanh/,/luu chuyen tien thuan tu hoat dong kinh doanh/],
 capex:[/tien chi de mua sam xay dung tscd va cac tai san dai han khac/],
 grossMargin:[/ty suat loi nhuan gop bien/],
 netMargin:[/ty suat sinh loi tren doanh thu thuan/],
 roe:[/ty suat loi nhuan tren von chu so huu binh quan/],
 roa:[/ty suat sinh loi tren tong tai san binh quan/],
 quick:[/ty so thanh toan nhanh/],
 debtAssets:[/ty so no vay tren tong tai san/],
 liabilitiesAssets:[/ty so no tren tong tai san/],
 liabilitiesEquity:[/ty so no tren von chu so huu/],
 ocfRevenue:[/ty so dong tien hd.* tren doanh thu thuan/],
 ocfIncome:[/dong tien tu hd.* tren loi nhuan thuan/],
 revGrowth:[/tang truong\s+doanh thu thuan/],
 profitGrowth:[/tang truong loi nhuan sau thue cua cd cong ty me/,/tang truong loi nhuan truoc thue/]
};
function find(data,key){const patterns=ALIASES[key]||[];return rows(data).find(r=>patterns.some(p=>p.test(norm(r.label))));}
function val(row,period){const v=row?.values?.[period];const n=Number(v);return Number.isFinite(n)?n:null;}
function latest(data){return periods(data).at(-1)||null;}
function previousPeriod(data,p){const ps=periods(data),i=ps.indexOf(String(p));return i>0?ps[i-1]:null;}
function sameQuarterLastYear(data,p){const m=String(p||'').match(/^(\d{4})-Q([1-4])$/);if(!m)return null;const x=`${Number(m[1])-1}-Q${m[2]}`;return periods(data).includes(x)?x:null;}
function growth(a,b){return Number.isFinite(a)&&Number.isFinite(b)&&b!==0?(a/b-1)*100:null;}
function divide(a,b,m=1){return Number.isFinite(a)&&Number.isFinite(b)&&b!==0?a/b*m:null;}
function money(v){return Number.isFinite(v)?`${nf.format(v/1000)} tỷ`:'—';}
function point(v,unit){if(!Number.isFinite(v))return'—';if(unit==='%')return`${nf.format(v)}%`;if(/vnd/i.test(unit||''))return`${nf.format(v)} đ`;if(/lan|vong/i.test(norm(unit)))return`${nf.format(v)}x`;return money(v);}
function metric(data,key,p=latest(data)){const r=find(data,key);return{row:r,value:val(r,p),period:p,unit:r?.unit||''};}

function annualSnapshot(data){
 if(!data)return null;const p=latest(data),prev=previousPeriod(data,p);
 const get=k=>metric(data,k,p),old=k=>metric(data,k,prev).value;
 const revenue=get('revenue'),profit=get('profit'),gross=get('grossProfit'),assets=get('assets'),liab=get('liabilities'),equity=get('equity'),cash=get('cash'),recv=get('receivables'),inv=get('inventory'),ocf=get('ocf'),capex=get('capex');
 const fcf=Number.isFinite(ocf.value)&&Number.isFinite(capex.value)?ocf.value+capex.value:null;
 return{
  period:p,previous:prev,
  values:{revenue:revenue.value,profit:profit.value,gross:gross.value,assets:assets.value,liabilities:liab.value,equity:equity.value,cash:cash.value,receivables:recv.value,inventory:inv.value,ocf:ocf.value,capex:capex.value,fcf},
  change:{revenue:growth(revenue.value,old('revenue')),profit:growth(profit.value,old('profit')),assets:growth(assets.value,old('assets')),liabilities:growth(liab.value,old('liabilities')),equity:growth(equity.value,old('equity')),cash:growth(cash.value,old('cash')),receivables:growth(recv.value,old('receivables'))},
  ratios:{
   grossMargin:val(find(data,'grossMargin'),p)??divide(gross.value,revenue.value,100),
   netMargin:val(find(data,'netMargin'),p)??divide(profit.value,revenue.value,100),
   roe:val(find(data,'roe'),p)??divide(profit.value,equity.value,100),
   roa:val(find(data,'roa'),p)??divide(profit.value,assets.value,100),
   quick:val(find(data,'quick'),p),
   debtAssets:val(find(data,'debtAssets'),p),
   liabilitiesAssets:val(find(data,'liabilitiesAssets'),p)??divide(liab.value,assets.value,100),
   liabilitiesEquity:val(find(data,'liabilitiesEquity'),p)??divide(liab.value,equity.value,100),
   ocfRevenue:val(find(data,'ocfRevenue'),p)??divide(ocf.value,revenue.value,100),
   ocfIncome:val(find(data,'ocfIncome'),p)??divide(ocf.value,profit.value,100),
   receivablesRevenue:divide(recv.value,revenue.value,100),
   inventoryRevenue:divide(inv.value,revenue.value,100)
  }
 };
}
function quarterSnapshot(data){
 if(!data)return null;const p=latest(data),prev=previousPeriod(data,p),yoy=sameQuarterLastYear(data,p);
 const get=(k,x=p)=>val(find(data,k),x);
 return{
  period:p,previous:prev,yoy,
  revenue:get('revenue'),profit:get('profit'),ocf:get('ocf'),assets:get('assets'),liabilities:get('liabilities'),equity:get('equity'),cash:get('cash'),receivables:get('receivables'),
  qoq:{revenue:growth(get('revenue'),get('revenue',prev)),profit:growth(get('profit'),get('profit',prev)),ocf:growth(get('ocf'),get('ocf',prev)),assets:growth(get('assets'),get('assets',prev))},
  yoyChange:{revenue:growth(get('revenue'),get('revenue',yoy)),profit:growth(get('profit'),get('profit',yoy)),ocf:growth(get('ocf'),get('ocf',yoy)),assets:growth(get('assets'),get('assets',yoy))}
 };
}
function riskSignals(a,q){
 const s=[];if(!a)return s;
 const push=(level,title,value,detail)=>s.push({level,title,value,detail});
 if(Number.isFinite(a.ratios.ocfIncome))push(a.ratios.ocfIncome>=100?'good':a.ratios.ocfIncome>=75?'watch':'risk','Chất lượng lợi nhuận',`${nf.format(a.ratios.ocfIncome)}%`,a.ratios.ocfIncome>=100?'Dòng tiền HĐKD bao phủ lợi nhuận sau thuế.':'Dòng tiền HĐKD thấp hơn lợi nhuận kế toán.');
 if(Number.isFinite(a.values.fcf))push(a.values.fcf>=0?'good':'risk','Dòng tiền tự do',money(a.values.fcf),a.values.fcf>=0?'OCF đủ bù CAPEX trong kỳ.':'CAPEX vượt dòng tiền HĐKD.');
 if(Number.isFinite(a.ratios.liabilitiesAssets))push(a.ratios.liabilitiesAssets<55?'good':a.ratios.liabilitiesAssets<70?'watch':'risk','Đòn bẩy',`${nf.format(a.ratios.liabilitiesAssets)}% tài sản`,a.ratios.liabilitiesAssets<55?'Cơ cấu nợ/tài sản ở mức cân bằng.':'Tỷ trọng nợ trong tổng tài sản cần theo dõi.');
 if(Number.isFinite(a.change.receivables)&&Number.isFinite(a.change.revenue))push(a.change.receivables<=a.change.revenue+5?'good':'watch','Phải thu / doanh thu',`${pct(a.change.receivables)} vs ${pct(a.change.revenue)}`,a.change.receivables<=a.change.revenue+5?'Phải thu không tăng nhanh bất thường so với doanh thu.':'Phải thu tăng nhanh hơn doanh thu.');
 if(q&&Number.isFinite(q.ocf))push(q.ocf>=0?'good':'risk',`OCF ${q.period}`,money(q.ocf),q.ocf>=0?'Dòng tiền HĐKD quý dương.':'Dòng tiền HĐKD quý âm.');
 return s;
}
function scoreHealth(a,q){
 if(!a)return null;let score=50,parts=0;
 const add=(ok,good,bad)=>{if(!Number.isFinite(ok))return;score+=ok>=good?8:ok<=bad?-8:0;parts++;};
 add(a.change.revenue,10,0);add(a.change.profit,10,0);add(a.ratios.netMargin,10,5);add(a.ratios.roe,15,8);add(a.ratios.ocfIncome,100,60);
 if(Number.isFinite(a.ratios.liabilitiesAssets)){score+=a.ratios.liabilitiesAssets<=55?7:a.ratios.liabilitiesAssets>=75?-7:0;parts++;}
 if(Number.isFinite(a.values.fcf)){score+=a.values.fcf>=0?7:-7;parts++;}
 if(q&&Number.isFinite(q.yoyChange.profit)){score+=q.yoyChange.profit>5?6:q.yoyChange.profit<-5?-6:0;parts++;}
 return Math.max(0,Math.min(100,Math.round(score)));
}
function trendTag(n,positive=true){if(!Number.isFinite(n))return{label:'Chưa đủ dữ liệu',tone:'neutral'};const good=positive?n>0:n<0;return{label:good?'Tích cực':n===0?'Đi ngang':'Cần theo dõi',tone:good?'positive':n===0?'neutral':'negative'};}

function card(label,value,sub='',t='neutral'){return`<div class="analysis-kpi"><span>${esc(label)}</span><strong class="${esc(t)}">${esc(value)}</strong>${sub?`<small>${esc(sub)}</small>`:''}</div>`;}
function table(rows){return`<div class="analysis-table">${rows.map(r=>`<div class="analysis-table-row"><span>${esc(r[0])}</span><b>${esc(r[1])}</b><em class="${esc(r[3]||'neutral')}">${esc(r[2]||'')}</em></div>`).join('')}</div>`;}
function section(title,body){return`<section class="analysis-block"><h4>${esc(title)}</h4>${body}</section>`;}
function headlineList(items){if(!items?.length)return'';return section('Tin liên quan gần nhất',`<div class="analysis-news">${items.slice(0,5).map(n=>{const u=/^https?:\/\//.test(n.url||'')?n.url:'#';return`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`}).join('')}</div>`);}
function movementHTML(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q&&!d)return section('Biến động phiên','<div class="analysis-empty">Chưa có snapshot thị trường cho mã này.</div>');
 const kpis=[card('Giá',q?nf.format(q.price)+' đ':'—','Snapshot gần nhất'),card('Biến động',q?pct(q.changePct):'—','So với tham chiếu',tone(q?.changePct)),card('Điểm động lực',d?`${d.score>0?'+':''}${num(d.score)}/100`:'—',d?`Độ tin cậy ${num(d.confidenceScore)}/100`:'' ,tone(d?.score)),card('KL / TB20',d&&Number.isFinite(d.volumeRatio20)?num(d.volumeRatio20)+'x':'—','Mức hoạt động tương đối',d?.volumeRatio20>1?'positive':'neutral')].join('');
 const factors=(d?.factors||[]).map(f=>[f.label,`${f.contribution>0?'+':''}${num(f.contribution)}`,`w ${Math.round((f.weight||0)*100)}%`,tone(f.contribution)]);
 const details=d?table([
  ['Thị trường chung',pct(d.marketMedianChangePct),'Trung vị VN100',tone(d.marketMedianChangePct)],
  ['Sức mạnh tương đối',pct(d.relativeStrengthPct),'so với thị trường',tone(d.relativeStrengthPct)],
  ['Động lượng 5 phiên',pct(d.momentum5dPct),'xu hướng ngắn hạn',tone(d.momentum5dPct)],
  ['Biến động 20 phiên',Number.isFinite(d.volatility20dPct)?num(d.volatility20dPct)+'%':'—','độ lệch chuẩn','neutral'],
  ['Vị trí trong biên phiên',Number.isFinite(d.rangePositionPct)?num(d.rangePositionPct)+'%':'—','0% thấp · 100% cao','neutral']
 ]):'';
 return`<div class="analysis-kpis">${kpis}</div>${factors.length?section('Phân rã động lực',table(factors)):''}${section('Bối cảnh định lượng',details)}${headlineList(ctx.news)}`;
}
function financialHTML(a,q){
 if(!a)return section('Sức khỏe tài chính','<div class="analysis-empty">Chưa có dữ liệu BCTC năm.</div>');
 const score=scoreHealth(a,q),quality=trendTag(a.ratios.ocfIncome-80),growthTone=trendTag(a.change.profit),levTone=trendTag(60-a.ratios.liabilitiesAssets);
 const kpis=[
  card('Điểm sức khỏe',score!==null?score+'/100':'—',a.period,score>=70?'positive':score>=50?'neutral':'negative'),
  card('Doanh thu',money(a.values.revenue),pct(a.change.revenue),tone(a.change.revenue)),
  card('LN sau thuế',money(a.values.profit),pct(a.change.profit),tone(a.change.profit)),
  card('OCF',money(a.values.ocf),`OCF/LNST ${num(a.ratios.ocfIncome)}%`,a.ratios.ocfIncome>=100?'positive':a.ratios.ocfIncome>=75?'neutral':'negative')
 ].join('');
 const perf=table([
  ['Tăng trưởng doanh thu',pct(a.change.revenue),a.previous+' → '+a.period,tone(a.change.revenue)],
  ['Tăng trưởng LNST',pct(a.change.profit),a.previous+' → '+a.period,tone(a.change.profit)],
  ['Biên gộp',Number.isFinite(a.ratios.grossMargin)?num(a.ratios.grossMargin)+'%':'—','khả năng tạo giá trị gộp',quality.tone],
  ['Biên ròng',Number.isFinite(a.ratios.netMargin)?num(a.ratios.netMargin)+'%':'—','LNST / doanh thu',growthTone.tone],
  ['ROE',Number.isFinite(a.ratios.roe)?num(a.ratios.roe)+'%':'—','hiệu quả vốn chủ','positive'],
  ['ROA',Number.isFinite(a.ratios.roa)?num(a.ratios.roa)+'%':'—','hiệu quả tài sản','positive']
 ]);
 const cash=table([
  ['OCF',money(a.values.ocf),`${num(a.ratios.ocfIncome)}% LNST`,a.ratios.ocfIncome>=100?'positive':a.ratios.ocfIncome>=75?'neutral':'negative'],
  ['CAPEX',money(a.values.capex),'chi đầu tư tài sản','neutral'],
  ['FCF',money(a.values.fcf),'OCF + CAPEX',tone(a.values.fcf)],
  ['OCF / doanh thu',Number.isFinite(a.ratios.ocfRevenue)?num(a.ratios.ocfRevenue)+'%':'—','chuyển doanh thu thành tiền',a.ratios.ocfRevenue>=10?'positive':'neutral']
 ]);
 const balance=table([
  ['Tổng tài sản',money(a.values.assets),pct(a.change.assets),tone(a.change.assets)],
  ['Nợ phải trả',money(a.values.liabilities),`${num(a.ratios.liabilitiesAssets)}% tài sản`,levTone.tone],
  ['Vốn chủ sở hữu',money(a.values.equity),pct(a.change.equity),tone(a.change.equity)],
  ['Tiền & tương đương',money(a.values.cash),pct(a.change.cash),tone(a.change.cash)],
  ['Phải thu',money(a.values.receivables),`${num(a.ratios.receivablesRevenue)}% doanh thu`,a.change.receivables>a.change.revenue+5?'negative':'neutral'],
  ['Hàng tồn kho',money(a.values.inventory),`${num(a.ratios.inventoryRevenue)}% doanh thu`,'neutral']
 ]);
 let quarter='';if(q){quarter=table([
  ['Doanh thu '+q.period,money(q.revenue),`QoQ ${pct(q.qoq.revenue)} · YoY ${pct(q.yoyChange.revenue)}`,tone(q.yoyChange.revenue)],
  ['LNST '+q.period,money(q.profit),`QoQ ${pct(q.qoq.profit)} · YoY ${pct(q.yoyChange.profit)}`,tone(q.yoyChange.profit)],
  ['OCF '+q.period,money(q.ocf),`QoQ ${pct(q.qoq.ocf)} · YoY ${pct(q.yoyChange.ocf)}`,tone(q.ocf)],
  ['Tài sản '+q.period,money(q.assets),`QoQ ${pct(q.qoq.assets)} · YoY ${pct(q.yoyChange.assets)}`,tone(q.yoyChange.assets)]
 ]);}
 return`<div class="analysis-kpis">${kpis}</div>${section('Tăng trưởng & hiệu quả',perf)}${section('Chất lượng dòng tiền',cash)}${section('Cơ cấu tài chính',balance)}${q?section('Quý gần nhất',quarter):''}`;
}
function riskHTML(a,q){
 const signals=riskSignals(a,q);if(!signals.length)return section('Rủi ro định lượng','<div class="analysis-empty">Chưa đủ dữ liệu để tạo cảnh báo định lượng.</div>');
 return`<div class="analysis-risk-grid">${signals.map(s=>`<div class="analysis-risk ${esc(s.level)}"><span>${esc(s.title)}</span><strong>${esc(s.value)}</strong><p>${esc(s.detail)}</p></div>`).join('')}</div>`;
}
function comparisonHTML(a,q){
 const parts=[];if(a)parts.push(section(`Năm ${a.period} so với ${a.previous}`,table([
  ['Doanh thu',money(a.values.revenue),pct(a.change.revenue),tone(a.change.revenue)],
  ['LN sau thuế',money(a.values.profit),pct(a.change.profit),tone(a.change.profit)],
  ['Tổng tài sản',money(a.values.assets),pct(a.change.assets),tone(a.change.assets)],
  ['Vốn chủ sở hữu',money(a.values.equity),pct(a.change.equity),tone(a.change.equity)],
  ['Dòng tiền HĐKD',money(a.values.ocf),`${num(a.ratios.ocfIncome)}% LNST`,tone(a.ratios.ocfIncome-100)]
 ])));
 if(q)parts.push(section(`${q.period} · QoQ và cùng kỳ`,table([
  ['Doanh thu',money(q.revenue),`QoQ ${pct(q.qoq.revenue)} · YoY ${pct(q.yoyChange.revenue)}`,tone(q.yoyChange.revenue)],
  ['LN sau thuế',money(q.profit),`QoQ ${pct(q.qoq.profit)} · YoY ${pct(q.yoyChange.profit)}`,tone(q.yoyChange.profit)],
  ['Dòng tiền HĐKD',money(q.ocf),`QoQ ${pct(q.qoq.ocf)} · YoY ${pct(q.yoyChange.ocf)}`,tone(q.ocf)],
  ['Tổng tài sản',money(q.assets),`QoQ ${pct(q.qoq.assets)} · YoY ${pct(q.yoyChange.assets)}`,tone(q.yoyChange.assets)]
 ])));
 return parts.join('');
}
function searchHTML(question,annual,quarterly){
 const terms=norm(question).split(' ').filter(x=>x.length>2),datasets=[['Năm',annual],['Quý',quarterly]],hits=[];
 for(const [label,data] of datasets){if(!data)continue;for(const r of rows(data)){const n=norm(r.label),score=terms.reduce((a,t)=>a+(n.includes(t)?1:0),0);if(!score)continue;const ps=periods(data).slice(-5),vals=ps.filter(p=>Number.isFinite(val(r,p))).map(p=>`${p}: ${point(val(r,p),r.unit)}`);if(vals.length)hits.push({score,label,row:r,vals});}}
 hits.sort((a,b)=>b.score-a.score);if(!hits.length)return section('Kết quả','<div class="analysis-empty">Không tìm thấy chỉ tiêu phù hợp trong dữ liệu hiện có. Hãy hỏi theo nhóm: doanh thu, lợi nhuận, dòng tiền, nợ, tài sản, ROE, ROA, phải thu hoặc tồn kho.</div>');
 return section('Chỉ tiêu liên quan',`<div class="analysis-search-results">${hits.slice(0,12).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.label)}</span><p>${esc(h.vals.join(' · '))}</p></div>`).join('')}</div>`);
}
function classify(q){const s=norm(q);if(/vi sao|tang|giam|bien dong|phien|gia co phieu|dong luc/.test(s))return'movement';if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';if(/suc khoe|tai chinh|tong quan|doanh thu|loi nhuan|dong tien|no|roe|roa|bien loi nhuan/.test(s))return'financial';return'search';}
function analyze(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 const ctx={quote:m.quote||null,driver:m.driver||null,news:m.news||[]};
 const body=type==='movement'?movementHTML(ctx):type==='financial'?financialHTML(a,q):type==='risk'?riskHTML(a,q):type==='compare'?comparisonHTML(a,q):searchHTML(question,annual,quarterly);
 return{type,html:body||'<div class="analysis-empty">Chưa đủ dữ liệu để phân tích.</div>'};
}
function addUser(text){const box=$('research-ai-messages');if(!box)return;const a=document.createElement('article');a.className='research-ai-message user';a.innerHTML=`<strong>Câu hỏi</strong><p>${esc(text)}</p>`;box.append(a);}
function addAnalysis(result){const box=$('research-ai-messages');if(!box)return;const a=document.createElement('article');a.className='research-ai-message assistant analysis-result';a.innerHTML=result.html;box.append(a);box.scrollTop=box.scrollHeight;}
function ask(question){const q=String(question||'').trim();if(!q)return;addUser(q);addAnalysis(analyze(q));}
function sync(symbol){state.symbol=symbol||'';const title=$('research-ai-title');if(title)title.textContent=`Phân tích chuyên sâu · ${state.symbol||'VN100'}`;}
window.FinQueryAI={sync,ask,analyze};
const form=$('research-ai-form'),input=$('research-ai-question');form?.addEventListener('submit',e=>{e.preventDefault();const q=input.value.trim();if(q){input.value='';ask(q);}});document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.aiPrompt||'')));
sync(window.FinancialMarket?.context?.().symbol||new URLSearchParams(location.search).get('symbol')||'MBB');
})();