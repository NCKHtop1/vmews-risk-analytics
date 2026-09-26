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
function prose(items){const parts=(items||[]).filter(Boolean);return parts.length?'<div class="analysis-narrative">'+parts.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>':'';}
function relationText(value,positive='tăng',negative='giảm'){if(!Number.isFinite(value))return'không đủ dữ liệu để xác định';if(Math.abs(value)<.15)return'gần như đi ngang';return value>0?positive+' '+num(Math.abs(value))+'%':negative+' '+num(Math.abs(value))+'%';}
function movementNarrative(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q)return[];
 const ch=Number(q.changePct),dir=ch>0?'tăng':ch<0?'giảm':'đi ngang',rel=Number(d?.relativeStrengthPct),vol=Number(d?.volumeRatio20),mom=Number(d?.momentum5dPct),top=(d?.factors||[]).slice(0,2),headline=(ctx.news||[])[0],out=[];
 let first=state.symbol+' đang '+dir+' '+num(Math.abs(ch||0))+'% so với tham chiếu tại snapshot gần nhất.';
 if(Number.isFinite(rel))first+=' So với trung vị VN100, mã này '+(rel>=0?'mạnh hơn':'yếu hơn')+' khoảng '+num(Math.abs(rel))+' điểm %, nên phần biến động hiện tại '+(Math.abs(rel)>=Math.abs(ch||0)*.5?'mang dấu ấn riêng của cổ phiếu nhiều hơn':'vẫn chịu ảnh hưởng đáng kể từ thị trường chung')+'.';
 out.push(first);
 if(d){let second='Động lượng 5 phiên '+relationText(mom)+', còn thanh khoản đang ở khoảng '+num(vol)+' lần bình quân 20 phiên.';if(top.length)second+=' Hai yếu tố có đóng góp định lượng lớn nhất là '+top.map(x=>x.label.toLowerCase()+' ('+(x.contribution>0?'+':'')+num(x.contribution)+')').join(' và ')+'.';out.push(second);}
 if(headline){out.push('Tin gần nhất liên quan tới '+state.symbol+' là “'+headline.title+'” từ '+(headline.source||'nguồn báo chí')+'. Việc tin xuất hiện gần thời điểm giá biến động chỉ cho thấy sự trùng khớp về thời gian, chưa đủ để coi đó là nguyên nhân. Cách đọc hợp lý là đặt tin này sau trạng thái thị trường, sức mạnh tương đối và thanh khoản; chỉ khi phản ứng giá và khối lượng xuất hiện sau tin với cường độ rõ rệt mới tăng mức tin cậy cho quan hệ nhân quả.');}
 else out.push('Hiện chưa có tin doanh nghiệp đủ gần để giải thích trực tiếp biến động. Vì vậy nên ưu tiên cách đọc theo chuỗi: thị trường chung → sức mạnh tương đối của mã → thanh khoản → động lượng, thay vì gán nguyên nhân cho một sự kiện chưa có bằng chứng thời điểm.');
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
 if(watch.length)return['Chưa xuất hiện cảnh báo định lượng nghiêm trọng, nhưng '+watch.map(x=>x.title.toLowerCase()).join(', ')+' vẫn cần theo dõi ở các kỳ tiếp theo.'];
 return['Các thước đo rủi ro cốt lõi hiện chưa phát tín hiệu bất lợi rõ rệt trong phạm vi dữ liệu đang có.'];
}
function compareNarrative(a,q){
 const out=[];if(a)out.push('So với '+a.previous+', năm '+a.period+' ghi nhận doanh thu '+relationText(a.change.revenue)+' và lợi nhuận sau thuế '+relationText(a.change.profit)+'; tổng tài sản '+relationText(a.change.assets)+' và vốn chủ sở hữu '+relationText(a.change.equity)+'.');
 if(q)out.push('Quý '+q.period+' cho thấy doanh thu '+relationText(q.qoq.revenue)+' so với quý trước và '+relationText(q.yoyChange.revenue)+' so với cùng kỳ; lợi nhuận '+relationText(q.qoq.profit)+' QoQ và '+relationText(q.yoyChange.profit)+' YoY.');
 return out;
}
const CONCEPTS={
 roe:{name:'ROE',text:'ROE đo lợi nhuận tạo ra trên vốn chủ sở hữu bình quân. Chỉ số cao cho thấy doanh nghiệp sử dụng vốn cổ đông hiệu quả hơn, nhưng cần đọc cùng đòn bẩy vì vay nợ cao có thể làm ROE tăng.',key:'roe'},
 roa:{name:'ROA',text:'ROA đo lợi nhuận tạo ra trên tổng tài sản bình quân. Nó phản ánh hiệu quả sử dụng toàn bộ nguồn lực và thường thấp hơn ROE khi doanh nghiệp có sử dụng nợ.',key:'roa'},
 fcf:{name:'FCF',text:'FCF, hay dòng tiền tự do, là lượng tiền còn lại sau khi dòng tiền từ hoạt động kinh doanh trang trải chi đầu tư tài sản dài hạn. FCF dương bền vững thường cho thấy doanh nghiệp có dư địa trả nợ, cổ tức hoặc tái đầu tư.',key:null},
 ocf:{name:'OCF',text:'OCF là dòng tiền thuần từ hoạt động kinh doanh. So OCF với lợi nhuận sau thuế giúp đánh giá chất lượng lợi nhuận: lợi nhuận tăng nhưng OCF yếu kéo dài thường là dấu hiệu cần xem kỹ vốn lưu động.',key:null},
 biengop:{name:'Biên lợi nhuận gộp',text:'Biên lợi nhuận gộp cho biết phần doanh thu còn lại sau giá vốn. Biên tăng thường phản ánh giá bán, cơ cấu sản phẩm hoặc chi phí đầu vào thuận lợi hơn; biên giảm có thể cho thấy áp lực cạnh tranh hoặc chi phí.',key:'grossMargin'},
 bienrong:{name:'Biên lợi nhuận ròng',text:'Biên lợi nhuận ròng cho biết bao nhiêu lợi nhuận sau thuế được tạo ra từ mỗi đồng doanh thu. Đây là thước đo tổng hợp sau giá vốn, chi phí vận hành, tài chính và thuế.',key:'netMargin'},
 donbay:{name:'Đòn bẩy tài chính',text:'Đòn bẩy phản ánh mức độ doanh nghiệp sử dụng nợ để tài trợ tài sản và hoạt động. Nợ cao không tự động là xấu, nhưng làm tăng độ nhạy với lãi suất, dòng tiền và khả năng tái cấp vốn.',key:'liabilitiesAssets'},
 phaitthu:{name:'Khoản phải thu',text:'Khoản phải thu là doanh thu hoặc nghĩa vụ khách hàng chưa chuyển thành tiền. Nếu phải thu tăng nhanh hơn doanh thu trong nhiều kỳ, cần kiểm tra chất lượng doanh thu và tốc độ thu tiền.',key:null},
 tonkho:{name:'Hàng tồn kho',text:'Hàng tồn kho phản ánh hàng hóa, nguyên vật liệu hoặc sản phẩm chưa được tiêu thụ. Tăng tồn kho có thể phục vụ mở rộng kinh doanh, nhưng tăng nhanh kéo dài có thể làm vốn bị giam và tăng rủi ro giảm giá.',key:null}
};
function conceptKey(question){const s=norm(question);if(/\broe\b/.test(s))return'roe';if(/\broa\b/.test(s))return'roa';if(/\bfcf\b|dong tien tu do/.test(s))return'fcf';if(/\bocf\b|dong tien hd|dong tien hoat dong kinh doanh/.test(s))return'ocf';if(/bien.*gop/.test(s))return'biengop';if(/bien.*rong/.test(s))return'bienrong';if(/don bay|no tren tai san|no tren von/.test(s))return'donbay';if(/phai thu/.test(s))return'phaitthu';if(/ton kho/.test(s))return'tonkho';return null;}
function conceptHTML(question,a,q){
 const key=conceptKey(question),d=CONCEPTS[key];if(!d)return'';
 let current='';if(a){if(key==='fcf')current=' Với '+state.symbol+', FCF năm '+a.period+' ước tính '+money(a.values.fcf)+'.';else if(key==='ocf')current=' Với '+state.symbol+', OCF năm '+a.period+' là '+money(a.values.ocf)+', tương đương '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế.';else if(key==='donbay')current=' Với '+state.symbol+', nợ phải trả hiện tương đương '+num(a.ratios.liabilitiesAssets)+'% tổng tài sản.';else if(key==='phaitthu')current=' Với '+state.symbol+', phải thu năm '+a.period+' là '+money(a.values.receivables)+', thay đổi '+pct(a.change.receivables)+' so với năm trước.';else if(key==='tonkho')current=' Với '+state.symbol+', tồn kho năm '+a.period+' là '+money(a.values.inventory)+'.';else if(d.key&&Number.isFinite(a.ratios[d.key]))current=' Với '+state.symbol+', '+d.name+' năm '+a.period+' là '+num(a.ratios[d.key])+'%.';}
 return prose([d.text+current])+financialHTML(a,q);
}
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
 return`${prose(movementNarrative(ctx))}<div class="analysis-kpis">${kpis}</div>${factors.length?section('Phân rã động lực',table(factors)):''}${section('Bối cảnh định lượng',details)}${headlineList(ctx.news)}`;
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
 return`${prose(financialNarrative(a,q))}<div class="analysis-kpis">${kpis}</div>${section('Tăng trưởng & hiệu quả',perf)}${section('Chất lượng dòng tiền',cash)}${section('Cơ cấu tài chính',balance)}${q?section('Quý gần nhất',quarter):''}`;
}
function riskHTML(a,q){
 const signals=riskSignals(a,q);if(!signals.length)return section('Rủi ro định lượng','<div class="analysis-empty">Chưa đủ dữ liệu để tạo cảnh báo định lượng.</div>');
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
function searchHTML(question,annual,quarterly){
 const terms=norm(question).split(' ').filter(x=>x.length>2),datasets=[['Năm',annual],['Quý',quarterly]],hits=[];
 for(const [label,data] of datasets){if(!data)continue;for(const r of rows(data)){const n=norm(r.label),score=terms.reduce((a,t)=>a+(n.includes(t)?1:0),0);if(!score)continue;const ps=periods(data).slice(-5),vals=ps.filter(p=>Number.isFinite(val(r,p))).map(p=>`${p}: ${point(val(r,p),r.unit)}`);if(vals.length)hits.push({score,label,row:r,vals});}}
 hits.sort((a,b)=>b.score-a.score);if(!hits.length)return section('Kết quả','<div class="analysis-empty">Không tìm thấy chỉ tiêu phù hợp trong dữ liệu hiện có. Hãy hỏi theo nhóm: doanh thu, lợi nhuận, dòng tiền, nợ, tài sản, ROE, ROA, phải thu hoặc tồn kho.</div>');
 return section('Chỉ tiêu liên quan',`<div class="analysis-search-results">${hits.slice(0,12).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.label)}</span><p>${esc(h.vals.join(' · '))}</p></div>`).join('')}</div>`);
}
function macroDatasetFor(question,macro){if(!macro?.datasets)return null;const s=norm(question),id=/\bpmi\b/.test(s)?'pmi':/\bfdi\b/.test(s)?'fdi':/gdp/.test(s)?'gdp_growth':/cung tien|m2|money supply/.test(s)?'money_supply':/tin dung|credit/.test(s)?'credit_sector':'macro_overview';return macro.datasets[id]?{id,...macro.datasets[id]}:null;}
function macroNews(question,items){const terms=norm(question).split(' ').filter(x=>x.length>2&&!['tai','sao','giam','tang','nhu','the','nao','hien','nay'].includes(x));return(items||[]).map(n=>{const s=norm(n.title),score=terms.reduce((a,t)=>a+(s.includes(t)?1:0),0);return{...n,score};}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||Date.parse(b.publishedAt)-Date.parse(a.publishedAt)).slice(0,5);}
function macroHTML(question,m){
 const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro),matched=macroNews(question,m.marketNews||[]),paragraphs=[];
 if(ds){const rows=ds.rows||[],last=rows.at(-1),prev=rows.at(-2),numeric=ds.numericColumns||[];const chosen=numeric.find(k=>norm(question).split(' ').some(t=>t.length>2&&norm(k).includes(t)))||numeric[0];if(last&&chosen&&typeof last[chosen]==='number'){let sentence='Trong dữ liệu VBMA gần nhất, '+chosen+' ở mức '+num(last[chosen])+'.';if(prev&&typeof prev[chosen]==='number'&&prev[chosen]!==0){const change=(last[chosen]/prev[chosen]-1)*100;sentence+=' So với điểm liền trước, chỉ tiêu này '+relationText(change)+'.';}paragraphs.push(sentence);}}
 if(matched.length){const first=matched[0];paragraphs.push('Tin phù hợp nhất với câu hỏi hiện là “'+first.title+'” từ '+(first.source||'nguồn chính thống')+'. FinQuery dùng tin này như bằng chứng bối cảnh, không coi việc xuất hiện cùng ngày là bằng chứng nhân quả. Nếu sự kiện điều tiết xảy ra sau khi biến thị trường đã bắt đầu đảo chiều, nó thường phù hợp hơn với vai trò phản ứng/điều tiết trạng thái đang có thay vì là nguyên nhân khởi phát.');if(matched[1])paragraphs.push('Chuỗi thời gian cần đọc theo thứ tự: trạng thái trước sự kiện → hành động chính sách/thị trường → phản ứng sau đó. Tin “'+matched[1].title+'” cung cấp thêm bối cảnh cho bước này; hướng kết luận chỉ nên mạnh lên khi nhiều nguồn và dữ liệu định lượng cùng chỉ về một cơ chế.');}
 else paragraphs.push('Chưa có tin thị trường đủ sát câu hỏi để gán nguyên nhân. Với các câu hỏi về NHNN, OMO, lãi suất qua đêm hay thanh khoản, FinQuery ưu tiên logic thời gian: căng thẳng thanh khoản xuất hiện trước hay sau hành động điều tiết, rồi mới xem lãi suất và nhu cầu vay phản ứng thế nào.');
 let sources='';if(matched.length)sources=section('Tin thị trường liên quan',`<div class="analysis-news">${matched.map(n=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`).join('')}</div>`);
 return prose(paragraphs)+sources;
}
function classify(q){const s=norm(q);if(/nhnn|ngan hang nha nuoc|lai suat|overnight|\bon\b|omo|thanh khoan|ty gia|lam phat|\bgdp\b|\bpmi\b|\bfdi\b|cung tien|m2|tin dung|vi mo/.test(s))return'macro';if((/la gi|nghia la gi|khai niem|giai thich|hieu the nao/.test(s))&&conceptKey(q))return'concept';if(/vi sao|nguyen nhan|tang|giam|bien dong|phien|gia co phieu|dong luc/.test(s))return'movement';if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';if(/suc khoe|tai chinh|tong quan|doanh thu|loi nhuan|dong tien|no|roe|roa|bien loi nhuan|fcf|ocf|phai thu|ton kho/.test(s))return'financial';return'search';}
function analyze(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 const ctx={quote:m.quote||null,driver:m.driver||null,news:m.news||[],marketNews:m.marketNews||[]};
 const body=type==='macro'?macroHTML(question,m):type==='movement'?movementHTML(ctx):type==='concept'?conceptHTML(question,a,q):type==='financial'?financialHTML(a,q):type==='risk'?riskHTML(a,q):type==='compare'?comparisonHTML(a,q):searchHTML(question,annual,quarterly);
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