(function(){'use strict';
const $=id=>document.getElementById(id);
const DOLPHIN_VERSION='DOLPHIN_V4';
const AI_MODE_KEY='finquery_dolphin_mode';
const state={symbol:'',history:[],busy:false,directKey:'',model:'',modelCandidates:[],mode:'normal',lastQuestion:'',currentController:null};
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
function trendTag(n,positive=true){if(!Number.isFinite(n))return{label:'Không có số liệu',tone:'neutral'};const good=positive?n>0:n<0;return{label:good?'Tích cực':n===0?'Đi ngang':'Cần theo dõi',tone:good?'positive':n===0?'neutral':'negative'};}

function card(label,value,sub='',t='neutral'){return`<div class="analysis-kpi"><span>${esc(label)}</span><strong class="${esc(t)}">${esc(value)}</strong>${sub?`<small>${esc(sub)}</small>`:''}</div>`;}
function table(rows){return`<div class="analysis-table">${rows.map(r=>`<div class="analysis-table-row"><span>${esc(r[0])}</span><b>${esc(r[1])}</b><em class="${esc(r[3]||'neutral')}">${esc(r[2]||'')}</em></div>`).join('')}</div>`;}
function section(title,body){return`<section class="analysis-block"><h4>${esc(title)}</h4>${body}</section>`;}
function prose(items){const parts=(items||[]).filter(Boolean);return parts.length?'<div class="analysis-narrative">'+parts.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>':'';}
function relationText(value,positive='tăng',negative='giảm'){if(!Number.isFinite(value))return'không có số liệu so sánh';if(Math.abs(value)<.15)return'gần như đi ngang';return value>0?positive+' '+num(Math.abs(value))+'%':negative+' '+num(Math.abs(value))+'%';}
function movementNarrative(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q)return[];
 const ch=Number(q.changePct),delta=Number.isFinite(q.price)&&Number.isFinite(q.reference)?q.price-q.reference:null,dir=ch>0?'tăng':ch<0?'giảm':'đi ngang',rel=Number(d?.relativeStrengthPct),vol=Number(d?.volumeRatio20),mom=Number(d?.momentum5dPct),top=(d?.factors||[]).slice(0,2),headline=(ctx.news||[])[0],out=[];
 let first=state.symbol+' đang '+dir+' '+num(Math.abs(ch||0))+'% so với giá tham chiếu '+(Number.isFinite(q.reference)?nf.format(q.reference)+' đồng':'—')+'.';
 if(Number.isFinite(delta))first+=' Mức thay đổi tuyệt đối là '+(delta>0?'+':'')+nf.format(delta)+' đồng, từ '+nf.format(q.reference)+' lên '+nf.format(q.price)+' đồng.';
 if(Number.isFinite(rel))first+=' So với trung vị VN100, '+state.symbol+' '+(rel>=0?'mạnh hơn':'yếu hơn')+' '+num(Math.abs(rel))+' điểm %.';
 out.push(first);
 if(d){let second='Động lượng 5 phiên '+relationText(mom)+'. Thanh khoản đạt '+num(vol)+' lần bình quân 20 phiên.';if(top.length)second+=' Hai lực nổi bật nhất trong mô hình là '+top.map(x=>x.label.toLowerCase()+' ('+(x.contribution>0?'+':'')+num(x.contribution)+')').join(' và ')+'.';second+=' Vì vậy nhịp '+dir+' hiện được đọc chủ yếu từ '+(top[0]?.label?.toLowerCase()||'trạng thái giá và thị trường')+'.';out.push(second);}
 if(ctx.technical?.snapshot)out.push(ctx.technical.snapshot.title+'. '+ctx.technical.snapshot.detail);
 if(headline){const qt=Date.parse(q.sourceTime||q.collectedAt||''),nt=Date.parse(headline.publishedAt||''),hours=Number.isFinite(qt)&&Number.isFinite(nt)?(qt-nt)/3600000:null;let timing='';if(Number.isFinite(hours))timing=hours>=0?' Tin được công bố khoảng '+num(Math.abs(hours))+' giờ trước snapshot, nên nằm trong bộ thông tin thị trường đã biết ở thời điểm giá hiện tại.':' Tin xuất hiện sau snapshot khoảng '+num(Math.abs(hours))+' giờ, vì vậy nó thuộc bối cảnh cho phiên kế tiếp chứ không giải thích phần biến động đã xảy ra trước đó.';out.push('Tin gần nhất gắn với '+state.symbol+' là “'+headline.title+'” từ '+(headline.source||'nguồn báo chí')+'.'+timing+(headline.summary?' Nội dung RSS tóm tắt: '+headline.summary:''));}
 return out;
}
function financialNarrative(a,q){
 if(!a)return[];
 const out=['Ở kỳ năm '+a.period+', doanh thu '+relationText(a.change.revenue)+' và lợi nhuận sau thuế '+relationText(a.change.profit)+' so với '+a.previous+'. Biên ròng ở mức '+num(a.ratios.netMargin)+'%, ROE '+num(a.ratios.roe)+'% và ROA '+num(a.ratios.roa)+'%.'];
 if(Number.isFinite(a.ratios.ocfIncome))out.push('Dòng tiền HĐKD đạt '+money(a.values.ocf)+', tương đương '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế; FCF ước tính '+money(a.values.fcf)+' sau CAPEX. Nợ phải trả chiếm khoảng '+num(a.ratios.liabilitiesAssets)+'% tổng tài sản.');
 if(q)out.push('Ở '+q.period+', doanh thu '+relationText(q.qoq.revenue)+' QoQ và '+relationText(q.yoyChange.revenue)+' YoY; lợi nhuận sau thuế '+relationText(q.qoq.profit)+' QoQ và '+relationText(q.yoyChange.profit)+' YoY. Nên đọc đồng thời với dòng tiền quý để đánh giá chất lượng tăng trưởng.');
 return out;
}
function riskNarrative(a,q){
 if(!a)return[];
 const signals=riskSignals(a,q),risks=signals.filter(x=>x.level==='risk'),watch=signals.filter(x=>x.level==='watch');
 if(risks.length)return['Điểm cần chú ý nhất hiện nằm ở '+risks.map(x=>x.title.toLowerCase()).join(', ')+'. Các cảnh báo này xuất phát trực tiếp từ dòng tiền, đòn bẩy hoặc biến động vốn lưu động trong dữ liệu hiện có.'];
 if(watch.length)return['Các chỉ tiêu rủi ro chính đang ở vùng kiểm soát; nhóm cần theo dõi sát nhất là '+watch.map(x=>x.title.toLowerCase()).join(', ')+'.'];
 return['Các thước đo rủi ro cốt lõi đang ở trạng thái ổn định trong bộ dữ liệu hiện tại. Trọng tâm chuyển sang tốc độ tăng trưởng, chất lượng dòng tiền và khả năng duy trì biên lợi nhuận.'];
}
function compareNarrative(a,q){
 const out=[];if(a)out.push('So với '+a.previous+', năm '+a.period+' ghi nhận doanh thu '+relationText(a.change.revenue)+' và lợi nhuận sau thuế '+relationText(a.change.profit)+'; tổng tài sản '+relationText(a.change.assets)+' và vốn chủ sở hữu '+relationText(a.change.equity)+'.');
 if(q)out.push('Quý '+q.period+' cho thấy doanh thu '+relationText(q.qoq.revenue)+' so với quý trước và '+relationText(q.yoyChange.revenue)+' so với cùng kỳ; lợi nhuận '+relationText(q.qoq.profit)+' QoQ và '+relationText(q.yoyChange.profit)+' YoY.');
 return out;
}
const K=window.FinQueryKnowledge||{find(){return null;},explainLabel(){return'Đây là chỉ tiêu có trong dữ liệu FinQuery.';}};
function technicalMetric(concept,m){const t=m?.technical,i=t?.indicators||{};if(!concept||!t)return null;const map={rsi:'rsi',macd:'macd',bollinger:'middle',atr:'atr',adx:'adx',stochastic:'stoch',supertrend:'supertrend',obv:'obv',mfi:'mfi',cmf:'cmf',sma:'sma',ema:'ema'};const key=map[concept.id];return key&&Number.isFinite(i[key])?{value:i[key],period:t.timeframe,key}:null;}
function currentConceptValue(concept,a,q,annual,m){if(!concept)return null;if(concept.metric&&a){if(Object.prototype.hasOwnProperty.call(a.ratios,concept.metric)&&Number.isFinite(a.ratios[concept.metric]))return{value:a.ratios[concept.metric],period:a.period,unit:'%'};if(Object.prototype.hasOwnProperty.call(a.values,concept.metric)&&Number.isFinite(a.values[concept.metric]))return{value:a.values[concept.metric],period:a.period,unit:'money'};}if(concept.id==='reference'&&Number.isFinite(m?.quote?.reference))return{value:m.quote.reference,period:'phiên hiện tại',unit:'VND'};return technicalMetric(concept,m);}
function dynamicMetricHit(question,annual,quarterly){const terms=norm(question).split(' ').filter(x=>x.length>2&&!['nghia','khai','niem','cong','thuc','the','nao','bao','nhieu','tot','xau'].includes(x)),hits=[];for(const [scope,data]of[['Năm',annual],['Quý',quarterly]]){if(!data)continue;for(const row of rows(data)){const n=norm(row.label),score=terms.reduce((s,t)=>s+(n.includes(t)?1:0),0);if(score)hits.push({score,scope,row,data});}}hits.sort((a,b)=>b.score-a.score);return hits[0]||null;}
function conceptDiagnosis(concept,a,q){
 if(!concept||!a)return[];
 const out=[];
 if(concept.id==='roa'){
  const profit=a.change.profit,assets=a.change.assets,margin=a.ratios.netMargin;
  if(Number.isFinite(profit)&&Number.isFinite(assets))out.push('ROA đang chịu tác động trực tiếp từ tốc độ lợi nhuận so với tốc độ mở rộng tài sản: lợi nhuận '+relationText(profit)+', trong khi tổng tài sản '+relationText(assets)+'. '+(profit>assets?'Lợi nhuận đang tăng nhanh hơn tài sản nên hiệu quả sử dụng tài sản được hỗ trợ.':'Tài sản đang tăng nhanh hơn lợi nhuận nên ROA bị pha loãng.'));
  if(Number.isFinite(margin))out.push('Biên ròng hiện ở '+num(margin)+'%; nếu biên ròng giảm thì ROA thường giảm ngay cả khi doanh thu vẫn tăng.');
 }
 if(concept.id==='roe'){
  const profit=a.change.profit,equity=a.change.equity,lev=a.ratios.liabilitiesEquity;
  if(Number.isFinite(profit)&&Number.isFinite(equity))out.push('ROE phụ thuộc vào lợi nhuận tạo ra trên vốn chủ: lợi nhuận '+relationText(profit)+', còn vốn chủ '+relationText(equity)+'. '+(profit>equity?'Lợi nhuận tăng nhanh hơn vốn chủ nên ROE được hỗ trợ.':'Vốn chủ tăng nhanh hơn lợi nhuận nên ROE bị kéo xuống.'));
  if(Number.isFinite(lev))out.push('Nợ/vốn chủ ở '+num(lev)+'; ROE cao đi cùng đòn bẩy tăng cần tách phần cải thiện do hoạt động khỏi phần do dùng nợ nhiều hơn.');
 }
 if(concept.id==='ocf'||concept.id==='fcf'){
  if(Number.isFinite(a.ratios.ocfIncome))out.push('OCF hiện bằng '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế. '+(a.ratios.ocfIncome>=100?'Tiền từ hoạt động đang bao phủ toàn bộ lợi nhuận kế toán.':'Tiền từ hoạt động đang thấp hơn lợi nhuận kế toán, nên phải thu, tồn kho và các khoản phải trả là các điểm cần đọc tiếp.'));
  if(Number.isFinite(a.values.fcf))out.push('FCF ước tính '+money(a.values.fcf)+'. '+(a.values.fcf>=0?'Sau CAPEX doanh nghiệp vẫn còn dòng tiền tự do dương.':'CAPEX đang lớn hơn lượng tiền hoạt động tạo ra trong kỳ.'));
 }
 if(concept.id==='receivables'&&Number.isFinite(a.change.receivables)&&Number.isFinite(a.change.revenue))out.push('Phải thu '+relationText(a.change.receivables)+', còn doanh thu '+relationText(a.change.revenue)+'. '+(a.change.receivables>a.change.revenue+5?'Tiền bị giữ ở khách hàng đang tăng nhanh hơn tốc độ bán hàng.':'Phải thu đang tăng cùng nhịp hoặc chậm hơn doanh thu, nên vốn bị giữ ở khách hàng chưa tạo áp lực lớn lên tăng trưởng hiện tại.'));
 if(concept.id==='inventory'&&Number.isFinite(a.ratios.inventoryRevenue))out.push('Tồn kho tương đương '+num(a.ratios.inventoryRevenue)+'% doanh thu năm hiện tại; cần đọc xu hướng nhiều kỳ để phân biệt tích trữ phục vụ tăng trưởng với tồn kho chậm luân chuyển.');
 if(q&&concept.metric&&Number.isFinite(q.yoyChange?.profit))out.push('Quý '+q.period+' có lợi nhuận '+relationText(q.yoyChange.profit)+' so với cùng kỳ, cung cấp tín hiệu gần hơn về hướng thay đổi của hiệu quả sinh lời.');
 return out;
}
function conceptHTML(question,a,q,annual,quarterly,m){
 const ranked=K.search?.(question,4)||[],concept=K.find?.(question)||ranked[0]?.c||null,dyn=!concept?dynamicMetricHit(question,annual,quarterly):null;if(!concept&&!dyn)return'';
 if(dyn){const p=latest(dyn.data),prev=previousPeriod(dyn.data,p),v=val(dyn.row,p),old=val(dyn.row,prev),g=growth(v,old),definition=K.explainLabel?.(dyn.row.label)||'Đây là chỉ tiêu có trong dữ liệu FinQuery.';return prose([dyn.row.label+': '+definition+' Với '+state.symbol+', kỳ '+p+' ghi nhận '+point(v,dyn.row.unit)+(Number.isFinite(g)?', '+relationText(g)+' so với '+prev:'')+'.'])+section('Dữ liệu đang có',table([[dyn.row.label,point(v,dyn.row.unit),prev?('so với '+prev+' '+pct(g)):'',tone(g)]]));}
 const current=currentConceptValue(concept,a,q,annual,m),paragraphs=[concept.definition,concept.formula?'Công thức: '+concept.formula+'.':'',concept.read||'',...conceptDiagnosis(concept,a,q)];
 if(current){let value=current.unit==='%'?num(current.value)+'%':current.unit==='money'?money(current.value):current.unit==='VND'?nf.format(current.value)+' đồng':num(current.value);let sentence='Với '+state.symbol+', '+concept.title+' tại '+current.period+' đang ở mức '+value+'.';if(concept.metric&&annual&&a?.previous){const old=val(find(annual,concept.metric),a.previous);if(Number.isFinite(old)){const diff=current.value-old;sentence+=' So với '+a.previous+', chỉ tiêu '+(diff>=0?'tăng ':'giảm ')+num(Math.abs(diff))+' điểm.';}}paragraphs.push(sentence);}
 if(m?.technical&&['rsi','macd','bollinger','atr','adx','stochastic','supertrend','obv','mfi','cmf','sma','ema','meanReversion','volume','cci','roc','willr','vwap'].includes(concept.id)&&m.technical.snapshot)paragraphs.push(m.technical.snapshot.title+'. '+m.technical.snapshot.detail);
 if(ranked.length>1)paragraphs.push('Các khái niệm gần câu hỏi nhất trong hệ thống: '+ranked.slice(1,4).map(x=>x.c.title).join(', ')+'.');
 return prose(paragraphs.filter(Boolean));
}
function headlineList(items){if(!items?.length)return'';return section('Tin liên quan gần nhất',`<div class="analysis-news">${items.slice(0,5).map(n=>{const u=/^https?:\/\//.test(n.url||'')?n.url:'#';return`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`}).join('')}</div>`);}
function movementHTML(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q&&!d)return section('Biến động phiên','<div class="analysis-empty">Snapshot thị trường của mã này không hiện diện trong bộ dữ liệu đang tải.</div>');
 const kpis=[card('Giá',q?nf.format(q.price)+' đ':'—','Snapshot gần nhất'),card('Biến động',q?pct(q.changePct):'—','So với tham chiếu',tone(q?.changePct)),card('Điểm động lực',d?`${d.score>0?'+':''}${num(d.score)}/100`:'—',d?`Độ tin cậy ${num(d.confidenceScore)}/100`:'' ,tone(d?.score)),card('KL / TB20',d&&Number.isFinite(d.volumeRatio20)?num(d.volumeRatio20)+'x':'—','Mức hoạt động tương đối',d?.volumeRatio20>1?'positive':'neutral')].join('');
 const factors=(d?.factors||[]).map(f=>[f.label,`${f.contribution>0?'+':''}${num(f.contribution)}`,`w ${Math.round((f.weight||0)*100)}%`,tone(f.contribution)]);
 const details=d?table([
  ['Thị trường chung',pct(d.marketMedianChangePct),'Trung vị VN100',tone(d.marketMedianChangePct)],
  ['Sức mạnh tương đối',pct(d.relativeStrengthPct),'so với thị trường',tone(d.relativeStrengthPct)],
  ['Động lượng 5 phiên',pct(d.momentum5dPct),'xu hướng ngắn hạn',tone(d.momentum5dPct)],
  ['Biến động 20 phiên',Number.isFinite(d.volatility20dPct)?num(d.volatility20dPct)+'%':'—','độ lệch chuẩn','neutral'],
  ['Vị trí trong biên phiên',Number.isFinite(d.rangePositionPct)?num(d.rangePositionPct)+'%':'—','0% thấp · 100% cao','neutral']
 ]):'';
 return`${prose(movementNarrative(ctx))}<div class="analysis-kpis">${kpis}</div>${factors.length?section('Phân rã động lực',table(factors)):''}${section('Bối cảnh định lượng',details)}${headlineList(ctx.news)}`;
}
function financialHTML(a,q){
 if(!a)return section('Sức khỏe tài chính','<div class="analysis-empty">Bộ dữ liệu đang tải không có BCTC năm để tính nhóm chỉ tiêu này.</div>');
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
 return`${prose(financialNarrative(a,q))}<div class="analysis-kpis">${kpis}</div>${section('Tăng trưởng & hiệu quả',perf)}${section('Chất lượng dòng tiền',cash)}${section('Cơ cấu tài chính',balance)}${q?section('Quý gần nhất',quarter):''}`;
}
function riskHTML(a,q){
 const signals=riskSignals(a,q);if(!signals.length)return section('Rủi ro định lượng','<div class="analysis-empty">Các trường dữ liệu cần thiết cho mô hình rủi ro này không hiện diện trong kỳ đang chọn.</div>');
 return`${prose(riskNarrative(a,q))}<div class="analysis-risk-grid">${signals.map(s=>`<div class="analysis-risk ${esc(s.level)}"><span>${esc(s.title)}</span><strong>${esc(s.value)}</strong><p>${esc(s.detail)}</p></div>`).join('')}</div>`;
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
 return prose(compareNarrative(a,q))+parts.join('');
}
function localMetricSearch(question,annual,quarterly){
 const terms=norm(question).split(' ').filter(x=>x.length>2&&!['bao','nhieu','hien','tai','the','nao','giai','thich','phan','tich','danh','gia'].includes(x)),datasets=[['Năm',annual],['Quý',quarterly]],hits=[];
 for(const [scope,data]of datasets){if(!data)continue;for(const row of rows(data)){const label=norm(row.label),score=terms.reduce((s,t)=>s+(label.includes(t)?2:0),0);if(!score)continue;const ps=periods(data).slice(-8),values=ps.filter(p=>Number.isFinite(val(row,p))).map(p=>({period:p,value:val(row,p)}));if(values.length)hits.push({score,scope,row,data,values});}}
 return hits.sort((a,b)=>b.score-a.score);
}
function newsSearch(question,items){
 const stop=new Set(['tai','sao','vi','sao','giam','tang','the','nao','hien','nay','phan','tich','danh','gia','cho','toi','ve','cua','anh','huong']);
 const terms=norm(question).split(' ').filter(x=>x.length>2&&!stop.has(x));
 return(items||[]).map(n=>{const hay=norm((n.title||'')+' '+(n.summary||'')+' '+(n.topics||[]).join(' ')),score=terms.reduce((s,t)=>s+(hay.includes(t)?2:0),0)+(n.symbols||[]).includes(state.symbol)?2:0;return{...n,score};}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||Date.parse(b.publishedAt)-Date.parse(a.publishedAt)).slice(0,8);
}
function searchHTML(question,annual,quarterly,m){
 const concept=K.find?.(question);if(concept)return conceptHTML(question,annualSnapshot(annual),quarterSnapshot(quarterly),annual,quarterly,m);
 const hits=localMetricSearch(question,annual,quarterly),newsHits=newsSearch(question,[...(m.news||[]),...(m.marketNews||[])]);
 const paragraphs=[];
 if(hits.length){const h=hits[0],last=h.values.at(-1),prev=h.values.at(-2),g=prev?growth(last.value,prev.value):null;paragraphs.push(h.row.label+' của '+state.symbol+' ở '+last.period+' là '+point(last.value,h.row.unit)+(Number.isFinite(g)?', '+relationText(g)+' so với '+prev.period:'')+'. '+(K.explainLabel?.(h.row.label)||''));}
 if(newsHits.length){const n=newsHits[0];paragraphs.push('Tin phù hợp nhất với câu hỏi là “'+n.title+'” từ '+(n.source||'nguồn báo chí')+' công bố '+String(n.publishedAt||'').slice(0,16).replace('T',' ')+'.'+(n.summary?' Nội dung tóm tắt: '+n.summary:''));}
 if(m.technical?.snapshot)paragraphs.push('Trạng thái kỹ thuật hiện tại: '+m.technical.snapshot.title+'. '+m.technical.snapshot.detail);
 if(paragraphs.length){let details='';if(hits.length)details+=section('Chuỗi dữ liệu liên quan',`<div class="analysis-search-results">${hits.slice(0,8).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.scope)}</span><p>${esc(h.values.map(x=>x.period+': '+point(x.value,h.row.unit)).join(' · '))}</p></div>`).join('')}</div>`);if(newsHits.length)details+=headlineList(newsHits);return prose(paragraphs)+details;}
 const nearest=K.search?.(question,4)||[];
 if(nearest.length){const first=nearest[0].c;return prose([first.definition,first.formula?'Công thức: '+first.formula+'.':'',first.read||'','Câu hỏi được ghép với nhóm khái niệm gần nhất trong kho FinQuery: '+nearest.map(x=>x.c.title).join(', ')+'.'].filter(Boolean));}
 const tech=m.technical?.snapshot?m.technical.snapshot.title+'. '+m.technical.snapshot.detail:'',marketText=m.quote?state.symbol+' đang '+(m.quote.changePct>=0?'tăng ':'giảm ')+num(Math.abs(m.quote.changePct))+'% so với tham chiếu '+(Number.isFinite(m.quote.reference)?nf.format(m.quote.reference)+' đồng':'hiện tại')+'.':'';
 return prose([marketText,tech,'Câu hỏi được xử lý theo dữ liệu thực của mã đang xem: giá, chỉ báo kỹ thuật, BCTC và tin liên quan đang có trong FinQuery.'].filter(Boolean));
}
function macroDatasetFor(question,macro){if(!macro?.datasets)return null;const s=norm(question),id=/\bpmi\b/.test(s)?'pmi':/\bfdi\b/.test(s)?'fdi':/gdp/.test(s)?'gdp_growth':/cung tien|m2|money supply/.test(s)?'money_supply':/tin dung|credit/.test(s)?'credit_sector':'macro_overview';return macro.datasets[id]?{id,...macro.datasets[id]}:null;}
function macroNews(question,items){return newsSearch(question,items).slice(0,5);}
function macroHTML(question,m){
 const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro),matched=macroNews(question,m.marketNews||[]),paragraphs=[];
 if(ds){const rs=ds.rows||[],last=rs.at(-1),prev=rs.at(-2),numeric=ds.numericColumns||[],tokens=norm(question).split(' '),chosen=numeric.find(k=>tokens.some(t=>t.length>2&&norm(k).includes(t)))||numeric[0];if(last&&chosen&&typeof last[chosen]==='number'){let sentence='Dữ liệu VBMA gần nhất ghi nhận '+chosen+' ở '+num(last[chosen])+'.';if(prev&&typeof prev[chosen]==='number'&&prev[chosen]!==0){const change=(last[chosen]/prev[chosen]-1)*100;sentence+=' So với mốc liền trước, '+chosen+' '+relationText(change)+'.';}paragraphs.push(sentence);}}
 if(matched.length){const first=matched[0],second=matched[1],qt=Date.parse(m.quote?.sourceTime||m.quote?.collectedAt||''),nt=Date.parse(first.publishedAt||''),timing=Number.isFinite(qt)&&Number.isFinite(nt)?(qt-nt)/3600000:null;let sentence='Tin gần nhất liên quan tới câu hỏi là “'+first.title+'” từ '+(first.source||'nguồn báo chí')+'.';if(Number.isFinite(timing))sentence+=timing>=0?' Tin xuất hiện trước snapshot khoảng '+num(Math.abs(timing))+' giờ, nên đã nằm trong bối cảnh thông tin thị trường ở thời điểm giá hiện tại.':' Tin xuất hiện sau snapshot khoảng '+num(Math.abs(timing))+' giờ, nên phù hợp hơn để theo dõi phản ứng ở phiên kế tiếp.';if(first.summary)sentence+=' Nội dung RSS: '+first.summary;paragraphs.push(sentence);if(second)paragraphs.push('Bối cảnh thứ hai là “'+second.title+'”. Khi đọc các sự kiện NHNN, OMO, lãi suất ON hay tín dụng, Dolphin AI sắp xếp theo thứ tự trạng thái thanh khoản trước sự kiện → hành động điều tiết → phản ứng lãi suất và thị trường sau sự kiện để xác định cơ chế đang chi phối.');}
 else paragraphs.push('Với câu hỏi vĩ mô này, Dolphin AI đọc dữ liệu VBMA đang mở trước, sau đó ghép với chuỗi tin thị trường theo thời điểm. Trọng tâm là diễn biến trước và sau sự kiện: thanh khoản, lãi suất, tín dụng và phản ứng của thị trường.');
 let sources='';if(matched.length)sources=headlineList(matched);
 return prose(paragraphs)+sources;
}
function evidenceFacts(a,q,m){
 const facts=[];if(m.quote){facts.push(['Giá',nf.format(m.quote.price)+' đ','Tham chiếu '+(Number.isFinite(m.quote.reference)?nf.format(m.quote.reference)+' đ':'—'),tone(m.quote.changePct)]);facts.push(['Biến động phiên',pct(m.quote.changePct),Number.isFinite(m.quote.reference)?'Từ '+nf.format(m.quote.reference)+' đ':'',tone(m.quote.changePct)]);}
 if(a){facts.push(['Doanh thu '+a.period,money(a.values.revenue),pct(a.change.revenue),tone(a.change.revenue)]);facts.push(['LNST '+a.period,money(a.values.profit),pct(a.change.profit),tone(a.change.profit)]);facts.push(['ROE / ROA',num(a.ratios.roe)+'% / '+num(a.ratios.roa)+'%','Hiệu quả vốn và tài sản','neutral']);facts.push(['OCF / LNST',num(a.ratios.ocfIncome)+'%',money(a.values.ocf),tone(a.ratios.ocfIncome-100)]);}
 if(q){facts.push(['Quý '+q.period,money(q.revenue),'DT YoY '+pct(q.yoyChange.revenue),tone(q.yoyChange.revenue)]);facts.push(['LNST quý',money(q.profit),'YoY '+pct(q.yoyChange.profit),tone(q.yoyChange.profit)]);}
 return facts;
}
function supportCase(a,q,m){
 const items=[];if(a?.change.revenue>0)items.push('Doanh thu năm '+a.period+' tăng '+num(a.change.revenue)+'%.');if(a?.change.profit>0)items.push('Lợi nhuận sau thuế tăng '+num(a.change.profit)+'%.');if(a?.ratios.ocfIncome>=100)items.push('OCF bao phủ '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế, chất lượng tiền mặt tốt.');if(q?.yoyChange.profit>0)items.push('Lợi nhuận quý '+q.period+' tăng '+num(q.yoyChange.profit)+'% so với cùng kỳ.');if(m.technical?.snapshot?.tone==='positive')items.push(m.technical.snapshot.title+': '+m.technical.snapshot.detail);if(m.driver?.relativeStrengthPct>0)items.push(state.symbol+' mạnh hơn trung vị VN100 '+num(m.driver.relativeStrengthPct)+' điểm %.');return items.slice(0,6);
}
function counterCase(a,q,m){
 const items=[];if(a?.change.profit<0)items.push('Lợi nhuận sau thuế giảm '+num(Math.abs(a.change.profit))+'%.');if(Number.isFinite(a?.ratios.ocfIncome)&&a.ratios.ocfIncome<75)items.push('OCF chỉ bằng '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế, tiền mặt đi sau lợi nhuận kế toán.');if(Number.isFinite(a?.ratios.liabilitiesAssets)&&a.ratios.liabilitiesAssets>=70)items.push('Nợ phải trả chiếm '+num(a.ratios.liabilitiesAssets)+'% tổng tài sản.');if(Number.isFinite(a?.change.receivables)&&Number.isFinite(a?.change.revenue)&&a.change.receivables>a.change.revenue+5)items.push('Phải thu tăng '+num(a.change.receivables)+'%, nhanh hơn doanh thu '+num(a.change.revenue)+'%.');if(q?.yoyChange.profit<0)items.push('Lợi nhuận quý '+q.period+' giảm '+num(Math.abs(q.yoyChange.profit))+'% YoY.');if(m.technical?.snapshot?.tone==='negative')items.push(m.technical.snapshot.title+': '+m.technical.snapshot.detail);if(m.driver?.relativeStrengthPct<0)items.push(state.symbol+' yếu hơn trung vị VN100 '+num(Math.abs(m.driver.relativeStrengthPct))+' điểm %.');return items.slice(0,6);
}
function memoHTML(question,a,q,m){
 const facts=evidenceFacts(a,q,m),support=supportCase(a,q,m),counter=counterCase(a,q,m),newsHits=newsSearch(question,[...(m.news||[]),...(m.marketNews||[])]).slice(0,4),headline=[];
 if(m.quote)headline.push(state.symbol+' đang '+(m.quote.changePct>=0?'tăng ':'giảm ')+num(Math.abs(m.quote.changePct))+'% so với tham chiếu '+nf.format(m.quote.reference)+' đồng.');
 if(a)headline.push('Năm '+a.period+', doanh thu '+relationText(a.change.revenue)+' và lợi nhuận '+relationText(a.change.profit)+'. OCF/LNST ở '+num(a.ratios.ocfIncome)+'%.');
 if(m.technical?.snapshot)headline.push(m.technical.snapshot.title+'. '+m.technical.snapshot.detail);
 const supportHTML=support.length?'<div class="research-case positive-case">'+support.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>':'',counterHTML=counter.length?'<div class="research-case negative-case">'+counter.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>':'';
 const watch=[];if(Number.isFinite(m.quote?.reference))watch.push('Giữ/đánh mất vùng tham chiếu '+nf.format(m.quote.reference)+' đồng.');if(m.technical?.indicators?.rsi<50)watch.push('RSI vượt 50 để xác nhận động lượng hồi phục rõ hơn.');else if(Number.isFinite(m.technical?.indicators?.rsi))watch.push('RSI hiện '+num(m.technical.indicators.rsi)+', theo dõi khả năng duy trì trên vùng cân bằng.');if(Number.isFinite(m.technical?.volumeRatio20))watch.push('Khối lượng hiện '+num(m.technical.volumeRatio20)+'x TB20.');if(q?.period)watch.push('Kỳ công bố tiếp theo sau '+q.period+' để kiểm tra hướng doanh thu, lợi nhuận và OCF.');
 return`${prose(headline)}${facts.length?section('Dữ kiện chính',table(facts)):''}${supportHTML?section('Luận điểm hỗ trợ',supportHTML):''}${counterHTML?section('Điểm làm yếu luận điểm',counterHTML):''}${newsHits.length?headlineList(newsHits):''}${watch.length?section('Mốc cần theo dõi','<div class="research-case watch-case">'+watch.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>'):''}`;
}
function classify(q){const s=norm(q),concept=K.find?.(q),asksDefinition=/la gi|nghia la gi|khai niem|cong thuc|cach tinh|do cai gi|the hien gi/.test(s),stockMove=/gia co phieu|co phieu|ma nay|phien hom nay|phien nay|dong luc phien|vi sao ma|vi sao co phieu/.test(s);if(/nhnn|ngan hang nha nuoc|lai suat|overnight|\bon\b|omo|thanh khoan|ty gia|lam phat|\bgdp\b|\bpmi\b|\bfdi\b|cung tien|m2|tin dung|vi mo/.test(s))return'macro';if(concept&&asksDefinition)return'concept';if(stockMove||((/vi sao|nguyen nhan|tang|giam|bien dong/.test(s))&&!concept))return'movement';if(concept)return'concept';if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';if(/phan tich chuyen sau|phan tich toan dien|tong hop|ho so nghien cuu|danh gia tong the|tinh hinh/.test(s))return'memo';if(/suc khoe|tai chinh|tong quan|doanh thu|loi nhuan|dong tien|no|roe|roa|bien loi nhuan|fcf|ocf|phai thu|ton kho/.test(s))return'financial';if(asksDefinition)return'concept';return'search';}
function analyze(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 const ctx={quote:m.quote||null,driver:m.driver||null,technical:m.technical||null,news:m.news||[],marketNews:m.marketNews||[]};
 const body=type==='macro'?macroHTML(question,m):type==='movement'?movementHTML(ctx):type==='concept'?conceptHTML(question,a,q,annual,quarterly,m):type==='financial'?financialHTML(a,q):type==='risk'?riskHTML(a,q):type==='compare'?comparisonHTML(a,q):type==='memo'?memoHTML(question,a,q,m):searchHTML(question,annual,quarterly,m);
 return{type,html:body||'<div class="analysis-empty">Câu hỏi này được neo vào các trường dữ liệu thực đang có; không có giá trị tương ứng để tính thêm trong kỳ hiện tại.</div>'};
}

const GOOGLE_AI_ORIGIN='https://generativelanguage.googleapis.com/v1beta';
const GEMINI_SESSION_KEY='vmews_solution_ai_browser_session';
const GOOGLE_SEARCH_TOOL={type:'google_search'};
const URL_CONTEXT_TOOL={type:'url_context'};
const STOP_WORDS=new Set(['bao','nhieu','hien','tai','the','nao','giai','thich','phan','tich','danh','gia','cho','toi','cua','nay','ma','co','phieu','doanh','nghiep','ky','gan','nhat']);
function restoreAIMode(){try{state.mode=localStorage.getItem(AI_MODE_KEY)==='deep'?'deep':'normal';}catch{state.mode='normal';}}
function modeLabel(mode=state.mode){return mode==='deep'?'Phân tích sâu':'Nhanh & tiết kiệm';}
function setAIMode(mode,persist=true){
 state.mode=mode==='deep'?'deep':'normal';
 if(persist)try{localStorage.setItem(AI_MODE_KEY,state.mode);}catch{}
 state.model=pickModel(state.mode,state.modelCandidates)||state.model;
 document.querySelectorAll('[data-dolphin-mode]').forEach(b=>b.classList.toggle('active',b.dataset.dolphinMode===state.mode));
 renderGeminiStatus();
}
function modelVersionScore(name){const m=String(name||'').match(/gemini-(\d+)(?:\.(\d+))?/i);return m?Number(m[1])*100+Number(m[2]||0):0;}
function pickModel(mode,models,exclude=[]){
 const blocked=new Set(exclude),pool=(models||[]).filter(x=>!blocked.has(x));if(!pool.length)return'';
 const lite=pool.filter(x=>/flash[-_.]?lite/i.test(x)).sort((a,b)=>modelVersionScore(b)-modelVersionScore(a));
 const full=pool.filter(x=>/flash/i.test(x)&&!/flash[-_.]?lite/i.test(x)).sort((a,b)=>modelVersionScore(b)-modelVersionScore(a));
 return mode==='deep'?(full[0]||lite[0]||''):(lite[0]||full[0]||'');
}
function modelPlan(mode=state.mode){
 const first=pickModel(mode,state.modelCandidates),plan=first?[first]:[];
 if(mode==='deep'){const lite=pickModel('normal',state.modelCandidates,plan);if(lite)plan.push(lite);}
 return plan;
}

function sessionSecret(){
 if(state.directKey)return state.directKey;
 try{return sessionStorage.getItem(GEMINI_SESSION_KEY)?.trim()||'';}catch{return'';}
}
function rememberSession(secret){
 state.directKey=String(secret||'').trim();
 try{sessionStorage.setItem(GEMINI_SESSION_KEY,state.directKey);}catch{}
}
function forgetSession(){
 state.directKey='';state.model='';state.modelCandidates=[];
 try{sessionStorage.removeItem(GEMINI_SESSION_KEY);}catch{}
}
function providerMessage(status,details=''){
 if(status===401||status===403)return'Khóa Google không hợp lệ, đã bị thu hồi hoặc chưa có quyền sử dụng Gemini.';
 if(status===429)return'Gemini đã hết hạn mức tạm thời. Dolphin chuyển sang FinQuery cục bộ.';
 if(status===404)return'Mô hình Gemini chưa khả dụng với dự án Google hiện tại.';
 if(status>=500)return'Google Gemini đang tạm thời gián đoạn.';
 return details||('Kết nối Gemini chưa sẵn sàng ('+status+').');
}
function availableModels(payload){
 return (payload?.models||[]).filter(item=>{
  const name=String(item.name||'').replace(/^models\//,'');
  const supported=item.supportedGenerationMethods||item.supportedActions||[];
  return name.startsWith('gemini-')&&/flash/i.test(name)&&!/image|audio|tts|live|embedding|robotics/i.test(name)&&(supported.length===0||supported.includes('generateContent')||supported.includes('generate_content'));
 }).map(item=>String(item.name||'').replace(/^models\//,''));
}
async function validateGemini(secret){
 const response=await fetch(GOOGLE_AI_ORIGIN+'/models?pageSize=100',{method:'GET',mode:'cors',cache:'no-store',headers:{'x-goog-api-key':secret}});
 const payload=await response.json().catch(()=>({}));
 if(!response.ok)throw new Error(providerMessage(response.status,payload?.error?.message));
 state.modelCandidates=availableModels(payload);
 const model=pickModel(state.mode,state.modelCandidates);
 if(!model)throw new Error('Dự án Google chưa có mô hình Gemini Flash khả dụng.');
 state.model=model;
 return model;
}
function compactRows(data,question,limit=18){
 if(!data)return[];
 const ps=periods(data).slice(-8),terms=norm(question).split(' ').filter(x=>x.length>2&&!STOP_WORDS.has(x)),chosen=new Map();
 const add=(row,score)=>{if(!row)return;const key=String(row.section||'')+'|'+String(row.label||'');const prior=chosen.get(key);if(!prior||score>prior.score)chosen.set(key,{row,score});};
 for(const row of rows(data)){const label=norm(row.label),score=terms.reduce((s,t)=>s+(label.includes(t)?3:0),0);if(score)add(row,score);}
 for(const key of ['revenue','profit','assets','liabilities','equity','cash','ocf','capex','roe','roa','grossMargin','netMargin','quick','liabilitiesAssets','liabilitiesEquity','revGrowth','profitGrowth'])add(find(data,key),2);
 return[...chosen.values()].sort((a,b)=>b.score-a.score).slice(0,limit).map(({row})=>({
  label:row.label,unit:row.unit||'',section:row.section||'',basis:row.basis||null,
  values:Object.fromEntries(ps.filter(p=>Number.isFinite(val(row,p))).map(p=>[p,val(row,p)]))
 }));
}
function compactMacro(question){
 try{
  const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro);if(!ds)return null;
  return{name:ds.name||ds.title||null,numericColumns:ds.numericColumns||[],rows:(ds.rows||[]).slice(-6)};
 }catch{return null;}
}
function cleanNews(items,limit=8){
 const seen=new Set(),out=[];
 for(const item of items||[]){const url=String(item?.url||'');if(!/^https?:\/\//i.test(url)||seen.has(url))continue;seen.add(url);out.push({title:String(item.title||'').slice(0,240),url,source:String(item.source||item.publisher||'').slice(0,100),publishedAt:String(item.publishedAt||item.date||'').slice(0,40),summary:String(item.summary||'').slice(0,500),topics:Array.isArray(item.topics)?item.topics.slice(0,8):[]});if(out.length>=limit)break;}
 return out;
}
function buildLLMContext(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null;
 const a=annualSnapshot(annual),q=quarterSnapshot(quarterly),companyNews=cleanNews(m.news||[],8),macro=compactMacro(question);
 return{
  scope:'financial-report',contextVersion:DOLPHIN_VERSION,symbol:state.symbol||m.symbol||'',mode:new URLSearchParams(location.search).get('mode')||null,
  generatedAt:new Date().toISOString(),
  dataPolicy:{financialNumbers:'FINQUERY_VERIFIED_ONLY',calculations:'LOCAL_ENGINE_ONLY',llmRole:'interpret_compare_explain',missingData:'STATE_MISSING_DO_NOT_INVENT'},
  marketSnapshot:m.quote||null,movementDrivers:m.driver||null,marketContext:m.market||null,technical:m.technical||null,
  localFinancialData:{annualSummary:a,quarterSummary:q,annualRows:compactRows(annual,question,18),quarterRows:compactRows(quarterly,question,18)},
  macroSnapshot:macro,recentNews:companyNews,sectorNews:cleanNews(m.sectorNews||m.marketNews||[],6)
 };
}
function sourcesForLLM(){
 const m=market(),company=cleanNews(m.news||[],6).map(x=>({...x,category:'COMPANY'})),sector=cleanNews(m.sectorNews||m.marketNews||[],6).map(x=>({...x,category:'SECTOR'}));
 return [...company,...sector].slice(0,10).map(x=>({title:x.title,url:x.url,publisher:x.source,publishedAt:x.publishedAt,category:x.category}));
}
function dolphinSystemInstruction(){
 return[
  'Bạn là Dolphin AI của FinQuery, trợ lý nghiên cứu tài chính doanh nghiệp Việt Nam.',
  'Luôn trả lời bằng tiếng Việt tự nhiên, trực tiếp, tránh văn phong chung chung kiểu AI.',
  'Dữ liệu trong context.localFinancialData, marketSnapshot, movementDrivers và technical là dữ liệu neo. Không tự tạo, thay đổi hoặc ước đoán số liệu nếu dữ liệu neo không có.',
  'Không tự tính lại ROA, ROE, biên lợi nhuận, tăng trưởng hoặc các tỷ số khi FinQuery đã cung cấp giá trị. Nếu thiếu chỉ tiêu như NIM, CIR, LDR thì nói rõ chưa có trong dữ liệu hiện tại.',
  'Luôn phân biệt số năm và số quý; gắn nhận định với kỳ cụ thể. Không annualize nếu context không cung cấp quy tắc.',
  'Nếu câu hỏi là follow-up ngắn, dùng lịch sử gần nhất và symbol hiện tại để hiểu mã này, quý này, chỉ số đó.',
  'Tin và Google Search chỉ là lớp bằng chứng bổ sung. Không dùng nguồn web để ghi đè số BCTC hoặc giá đã neo trong FinQuery.',
  'Phân biệt recentNews là tin doanh nghiệp đã lọc chặt với sectorNews là bối cảnh ngành. Không được gọi sectorNews là tin của doanh nghiệp.',
  'Nếu hỏi nguyên nhân biến động giá, tách rõ dữ kiện quan sát được khỏi nguyên nhân có bằng chứng. Không khẳng định quan hệ nhân quả chỉ từ tương quan.',
  'Nếu dữ liệu không đủ, nêu đúng dữ liệu nào đang thiếu và vẫn trả lời phần có thể kiểm chứng.',
  'Không đưa ra khuyến nghị mua/bán hoặc cam kết lợi nhuận. Có thể phân tích kịch bản, rủi ro, điều kiện xác nhận và điểm cần theo dõi.',
  'Trả lời theo cấu trúc phù hợp với câu hỏi; không ép mọi câu trả lời vào cùng một mẫu.'
 ].join('\n');
}
function shouldSearchWeb(question){
 const s=norm(question);
 return /hom nay|phien nay|moi nhat|tin|nhnn|ngan hang nha nuoc|lai suat|vi mo|ty gia|lam phat|gdp|pmi|fdi|tai sao gia|vi sao gia|bien dong|su kien|chinh sach/.test(s);
}
function inferredQuestionMode(question){
 const s=norm(question);
 return /phan tich chuyen sau|phan tich toan dien|ho so nghien cuu|vi sao .*phien|dong luc phien|doi chieu nguon|nguyen nhan bien dong/.test(s)?'deep':null;
}
function geminiPrompt(question){
 return[
  'CÂU HỎI NGƯỜI DÙNG:\n'+question,
  'LỊCH SỬ GẦN NHẤT:\n'+JSON.stringify(state.history.slice(-8)),
  'FINQUERY CONTEXT:\n'+JSON.stringify(buildLLMContext(question)),
  'NGUỒN ĐÃ CÓ TRONG TRANG:\n'+JSON.stringify(sourcesForLLM()),
  'Hãy trả lời câu hỏi dựa trên dữ liệu neo trước. Nếu có tìm kiếm web, chỉ dùng để bổ sung bằng chứng và nêu thời điểm khi cần.'
 ].join('\n\n');
}
function safeExternalUrl(url){
 try{const u=new URL(String(url||''));return /^https?:$/.test(u.protocol)?u.href:'';}catch{return'';}
}
function providerAnswer(payload){
 const sources=[],known=new Set(),queries=[];let searched=false,readUrls=false;const paragraphs=[];
 const add=(url,title)=>{const safe=safeExternalUrl(url);if(!safe||known.has(safe))return;known.add(safe);sources.push({url:safe,title:String(title||new URL(safe).hostname).slice(0,160)});};
 for(const step of payload?.steps||[]){
  if(step.type==='google_search_call'||step.type==='google_search_result')searched=true;
  if(step.type==='url_context_call'||step.type==='url_context_result')readUrls=true;
  if(typeof step.query==='string'&&step.query.trim())queries.push(step.query.trim());
  for(const query of step.queries||[])if(String(query).trim())queries.push(String(query).trim());
  if(step.type!=='model_output')continue;
  for(const item of step.content||[]){
   if(typeof item.text==='string'&&item.text.trim())paragraphs.push(item.text.trim());
   for(const a of item.annotations||[])if(a.type==='url_citation')add(a.url,a.title);
  }
 }
 for(const candidate of payload?.candidates||[]){
  for(const chunk of candidate.groundingMetadata?.groundingChunks||[])if(chunk.web?.uri)add(chunk.web.uri,chunk.web.title);
  if(candidate.groundingMetadata?.webSearchQueries?.length){searched=true;queries.push(...candidate.groundingMetadata.webSearchQueries.map(String));}
 }
 if(paragraphs.length)return{text:paragraphs.join('\n\n'),sources:sources.slice(0,8),searched,readUrls,queries:[...new Set(queries)].slice(0,5)};
 if(typeof payload?.output_text==='string'&&payload.output_text.trim())return{text:payload.output_text.trim(),sources:sources.slice(0,8),searched,readUrls,queries:[...new Set(queries)].slice(0,5)};
 for(const output of payload?.outputs||[]){
  if(typeof output.text==='string'&&output.text.trim())return{text:output.text.trim(),sources:sources.slice(0,8),searched,readUrls,queries:[...new Set(queries)].slice(0,5)};
  for(const item of output.content||[])if(typeof item.text==='string'&&item.text.trim())return{text:item.text.trim(),sources:sources.slice(0,8),searched,readUrls,queries:[...new Set(queries)].slice(0,5)};
 }
 const text=(payload?.candidates||[]).flatMap(x=>x.content?.parts||[]).map(x=>x.text||'').filter(Boolean).join('\n').trim();
 return{text,sources:sources.slice(0,8),searched,readUrls,queries:[...new Set(queries)].slice(0,5)};
}
async function callGeminiModel(question,secret,model){
 const search=shouldSearchWeb(question),input=geminiPrompt(question),deep=state.mode==='deep';
 const signal=state.currentController?.signal;
 const common={method:'POST',mode:'cors',cache:'no-store',headers:{'Content-Type':'application/json','x-goog-api-key':secret},...(signal?{signal}:{})};
 const generation={max_output_tokens:deep?4200:2100,temperature:deep?.16:.12,...(deep?{thinking_level:'high'}:{})};
 const interactionBody=tools=>({model,input,system_instruction:dolphinSystemInstruction(),store:false,generation_config:generation,...(tools.length?{tools:tools.map(type=>type==='google_search'?GOOGLE_SEARCH_TOOL:URL_CONTEXT_TOOL)}:{})});
 const compatibleBody=withSearch=>({systemInstruction:{parts:[{text:dolphinSystemInstruction()}]},contents:[{role:'user',parts:[{text:input}]}],generationConfig:{maxOutputTokens:deep?4200:2100,temperature:deep?.16:.12},...(withSearch?{tools:[{googleSearch:{}}]}:{})});
 let response;
 if(search){
  response=await fetch(GOOGLE_AI_ORIGIN+'/interactions',{...common,body:JSON.stringify(interactionBody(['google_search','url_context']))});
  if(!response.ok&&[400,403].includes(response.status))response=await fetch(GOOGLE_AI_ORIGIN+'/interactions',{...common,body:JSON.stringify(interactionBody(['google_search']))});
 }else{
  response=await fetch(GOOGLE_AI_ORIGIN+'/interactions',{...common,body:JSON.stringify(interactionBody([]))});
 }
 if([400,404,405].includes(response.status)){
  response=await fetch(GOOGLE_AI_ORIGIN+'/models/'+encodeURIComponent(model)+':generateContent',{...common,body:JSON.stringify(compatibleBody(search))});
  if(!response.ok&&search&&[400,403,429].includes(response.status))response=await fetch(GOOGLE_AI_ORIGIN+'/models/'+encodeURIComponent(model)+':generateContent',{...common,body:JSON.stringify(compatibleBody(false))});
 }
 const payload=await response.json().catch(()=>({}));
 if(!response.ok){const err=new Error(providerMessage(response.status,payload?.error?.message));err.status=response.status;throw err;}
 const result=providerAnswer(payload);
 if(!result.text)throw new Error('Gemini chưa trả về nội dung phân tích.');
 return{answer:result.text,provider:'Gemini',model,sourceMode:result.searched?'NATIVE_WEB_SEARCH':'FINQUERY_GROUNDED',sources:result.sources,queries:result.queries};
}
async function callLLM(question){
 const secret=sessionSecret();
 if(!secret){const err=new Error('Dolphin chưa kết nối Gemini.');err.code='NO_GEMINI_KEY';throw err;}
 if(!state.modelCandidates.length)await validateGemini(secret);
 const candidates=modelPlan(state.mode);
 if(!candidates.length)throw new Error('Không tìm thấy Gemini Flash phù hợp.');
 let lastError;
 for(const model of candidates){
  state.model=model;
  try{return await callGeminiModel(question,secret,model);}
  catch(error){
   lastError=error;
   if(error?.name==='AbortError')throw error;
   if(![404,429,500,502,503,504].includes(Number(error.status)))break;
  }
 }
 throw lastError||new Error('Gemini tạm thời chưa phản hồi.');
}
function inlineMarkdown(value){
 let out=esc(String(value||''));out=out.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');return out;
}
function llmHTML(answer,meta={}){
 const lines=String(answer||'').trim().split(/\n/),blocks=[];let bullets=[];
 const flush=()=>{if(!bullets.length)return;blocks.push('<div class="research-case">'+bullets.map(x=>'<p>• '+inlineMarkdown(x)+'</p>').join('')+'</div>');bullets=[];};
 for(const rawLine of lines){const line=rawLine.trim();if(!line){flush();continue;}const h=line.match(/^#{1,4}\s+(.+)$/);if(h){flush();blocks.push('<h4>'+inlineMarkdown(h[1])+'</h4>');continue;}const b=line.match(/^[-*]\s+(.+)$/);if(b){bullets.push(b[1]);continue;}flush();blocks.push('<p>'+inlineMarkdown(line)+'</p>');}
 flush();
 const mode=meta.sourceMode==='NATIVE_WEB_SEARCH'?'FinQuery + Gemini + Web':'FinQuery + Gemini';
 const sources=(meta.sources||[]).slice(0,6).map(s=>{const url=safeExternalUrl(s.url);return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title||url)+'</a>':'';}).filter(Boolean);
 return '<section class="analysis-block"><div class="analysis-narrative">'+blocks.join('')+'</div>'+(sources.length?'<div class="analysis-news"><strong>Nguồn đối chiếu</strong>'+sources.join('')+'</div>':'')+'<small>'+esc(mode+' · '+modeLabel())+'</small></section>';
}
function nearBottom(box){return !box||box.scrollHeight-box.scrollTop-box.clientHeight<120;}
function scrollIfNeeded(box,wasNear=true){if(box&&wasNear)box.scrollTop=box.scrollHeight;}
function addUser(text){const box=$('research-ai-messages');if(!box)return;const was=nearBottom(box),a=document.createElement('article');a.className='research-ai-message user';a.innerHTML='<strong>Câu hỏi</strong><p>'+esc(text)+'</p>';box.append(a);scrollIfNeeded(box,was);}
function addAnalysis(result){const box=$('research-ai-messages');if(!box)return;const was=nearBottom(box),a=document.createElement('article');a.className='research-ai-message assistant analysis-result';a.innerHTML=result.html;box.append(a);scrollIfNeeded(box,was);return a;}
function addThinking(){return addAnalysis({html:'<div class="analysis-empty"><span class="loading-ring"></span><p>'+(state.mode==='deep'?'Dolphin đang phân tích dữ liệu và đối chiếu nguồn…':'Dolphin đang phân tích '+esc(state.symbol||'mã đang xem')+'…')+'</p></div>'});}
function mountGeminiUI(){
 const drawer=$('research-ai');if(!drawer||$('dolphin-gemini-connect'))return;
 const box=document.createElement('section');box.id='dolphin-gemini-connect';box.className='dolphin-connect-card';
 box.innerHTML='<div class="dolphin-connect-head"><div><strong>Bật Dolphin AI thông minh</strong><small id="dolphin-gemini-status">Đang kiểm tra kết nối…</small></div><button id="dolphin-gemini-disconnect" class="dolphin-disconnect" type="button">Ngắt</button></div><div class="dolphin-mode-switch" aria-label="Chế độ AI"><button type="button" data-dolphin-mode="normal">⚡ Nhanh & tiết kiệm<small>Flash-Lite</small></button><button type="button" data-dolphin-mode="deep">✦ Phân tích sâu<small>Flash · dùng nhiều quota hơn</small></button></div><div id="dolphin-gemini-guide" class="dolphin-connect-guide"><p><b>3 bước để bật AI:</b> lấy khóa miễn phí từ Google AI Studio, sao chép rồi kết nối.</p><div><a id="dolphin-gemini-get-key" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">1. Lấy khóa miễn phí ↗</a><button id="dolphin-gemini-paste" type="button">2. Dán khóa</button></div></div><div id="dolphin-gemini-form" class="dolphin-key-form"><input id="dolphin-gemini-key" type="password" autocomplete="off" spellcheck="false" placeholder="Dán khóa Gemini của Google"><button id="dolphin-gemini-save" type="button">3. Kết nối</button></div><small id="dolphin-gemini-note" class="dolphin-connect-note">Khóa chỉ giữ trong phiên trình duyệt này; không ghi vào GitHub.</small>';
 const prompts=drawer.querySelector('.research-ai-prompts');drawer.insertBefore(box,prompts||drawer.firstChild);
 document.querySelectorAll('[data-dolphin-mode]').forEach(b=>b.addEventListener('click',()=>setAIMode(b.dataset.dolphinMode)));
 $('dolphin-gemini-save')?.addEventListener('click',connectGeminiFromUI);
 $('dolphin-gemini-key')?.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();connectGeminiFromUI();}});
 $('dolphin-gemini-paste')?.addEventListener('click',async()=>{
  const input=$('dolphin-gemini-key'),button=$('dolphin-gemini-paste');
  try{
   const value=String(await navigator.clipboard.readText()).trim();
   if(!value){renderGeminiStatus('Clipboard chưa có khóa. Hãy sao chép khóa từ Google AI Studio.');return;}
   if(input)input.value=value;if(button)button.textContent='Đã dán ✓';renderGeminiStatus('Đã dán khóa · bấm “3. Kết nối”.');
  }catch{renderGeminiStatus('Trình duyệt không cho dán tự động; hãy nhấn Ctrl+V vào ô khóa.');input?.focus();}
 });
 $('dolphin-gemini-disconnect')?.addEventListener('click',()=>{forgetSession();renderGeminiStatus();});
 setAIMode(state.mode,false);renderGeminiStatus();
}
function renderGeminiStatus(message=''){
 const secret=sessionSecret(),card=$('dolphin-gemini-connect'),status=$('dolphin-gemini-status'),form=$('dolphin-gemini-form'),guide=$('dolphin-gemini-guide'),disconnect=$('dolphin-gemini-disconnect'),note=$('dolphin-gemini-note');
 card?.classList.toggle('connected',Boolean(secret));
 if(status)status.textContent=message||(secret?('Đã kết nối · '+modeLabel()):'Chưa bật Gemini · làm 3 bước bên dưới');
 if(form)form.hidden=Boolean(secret);if(guide)guide.hidden=Boolean(secret);if(disconnect)disconnect.hidden=!secret;
 if(note)note.textContent=secret?((state.mode==='deep'?'Gemini Flash':'Gemini Flash-Lite')+' · dữ liệu tài chính lấy từ FinQuery.'):'Khóa chỉ giữ trong phiên trình duyệt này; không ghi vào GitHub.';
 document.querySelectorAll('[data-dolphin-mode]').forEach(b=>b.classList.toggle('active',b.dataset.dolphinMode===state.mode));
}
async function connectGeminiFromUI(){
 const input=$('dolphin-gemini-key'),button=$('dolphin-gemini-save'),secret=String(input?.value||'').trim();if(!secret)return;
 if(button)button.disabled=true;renderGeminiStatus('Đang xác minh trực tiếp với Google Gemini…');
 try{rememberSession(secret);await validateGemini(secret);if(input)input.value='';renderGeminiStatus('Đã kết nối · '+modeLabel());}
 catch(error){forgetSession();renderGeminiStatus(error?.message||'Không kết nối được Gemini.');}
 finally{if(button)button.disabled=false;}
}
async function refreshGeminiSession(){
 mountGeminiUI();const secret=sessionSecret();if(!secret)return;
 try{await validateGemini(secret);renderGeminiStatus('Đã kết nối · '+modeLabel());}
 catch(error){renderGeminiStatus(error?.message||'Khóa phiên cần được kiểm tra lại.');}
}
function openDrawer(){const drawer=$('research-ai'),fab=$('ai-fab');if(!drawer)return;drawer.hidden=false;drawer.classList.add('open');mountGeminiUI();if(fab){fab.setAttribute('aria-expanded','true');fab.hidden=true;}setTimeout(()=>$('research-ai-question')?.focus(),80);}
function closeDrawer(){const drawer=$('research-ai'),fab=$('ai-fab');if(!drawer)return;drawer.classList.remove('open');drawer.hidden=true;if(fab){fab.setAttribute('aria-expanded','false');fab.hidden=false;}}
async function ask(question,preferredMode=null){
 const q=String(question||'').trim();if(!q||state.busy)return;
 const nextMode=preferredMode||inferredQuestionMode(q);if(nextMode)setAIMode(nextMode);
 state.lastQuestion=q;openDrawer();addUser(q);state.busy=true;state.currentController=new AbortController();
 const send=$('research-ai-send');if(send){send.disabled=false;send.textContent='Dừng';send.dataset.busy='1';}const waiting=addThinking();
 try{
  const payload=await callLLM(q);waiting?.remove();addAnalysis({html:llmHTML(payload.answer,payload)});
  state.history.push({role:'user',content:q},{role:'assistant',content:String(payload.answer).slice(0,2400)});state.history=state.history.slice(-8);renderGeminiStatus();
 }catch(error){
  waiting?.remove();if(error?.name==='AbortError'){addAnalysis({html:'<div class="analysis-empty">Đã dừng phân tích.</div>'});return;}
  const local=analyze(q),noKey=error?.code==='NO_GEMINI_KEY';
  local.html='<div class="analysis-empty">'+(noKey?'Gemini chưa kết nối. Muốn bật AI, làm 3 bước ở phía trên. ':'Gemini chưa phản hồi; đang tiếp tục bằng FinQuery local. ')+'</div>'+local.html;addAnalysis(local);
  if(error?.message&&!noKey)renderGeminiStatus(error.message);
 }finally{state.busy=false;state.currentController=null;if(send){send.disabled=false;send.textContent='Phân tích';delete send.dataset.busy;}}
}
function sync(symbol){const next=symbol||'';if(state.symbol&&next&&next!==state.symbol)state.history=[];state.symbol=next;const title=$('research-ai-title'),fab=$('ai-fab');if(title)title.textContent=`Phân tích chuyên sâu · ${state.symbol||'VN100'}`;if(fab)fab.dataset.symbol=state.symbol||'VN100';}
window.FinQueryAI={version:DOLPHIN_VERSION,sync,ask,analyze,open:openDrawer,close:closeDrawer,connect:connectGeminiFromUI,disconnect:()=>{forgetSession();renderGeminiStatus();},setMode:setAIMode,geminiStatus:()=>({connected:Boolean(sessionSecret()),mode:state.mode,model:state.model||null})};
const form=$('research-ai-form'),input=$('research-ai-question'),sendButton=$('research-ai-send');
form?.addEventListener('submit',e=>{e.preventDefault();if(state.busy){state.currentController?.abort();return;}const q=input.value.trim();if(q){input.value='';input.style.height='';ask(q);}});
input?.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,130)+'px';});
input?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&window.innerWidth>600){e.preventDefault();form?.requestSubmit();}});
document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.aiPrompt||'',b.dataset.aiMode||null)));
$('ai-fab')?.addEventListener('click',()=>{if($('research-ai')?.hidden)openDrawer();else closeDrawer();});$('ai-close')?.addEventListener('click',closeDrawer);document.querySelector('a[href="#research-ai"]')?.addEventListener('click',e=>{e.preventDefault();openDrawer();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('research-ai')?.hidden)closeDrawer();});
restoreAIMode();sync(window.FinancialMarket?.context?.().symbol||new URLSearchParams(location.search).get('symbol')||'MBB');mountGeminiUI();void refreshGeminiSession();
})();