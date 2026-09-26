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
 const q=ctx.quote,d=ctx.driver,t=ctx.technical,headline=(ctx.news||[])[0],out=[];
 if(q){
  const ch=Number(q.changePct),abs=Number.isFinite(q.price)&&Number.isFinite(q.reference)?q.price-q.reference:null,dir=ch>0?'tăng':ch<0?'giảm':'đi ngang';
  let first=state.symbol+' '+dir+' '+num(Math.abs(ch||0))+'%';
  if(Number.isFinite(q.price))first+=' lên '+nf.format(q.price)+' đ';
  if(Number.isFinite(q.reference))first+=' so với giá phiên trước '+nf.format(q.reference)+' đ';
  if(Number.isFinite(abs))first+=' ('+(abs>0?'+':'')+nf.format(abs)+' đ)';
  first+='.';
  out.push(first);
 }
 if(d){
  const rel=Number(d.relativeStrengthPct),vol=Number(d.volumeRatio20),mom=Number(d.momentum5dPct),top=(d.factors||[]).slice(0,3);
  let second='Động lực định lượng hiện nghiêng '+(d.score>8?'tăng':d.score<-8?'giảm':'trung tính')+' với điểm '+(d.score>0?'+':'')+num(d.score)+'/100.';
  if(top.length)second+=' Trụ chính: '+top.map(x=>x.label.toLowerCase()+' '+(x.contribution>0?'+':'')+num(x.contribution)).join(' · ')+'.';
  if(Number.isFinite(rel))second+=' Sức mạnh tương đối '+(rel>=0?'cao hơn':'thấp hơn')+' trung vị VN100 '+num(Math.abs(rel))+' điểm %.';
  if(Number.isFinite(vol))second+=' Thanh khoản '+num(vol)+'x TB20.';
  if(Number.isFinite(mom))second+=' Động lượng 5 phiên '+pct(mom)+'.';
  out.push(second);
 }
 if(t)out.push('Kỹ thuật khung '+t.timeframe+': tín hiệu '+t.label+' '+t.confidence+'/100. '+t.summary+'.');
 if(headline){
  const newsFactor=(d?.factors||[]).find(x=>x.id==='news'),weight=Number(newsFactor?.contribution);
  let rank='bổ trợ';if(Number.isFinite(weight)&&Math.abs(weight)>=8)rank='mạnh';else if(Number.isFinite(weight)&&Math.abs(weight)>=3)rank='trung bình';
  out.push('Catalyst tin tức ưu tiên: “'+headline.title+'” ('+(headline.source||'nguồn báo chí')+'). Mức tác động trong mô hình động lực: '+rank+(Number.isFinite(weight)?' · đóng góp '+(weight>0?'+':'')+num(weight):'')+'.');
 }
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
 sma:{name:'SMA',aliases:['sma','simple moving average','duong trung binh don'],text:'SMA là trung bình cộng giá đóng cửa trong một số phiên cố định. Nó làm mượt nhiễu để nhìn xu hướng nền.',formula:'SMA(n) = tổng n giá đóng cửa / n',read:'Giá trên SMA và SMA dốc lên thiên về xu hướng tăng; giá dưới SMA và SMA dốc xuống thiên về xu hướng giảm. Cắt SMA chỉ mạnh khi đi kèm động lượng và khối lượng.',source:'technical'},
 ema:{name:'EMA',aliases:['ema','exponential moving average','duong trung binh luy thua'],text:'EMA là đường trung bình đặt trọng số lớn hơn cho dữ liệu gần nhất nên phản ứng nhanh hơn SMA.',formula:'EMA hôm nay = Giá × k + EMA trước × (1-k), k=2/(n+1)',read:'EMA phù hợp theo dõi thay đổi xu hướng ngắn hạn. Giá trên EMA cho thấy lực giá hiện tại cao hơn nền gần đây.',source:'technical'},
 wma:{name:'WMA',aliases:['wma','weighted moving average'],text:'WMA là trung bình động có trọng số tuyến tính, phiên gần nhất được trọng số cao nhất.',formula:'WMA = Σ(Giá × trọng số) / Σ trọng số',read:'Phản ứng nhanh hơn SMA, chậm hoặc tương đương EMA tùy chu kỳ.',source:'technical'},
 vwma:{name:'VWMA',aliases:['vwma','volume weighted moving average'],text:'VWMA là trung bình giá có trọng số theo khối lượng, nhấn mạnh những phiên có giao dịch lớn.',formula:'VWMA = Σ(Giá × Khối lượng) / Σ Khối lượng',read:'Giá trên VWMA cho thấy giao dịch hiện tại cao hơn mức giá trung bình được khối lượng xác nhận.',source:'technical'},
 rsi:{name:'RSI',aliases:['rsi','relative strength index','qua mua','qua ban','mean reversion rsi'],text:'RSI đo cường độ tăng/giảm trên thang 0–100, thường dùng chu kỳ 14.',formula:'RSI = 100 - 100/(1+RS), RS = TB tăng / TB giảm',read:'Trên 70: quá mua; dưới 30: quá bán; 45–55: vùng mean. RSI rời >70 đi xuống hoặc rời <30 đi lên là mean reversion về 50; RSI duy trì >55 hoặc <45 thể hiện động lượng có hướng.',source:'technical'},
 macd:{name:'MACD',aliases:['macd','signal','histogram macd'],text:'MACD đo chênh lệch giữa EMA nhanh và EMA chậm; Signal là EMA của MACD; Histogram là MACD trừ Signal.',formula:'MACD = EMA12 - EMA26; Signal = EMA9(MACD)',read:'MACD cắt lên Signal là chuyển động lượng sang tăng; cắt xuống là chuyển sang giảm. Histogram mở rộng cùng hướng cho thấy động lượng đang mạnh thêm.',source:'technical'},
 bollinger:{name:'Bollinger Bands',aliases:['bollinger','bollinger bands','bb'],text:'Bollinger Bands tạo dải quanh SMA bằng độ lệch chuẩn để đo vị trí giá và biến động.',formula:'Middle=SMA(n); Upper/Lower = SMA ± k×σ',read:'Dải mở rộng = biến động tăng; co hẹp = biến động giảm. Giá chạm dải không tự động là đảo chiều; cần đọc với RSI, xu hướng và volume.',source:'technical'},
 supertrend:{name:'Supertrend',aliases:['supertrend'],text:'Supertrend dùng ATR để tạo ngưỡng bám theo giá và xác định hướng xu hướng.',formula:'Ngưỡng cơ sở = (High+Low)/2 ± hệ số×ATR',read:'Supertrend tăng khi giá nằm trên ngưỡng theo xu hướng; chuyển màu/hướng là tín hiệu đổi chế độ xu hướng.',source:'technical'},
 adx:{name:'ADX',aliases:['adx','average directional index'],text:'ADX đo độ mạnh của xu hướng, không đo hướng.',formula:'ADX được làm mượt từ +DI, -DI và DX',read:'ADX <20: xu hướng yếu; 20–25: hình thành; >25: đủ mạnh; >30: mạnh. Hướng lấy từ giá/MACD/Supertrend.',source:'technical'},
 atr:{name:'ATR',aliases:['atr','average true range'],text:'ATR đo biên độ dao động thực tế trung bình, phản ánh biến động chứ không phản ánh hướng.',formula:'TR=max(H-L, |H-C trước|, |L-C trước|); ATR=MA(TR)',read:'ATR tăng = biên dao động lớn hơn; dùng để đặt khoảng dừng lỗ/biên kỳ vọng theo biến động.',source:'technical'},
 stochastic:{name:'Stochastic',aliases:['stochastic','stoch','%k','%d'],text:'Stochastic so vị trí giá đóng cửa với biên cao-thấp của một cửa sổ.',formula:'%K = (Close-Low_n)/(High_n-Low_n)×100; %D = MA(%K)',read:'>80 thường là vùng cao, <20 vùng thấp; giao cắt %K/%D có ý nghĩa hơn khi phù hợp xu hướng lớn.',source:'technical'},
 cci:{name:'CCI',aliases:['cci','commodity channel index'],text:'CCI đo độ lệch của giá điển hình so với trung bình thống kê.',formula:'CCI=(Typical Price-SMA)/(0.015×Mean Deviation)',read:'Trên +100 cho thấy động lượng tăng mạnh; dưới -100 là giảm mạnh; quay lại qua các ngưỡng thường dùng để nhận biết suy giảm động lượng.',source:'technical'},
 roc:{name:'ROC',aliases:['roc','rate of change'],text:'ROC đo phần trăm thay đổi giá so với n phiên trước.',formula:'ROC = (Close_t / Close_t-n - 1)×100',read:'ROC >0 là động lượng tăng, <0 là giảm; độ lớn cho biết tốc độ biến động.',source:'technical'},
 willr:{name:'Williams %R',aliases:['williams','williams %r','willr'],text:'Williams %R đo vị trí giá đóng cửa trong biên cao-thấp, thang từ -100 đến 0.',formula:'%R = (High_n-Close)/(High_n-Low_n)×-100',read:'Trên -20 là vùng cao; dưới -80 là vùng thấp; nên kết hợp xu hướng.',source:'technical'},
 volume:{name:'Khối lượng',aliases:['volume','khoi luong','thanh khoan'],text:'Khối lượng cho biết số cổ phiếu giao dịch. FinQuery so khối lượng hiện tại với trung bình 20 nến để đo mức xác nhận.',formula:'Volume ratio 20 = KL hiện tại / KL trung bình 20 nến trước',read:'≥1.5x: bùng nổ; 1.15–1.5x: xác nhận tốt; 0.8–1.15x: bình thường; <0.8x: thấp.',source:'technical'},
 obv:{name:'OBV',aliases:['obv','on balance volume'],text:'OBV cộng/trừ khối lượng theo hướng giá đóng cửa để theo dõi dòng tiền tích lũy.',formula:'OBV_t = OBV_t-1 ± Volume_t',read:'OBV tăng đồng pha với giá củng cố xu hướng; phân kỳ giá–OBV cảnh báo độ bền suy yếu.',source:'technical'},
 mfi:{name:'MFI',aliases:['mfi','money flow index'],text:'MFI giống RSI nhưng đưa khối lượng vào dòng tiền dương/âm.',formula:'MFI = 100 - 100/(1+Money Ratio)',read:'>80 thường quá mua, <20 quá bán; phân kỳ có thể báo suy yếu dòng tiền.',source:'technical'},
 cmf:{name:'CMF',aliases:['cmf','chaikin money flow'],text:'CMF đo áp lực tích lũy/phân phối dựa trên vị trí đóng cửa trong biên và khối lượng.',formula:'CMF = Σ Money Flow Volume / Σ Volume',read:'CMF >0 nghiêng tích lũy; <0 nghiêng phân phối.',source:'technical'},
 meanreversion:{name:'Mean reversion',aliases:['mean reversion','hoi quy ve trung binh','quay lai mean'],text:'Mean reversion là hiện tượng giá hoặc chỉ báo sau khi lệch xa mức trung bình có xu hướng quay về vùng cân bằng.',formula:'Không có một công thức duy nhất; thường đo bằng z-score, RSI hoặc khoảng cách tới MA.',read:'Trong FinQuery, RSI rời vùng >70 đi xuống hoặc <30 đi lên được mô tả là quay về mean 50.',source:'technical'},
 support:{name:'Hỗ trợ',aliases:['ho tro','support'],text:'Hỗ trợ là vùng giá nơi lực mua từng hấp thụ lực bán hoặc giá nhiều lần phản ứng đi lên.',formula:'Xác định từ đáy lặp lại, vùng khối lượng, MA hoặc cấu trúc giá.',read:'Hỗ trợ là vùng, không phải một điểm tuyệt đối; phá vỡ có giá trị hơn khi đóng cửa dưới vùng với volume tăng.',source:'technical'},
 resistance:{name:'Kháng cự',aliases:['khang cu','resistance'],text:'Kháng cự là vùng giá nơi lực bán từng chặn đà tăng.',formula:'Xác định từ đỉnh lặp lại, vùng cung, MA hoặc cấu trúc giá.',read:'Vượt kháng cự kèm volume tăng thường mạnh hơn vượt với thanh khoản thấp.',source:'technical'},
 revenue:{name:'Doanh thu',aliases:['doanh thu','revenue'],text:'Doanh thu là giá trị bán hàng/dịch vụ ghi nhận trong kỳ trước khi trừ phần lớn chi phí.',formula:'Tùy ngành và chuẩn kế toán; đọc trực tiếp từ KQKD.',read:'Nên so YoY/QoQ, biên lợi nhuận và dòng tiền để đánh giá chất lượng tăng trưởng.',source:'financial'},
 grossprofit:{name:'Lợi nhuận gộp',aliases:['loi nhuan gop','gross profit'],text:'Lợi nhuận gộp là doanh thu thuần trừ giá vốn.',formula:'LN gộp = Doanh thu thuần - Giá vốn',read:'Cho biết phần giá trị còn lại để trang trải chi phí vận hành, tài chính và thuế.',source:'financial'},
 netprofit:{name:'Lợi nhuận sau thuế',aliases:['lnst','loi nhuan sau thue','net profit'],text:'Lợi nhuận sau thuế là lợi nhuận còn lại sau toàn bộ chi phí và thuế.',formula:'LNST = LNTT - thuế TNDN',read:'So tăng trưởng LNST với doanh thu và OCF để kiểm tra đòn bẩy lợi nhuận và chất lượng lợi nhuận.',source:'financial'},
 roe:{name:'ROE',aliases:['roe','return on equity'],text:'ROE đo lợi nhuận tạo ra trên vốn chủ sở hữu bình quân.',formula:'ROE = LNST / VCSH bình quân ×100%',read:'ROE cao phản ánh hiệu quả vốn chủ nhưng phải đọc cùng đòn bẩy vì nợ cao có thể khuếch đại ROE.',source:'financial',metric:'roe'},
 roa:{name:'ROA',aliases:['roa','return on assets'],text:'ROA đo lợi nhuận tạo ra trên tổng tài sản bình quân.',formula:'ROA = LNST / Tổng tài sản bình quân ×100%',read:'Phản ánh hiệu quả sử dụng toàn bộ tài sản; hữu ích khi so các doanh nghiệp cùng ngành.',source:'financial',metric:'roa'},
 grossmargin:{name:'Biên lợi nhuận gộp',aliases:['bien loi nhuan gop','bien gop','gross margin'],text:'Biên gộp cho biết tỷ lệ doanh thu còn lại sau giá vốn.',formula:'Biên gộp = LN gộp / Doanh thu thuần ×100%',read:'Biên tăng cho thấy pricing mix/chi phí đầu vào thuận lợi hơn; biên giảm cho thấy áp lực giá vốn hoặc cạnh tranh.',source:'financial',metric:'grossMargin'},
 netmargin:{name:'Biên lợi nhuận ròng',aliases:['bien loi nhuan rong','bien rong','net margin'],text:'Biên ròng cho biết bao nhiêu LNST được tạo ra từ mỗi đồng doanh thu.',formula:'Biên ròng = LNST / Doanh thu ×100%',read:'Đây là thước đo tổng hợp sau chi phí vận hành, tài chính và thuế.',source:'financial',metric:'netMargin'},
 ocf:{name:'OCF',aliases:['ocf','dong tien hd','dong tien hoat dong kinh doanh'],text:'OCF là dòng tiền thuần từ hoạt động kinh doanh.',formula:'Theo báo cáo lưu chuyển tiền tệ; có thể bắt đầu từ LNST rồi điều chỉnh phi tiền tệ và vốn lưu động.',read:'OCF/LNST quanh hoặc trên 100% trong nhiều kỳ thường thể hiện lợi nhuận chuyển hóa thành tiền tốt.',source:'financial'},
 fcf:{name:'FCF',aliases:['fcf','dong tien tu do','free cash flow'],text:'FCF là tiền còn lại sau khi dòng tiền kinh doanh trang trải đầu tư tài sản dài hạn.',formula:'FCF ≈ OCF - CAPEX tiền mặt; trong dữ liệu FinQuery CAPEX chi ra mang dấu âm nên hiển thị OCF + CAPEX.',read:'FCF dương bền vững tạo dư địa trả nợ, cổ tức hoặc tái đầu tư.',source:'financial'},
 capex:{name:'CAPEX',aliases:['capex','chi dau tu','chi mua tscd'],text:'CAPEX là chi đầu tư tài sản cố định và tài sản dài hạn phục vụ hoạt động.',formula:'Lấy từ dòng tiền đầu tư.',read:'CAPEX cao có thể là mở rộng; cần so với OCF, tăng trưởng và hiệu suất tài sản.',source:'financial'},
 leverage:{name:'Đòn bẩy tài chính',aliases:['don bay','no tren tai san','no tren von','leverage'],text:'Đòn bẩy phản ánh mức độ doanh nghiệp dùng nợ để tài trợ tài sản và vốn.',formula:'Ví dụ: Nợ/Tài sản = Nợ phải trả / Tổng tài sản; Nợ/VCSH = Nợ / VCSH',read:'Đòn bẩy cao làm lợi nhuận nhạy hơn với lãi suất và chu kỳ; mức hợp lý phụ thuộc ngành.',source:'financial',metric:'liabilitiesAssets'},
 receivables:{name:'Khoản phải thu',aliases:['phai thu','receivables'],text:'Khoản phải thu là số tiền khách hàng/đối tác còn phải thanh toán.',formula:'Đọc từ bảng cân đối; có thể so Phải thu/Doanh thu và DSO.',read:'Phải thu tăng nhanh hơn doanh thu kéo dài là tín hiệu chất lượng doanh thu cần kiểm tra.',source:'financial'},
 inventory:{name:'Hàng tồn kho',aliases:['ton kho','hang ton kho','inventory'],text:'Hàng tồn kho là nguyên vật liệu, sản phẩm dở dang hoặc hàng hóa chưa bán.',formula:'Đọc từ bảng cân đối; có thể so Tồn kho/Doanh thu hoặc DIO.',read:'Tăng tồn kho có thể phục vụ mở rộng, nhưng tăng nhanh kéo dài có thể giam vốn hoặc báo nhu cầu yếu.',source:'financial'},
 currentratio:{name:'Current ratio',aliases:['current ratio','ty so thanh toan hien hanh'],text:'Current ratio đo khả năng tài sản ngắn hạn bao phủ nợ ngắn hạn.',formula:'Tài sản ngắn hạn / Nợ ngắn hạn',read:'>1 thường nghĩa là tài sản ngắn hạn lớn hơn nợ ngắn hạn; chuẩn phù hợp phụ thuộc ngành.',source:'financial'},
 quickratio:{name:'Quick ratio',aliases:['quick ratio','ty so thanh toan nhanh'],text:'Quick ratio loại tồn kho khỏi tài sản ngắn hạn để đo thanh khoản thận trọng hơn.',formula:'(Tài sản ngắn hạn - Tồn kho) / Nợ ngắn hạn',read:'Hữu ích với doanh nghiệp có tồn kho lớn hoặc khó chuyển đổi thành tiền.',source:'financial',metric:'quick'},
 eps:{name:'EPS',aliases:['eps','earnings per share','lai co ban tren co phieu'],text:'EPS là lợi nhuận thuộc cổ đông thường trên số cổ phiếu bình quân.',formula:'EPS = LNST thuộc CĐ thường / CP bình quân',read:'EPS dùng trong định giá P/E và so tăng trưởng lợi nhuận trên mỗi cổ phiếu.',source:'financial'},
 pe:{name:'P/E',aliases:['p e','pe','price earnings'],text:'P/E cho biết giá thị trường đang trả bao nhiêu lần lợi nhuận trên mỗi cổ phiếu.',formula:'P/E = Giá cổ phiếu / EPS',read:'P/E cao có thể phản ánh kỳ vọng tăng trưởng hoặc định giá cao; phải so ngành và chu kỳ.',source:'financial'},
 pb:{name:'P/B',aliases:['p b','pb','price book'],text:'P/B so giá thị trường với giá trị sổ sách trên mỗi cổ phiếu.',formula:'P/B = Giá / BVPS',read:'Thường hữu ích với ngân hàng/tài chính và doanh nghiệp tài sản lớn; cần kết hợp ROE.',source:'financial'},
 reference:{name:'Giá phiên trước / giá tham chiếu',aliases:['phien truoc','gia phien truoc','gia tham chieu','reference price'],text:'Trong bảng VN100, “Phiên trước” dùng giá tham chiếu của phiên hiện tại, thông thường chính là giá đóng cửa điều chỉnh theo quy định của phiên giao dịch trước.',formula:'± Giá = Giá hiện tại - Giá phiên trước; ±% = (Giá hiện tại/Giá phiên trước -1)×100%',read:'Ví dụ +3,59% nghĩa là giá hiện tại cao hơn giá phiên trước 3,59%; FinQuery hiển thị cả mức giá trước và chênh lệch tuyệt đối.',source:'market'},
 relativestrength:{name:'Sức mạnh tương đối',aliases:['suc manh tuong doi','relative strength'],text:'Sức mạnh tương đối của FinQuery so biến động mã với trung vị biến động VN100 cùng snapshot.',formula:'RS tương đối = % thay đổi mã - trung vị % thay đổi VN100',read:'Dương = mã mạnh hơn thị trường; âm = yếu hơn thị trường.',source:'market'},
 driverscore:{name:'Điểm động lực',aliases:['diem dong luc','dong luc','driver score'],text:'Điểm động lực FinQuery tổng hợp thị trường chung, sức mạnh tương đối, volume, động lượng 5 phiên và tin tức bằng trọng số minh bạch.',formula:'Điểm = Σ(điểm yếu tố × trọng số), chuẩn hóa khoảng -100 đến +100',read:'Điểm dương nghiêng tăng, âm nghiêng giảm; độ lớn cho biết mức đồng thuận của các yếu tố.',source:'system'},
 gdp:{name:'GDP',aliases:['gdp','tong san pham quoc noi'],text:'GDP đo giá trị hàng hóa và dịch vụ cuối cùng sản xuất trong nền kinh tế trong một giai đoạn.',formula:'Có thể tính theo sản xuất, chi tiêu hoặc thu nhập.',read:'Tăng trưởng GDP phản ánh nhịp hoạt động kinh tế; tác động khác nhau theo ngành.',source:'macro'},
 cpi:{name:'CPI / lạm phát',aliases:['cpi','lam phat','inflation'],text:'CPI đo mức thay đổi giá của rổ hàng hóa/dịch vụ tiêu dùng.',formula:'CPI growth = CPI_t/CPI_base -1',read:'Lạm phát ảnh hưởng lãi suất, sức mua, chi phí đầu vào và định giá tài sản.',source:'macro'},
 pmi:{name:'PMI',aliases:['pmi','purchasing managers index'],text:'PMI là chỉ số khảo sát quản trị mua hàng phản ánh tốc độ hoạt động sản xuất/dịch vụ.',formula:'Chỉ số khuếch tán từ nhiều thành phần khảo sát.',read:'Trên 50 = mở rộng; dưới 50 = thu hẹp; tốc độ thay đổi cũng quan trọng.',source:'macro'},
 fdi:{name:'FDI',aliases:['fdi','dau tu truc tiep nuoc ngoai'],text:'FDI là vốn đầu tư trực tiếp nước ngoài vào hoạt động sản xuất/kinh doanh trong nước.',formula:'Theo số đăng ký, điều chỉnh và giải ngân tùy bộ dữ liệu.',read:'Giải ngân FDI phản ánh dòng vốn thực tế tốt hơn chỉ nhìn đăng ký.',source:'macro'},
 m2:{name:'M2',aliases:['m2','cung tien','money supply'],text:'M2 là thước đo cung tiền rộng gồm tiền mặt, tiền gửi thanh toán và nhiều loại tiền gửi có kỳ hạn.',formula:'Theo định nghĩa thống kê tiền tệ của cơ quan quản lý.',read:'M2 tăng nhanh thường đi cùng thanh khoản hệ thống cao hơn; phải đọc cùng tín dụng và lạm phát.',source:'macro'},
 credit:{name:'Tín dụng',aliases:['tin dung','credit growth','du no'],text:'Tăng trưởng tín dụng đo tốc độ mở rộng dư nợ của hệ thống ngân hàng.',formula:'Tăng trưởng = Dư nợ hiện tại/Dư nợ kỳ gốc -1',read:'Tín dụng tăng hỗ trợ hoạt động kinh tế nhưng tốc độ quá cao có thể tăng rủi ro lạm phát/chất lượng tài sản.',source:'macro'},
 omo:{name:'OMO',aliases:['omo','thi truong mo','open market operations'],text:'OMO là nghiệp vụ thị trường mở của ngân hàng trung ương để bơm/hút thanh khoản ngắn hạn qua giấy tờ có giá.',formula:'Theo khối lượng trúng thầu, kỳ hạn và lãi suất OMO.',read:'Bơm ròng thường hỗ trợ thanh khoản; hút ròng làm thanh khoản bớt dư thừa.',source:'macro'},
 overnight:{name:'Lãi suất qua đêm',aliases:['overnight','lai suat qua dem','on rate'],text:'Lãi suất qua đêm là chi phí vay mượn rất ngắn giữa các tổ chức tín dụng.',formula:'Lãi suất thị trường liên ngân hàng kỳ hạn O/N.',read:'Tăng mạnh thường phản ánh thanh khoản ngắn hạn căng hơn; giảm mạnh thường phản ánh thanh khoản dồi dào hơn.',source:'macro'},
 forecast:{name:'Dự báo T+1–T+5',aliases:['t 1','t+1','t 5','t+5','forecast','du bao'],text:'T+1–T+5 là các chân trời dự báo một đến năm phiên giao dịch tiếp theo trong trang Forecast.',formula:'Đầu ra phụ thuộc pipeline mô hình, feature và snapshot dữ liệu đang dùng.',read:'Nên đọc đường dự báo cùng sai số backtest, độ ổn định qua thời gian và bối cảnh kỹ thuật thay vì chỉ nhìn một điểm giá.',source:'system'},
 backtest:{name:'Backtest',aliases:['backtest','kiem dinh qua khu'],text:'Backtest chạy quy tắc hoặc mô hình trên dữ liệu lịch sử để đo hiệu năng ngoài giai đoạn huấn luyện.',formula:'Tùy bài toán: MAE/RMSE/MAPE, directional accuracy, return, drawdown…',read:'Backtest tốt cần tránh leakage, dùng walk-forward và giữ nguyên logic như khi chạy thật.',source:'system'},
 rmse:{name:'RMSE',aliases:['rmse'],text:'RMSE đo căn bậc hai của trung bình bình phương sai số dự báo.',formula:'RMSE = sqrt(mean((y-ŷ)^2))',read:'Phạt sai số lớn mạnh hơn MAE; càng thấp càng tốt khi so trên cùng thang đo.',source:'system'},
 mae:{name:'MAE',aliases:['mae'],text:'MAE là trung bình trị tuyệt đối sai số dự báo.',formula:'MAE = mean(|y-ŷ|)',read:'Dễ diễn giải theo cùng đơn vị với biến mục tiêu; càng thấp càng tốt.',source:'system'},
 mape:{name:'MAPE',aliases:['mape'],text:'MAPE là trung bình phần trăm sai số tuyệt đối.',formula:'MAPE = mean(|(y-ŷ)/y|)×100%',read:'Dễ đọc theo %, nhưng không ổn khi y gần 0.',source:'system'}
};
function conceptKey(question){
 const s=norm(question);let best=null,bestScore=0;
 for(const[key,d]of Object.entries(CONCEPTS)){for(const alias of [d.name,...(d.aliases||[])]){const a=norm(alias);if(!a)continue;let score=0;if(s===a)score=100+a.length;else if(s.includes(a))score=60+a.length;else{const tokens=a.split(' ').filter(x=>x.length>1),matched=tokens.filter(t=>s.includes(t)).length;score=tokens.length&&matched===tokens.length?20+matched*4:matched>=2?matched*3:0;}if(score>bestScore){best=key;bestScore=score;}}}
 return bestScore>=6?best:null;
}
function conceptCurrent(key,d,a,q,m){
 const t=m?.technical||null,quote=m?.quote||null;
 if(d.source==='technical'&&t){
  const map={sma:t.price?.sma,ema:t.price?.ema,rsi:t.rsi?.value,macd:t.macd?.value,supertrend:t.supertrend?.value,adx:t.adx?.value,volume:t.volume?.ratio20};
  if(Number.isFinite(map[key]))return key==='volume'?'Hiện tại '+num(map[key])+'x TB20.':'Hiện tại '+d.name+' = '+num(map[key])+'.';
  if(key==='meanreversion'&&t.rsi)return 'RSI hiện '+num(t.rsi.value)+' · '+t.rsi.state+'.';
 }
 if(key==='reference'&&quote&&Number.isFinite(quote.reference)&&Number.isFinite(quote.price))return 'Hiện tại: giá '+nf.format(quote.price)+' đ; phiên trước '+nf.format(quote.reference)+' đ; chênh '+(quote.price-quote.reference>0?'+':'')+nf.format(quote.price-quote.reference)+' đ ('+pct(quote.changePct)+').';
 if(key==='relativestrength'&&Number.isFinite(m?.driver?.relativeStrengthPct))return 'Hiện tại sức mạnh tương đối '+pct(m.driver.relativeStrengthPct)+'.';
 if(key==='driverscore'&&Number.isFinite(m?.driver?.score))return 'Điểm động lực hiện '+(m.driver.score>0?'+':'')+num(m.driver.score)+'/100.';
 if(a){if(key==='fcf'&&Number.isFinite(a.values.fcf))return 'FCF năm '+a.period+' = '+money(a.values.fcf)+'.';if(key==='ocf'&&Number.isFinite(a.values.ocf))return 'OCF năm '+a.period+' = '+money(a.values.ocf)+' · OCF/LNST '+num(a.ratios.ocfIncome)+'%.';if(key==='leverage'&&Number.isFinite(a.ratios.liabilitiesAssets))return 'Nợ phải trả/Tổng tài sản năm '+a.period+' = '+num(a.ratios.liabilitiesAssets)+'%.';if(key==='receivables'&&Number.isFinite(a.values.receivables))return 'Phải thu năm '+a.period+' = '+money(a.values.receivables)+' · thay đổi '+pct(a.change.receivables)+'.';if(key==='inventory'&&Number.isFinite(a.values.inventory))return 'Tồn kho năm '+a.period+' = '+money(a.values.inventory)+'.';if(d.metric&&Number.isFinite(a.ratios[d.metric]))return d.name+' năm '+a.period+' = '+num(a.ratios[d.metric])+(d.metric==='quick'?'x':'%')+'.';if(key==='revenue'&&Number.isFinite(a.values.revenue))return 'Doanh thu năm '+a.period+' = '+money(a.values.revenue)+' · tăng trưởng '+pct(a.change.revenue)+'.';if(key==='netprofit'&&Number.isFinite(a.values.profit))return 'LNST năm '+a.period+' = '+money(a.values.profit)+' · tăng trưởng '+pct(a.change.profit)+'.';}
 return '';
}
function conceptHTML(question,a,q,m){
 const key=conceptKey(question),d=CONCEPTS[key];if(!d)return'';
 const current=conceptCurrent(key,d,a,q,m),body=[
  section('Khái niệm',prose([d.text])),
  d.formula?section('Cách tính',prose([d.formula])):'',
  d.read?section('Cách đọc',prose([d.read])):'',
  current?section('Ngay trên '+state.symbol,prose([current])):''
 ].join('');
 return body;
}
function relatedConcepts(question){
 const terms=norm(question).split(' ').filter(x=>x.length>2);return Object.entries(CONCEPTS).map(([key,d])=>{const text=norm([d.name,...(d.aliases||[]),d.text,d.read||''].join(' ')),score=terms.reduce((s,t)=>s+(text.includes(t)?1:0),0);return{key,d,score};}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).slice(0,6);
}
function headlineList(items){if(!items?.length)return'';return section('Tin liên quan gần nhất',`<div class="analysis-news">${items.slice(0,5).map(n=>{const u=/^https?:\/\//.test(n.url||'')?n.url:'#';return`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`}).join('')}</div>`);}
function movementHTML(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q&&!d)return section('Biến động phiên','<div class="analysis-empty">Nguồn thị trường hiện tại không có snapshot cho mã này.</div>');
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
 if(!a)return section('Sức khỏe tài chính','<div class="analysis-empty">Nguồn hiện tại không có BCTC năm cho mã này.</div>');
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
 const signals=riskSignals(a,q);if(!signals.length)return section('Rủi ro định lượng','<div class="analysis-empty">Nguồn BCTC hiện tại không có đủ trường để tạo cảnh báo định lượng.</div>');
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
function searchHTML(question,annual,quarterly,m){
 const terms=norm(question).split(' ').filter(x=>x.length>2),datasets=[['Năm',annual],['Quý',quarterly]],hits=[];
 for(const [label,data] of datasets){if(!data)continue;for(const r of rows(data)){const n=norm(r.label),score=terms.reduce((a,t)=>a+(n.includes(t)?1:0),0);if(!score)continue;const ps=periods(data).slice(-8),vals=ps.filter(p=>Number.isFinite(val(r,p))).map(p=>`${p}: ${point(val(r,p),r.unit)}`);if(vals.length)hits.push({score,label,row:r,vals});}}
 hits.sort((a,b)=>b.score-a.score);
 const related=relatedConcepts(question);
 let out='';
 if(hits.length)out+=section('Dữ liệu khớp câu hỏi',`<div class="analysis-search-results">${hits.slice(0,12).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.label)}</span><p>${esc(h.vals.join(' · '))}</p></div>`).join('')}</div>`);
 if(related.length)out+=section('Khái niệm liên quan',`<div class="analysis-search-results">${related.map(x=>`<div><strong>${esc(x.d.name)}</strong><span>${esc(x.d.source||'FinQuery')}</span><p>${esc(x.d.text)}</p></div>`).join('')}</div>`);
 if(m?.technical)out+=section('Trạng thái kỹ thuật đang xem',prose(['Tín hiệu '+m.technical.label+' '+m.technical.confidence+'/100. '+m.technical.summary+'.']));
 return out||section('Phân tích câu hỏi',prose(['Câu hỏi này không khớp một trường dữ liệu cụ thể. Dolphin AI vẫn có thể phân tích nếu bạn nêu rõ biến, chỉ báo, kỳ thời gian hoặc phần màn hình đang hỏi.']));
}
function macroDatasetFor(question,macro){if(!macro?.datasets)return null;const s=norm(question),id=/\bpmi\b/.test(s)?'pmi':/\bfdi\b/.test(s)?'fdi':/gdp/.test(s)?'gdp_growth':/cung tien|m2|money supply/.test(s)?'money_supply':/tin dung|credit/.test(s)?'credit_sector':'macro_overview';return macro.datasets[id]?{id,...macro.datasets[id]}:null;}
function macroNews(question,items){const terms=norm(question).split(' ').filter(x=>x.length>2&&!['tai','sao','giam','tang','nhu','the','nao','hien','nay'].includes(x));return(items||[]).map(n=>{const s=norm(n.title),score=terms.reduce((a,t)=>a+(s.includes(t)?1:0),0);return{...n,score};}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||Date.parse(b.publishedAt)-Date.parse(a.publishedAt)).slice(0,5);}
function macroHTML(question,m){
 const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro),matched=macroNews(question,m.marketNews||[]),paragraphs=[];
 if(ds){const rs=ds.rows||[],last=rs.at(-1),prev=rs.at(-2),numeric=ds.numericColumns||[];const tokens=norm(question).split(' '),chosen=numeric.find(k=>tokens.some(t=>t.length>2&&norm(k).includes(t)))||numeric[0];if(last&&chosen&&typeof last[chosen]==='number'){let sentence='VBMA gần nhất: '+chosen+' = '+num(last[chosen])+'.';if(prev&&typeof prev[chosen]==='number'&&prev[chosen]!==0){const change=(last[chosen]/prev[chosen]-1)*100;sentence+=' So với điểm liền trước: '+pct(change)+'.';}paragraphs.push(sentence);}}
 if(matched.length){const first=matched[0];paragraphs.push('Catalyst vĩ mô phù hợp nhất với câu hỏi: “'+first.title+'” ('+(first.source||'nguồn báo chí')+'). Dolphin AI xếp sự kiện này vào bối cảnh ưu tiên vì nội dung khớp trực tiếp với các từ khóa và biến đang hỏi.');if(matched[1])paragraphs.push('Bối cảnh bổ sung: “'+matched[1].title+'”. Khi đọc chuỗi thời gian, ưu tiên thứ tự: trạng thái trước sự kiện → hành động chính sách/thị trường → phản ứng lãi suất/thanh khoản/giá sau đó.');}
 else if(ds)paragraphs.push('Dữ liệu định lượng ở trên là trục chính để đọc câu hỏi; phần tin tức hiện không có bài nào khớp mạnh hơn dữ liệu VBMA.');
 let sources='';if(matched.length)sources=section('Tin thị trường liên quan',`<div class="analysis-news">${matched.map(n=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`).join('')}</div>`);
 return prose(paragraphs)+sources;
}
function classify(q){
 const s=norm(q),ck=conceptKey(q);
 if(ck)return'concept';
 if(/nhnn|ngan hang nha nuoc|lai suat|overnight|\bon\b|omo|thanh khoan|ty gia|lam phat|\bgdp\b|\bpmi\b|\bfdi\b|cung tien|m2|tin dung|vi mo/.test(s))return'macro';
 if(/vi sao|nguyen nhan|tang|giam|bien dong|phien|gia co phieu|dong luc|ky thuat|tin hieu/.test(s))return'movement';
 if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';
 if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';
 if(/suc khoe|tai chinh|tong quan|doanh thu|loi nhuan|dong tien|no|tai san|von chu/.test(s))return'financial';
 return'search';
}
function analyze(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 const ctx={quote:m.quote||null,driver:m.driver||null,technical:m.technical||null,history:m.history||null,news:m.news||[],marketNews:m.marketNews||[]};
 const body=type==='macro'?macroHTML(question,m):type==='movement'?movementHTML(ctx):type==='concept'?conceptHTML(question,a,q,m):type==='financial'?financialHTML(a,q):type==='risk'?riskHTML(a,q):type==='compare'?comparisonHTML(a,q):searchHTML(question,annual,quarterly,m);
 return{type,html:body||section('Kết quả',prose(['Nguồn hiện tại không có giá trị phù hợp cho câu hỏi này.']))};
}
function addUser(text){const box=$('research-ai-messages');if(!box)return;const a=document.createElement('article');a.className='research-ai-message user';a.innerHTML=`<strong>Câu hỏi</strong><p>${esc(text)}</p>`;box.append(a);}
function addAnalysis(result){const box=$('research-ai-messages');if(!box)return;const a=document.createElement('article');a.className='research-ai-message assistant analysis-result';a.innerHTML=result.html;box.append(a);box.scrollTop=box.scrollHeight;}
function openDrawer(){const drawer=$('research-ai'),fab=$('ai-fab');if(!drawer)return;drawer.hidden=false;drawer.classList.add('open');if(fab)fab.setAttribute('aria-expanded','true');setTimeout(()=>$('research-ai-question')?.focus(),80);}
function closeDrawer(){const drawer=$('research-ai'),fab=$('ai-fab');if(!drawer)return;drawer.classList.remove('open');drawer.hidden=true;if(fab)fab.setAttribute('aria-expanded','false');}
function ask(question){const q=String(question||'').trim();if(!q)return;openDrawer();addUser(q);addAnalysis(analyze(q));}
function sync(symbol){state.symbol=symbol||'';const title=$('research-ai-title'),sub=$('research-ai-subtitle'),fab=$('ai-fab');if(title)title.textContent=`Phân tích chuyên sâu · ${state.symbol||'VN100'}`;if(sub)sub.textContent=`Đọc BCTC, giá, kỹ thuật và tin thị trường cho ${state.symbol||'VN100'} bằng dữ liệu FinQuery hiện có.`;if(fab)fab.dataset.symbol=state.symbol||'VN100';}
window.FinQueryAI={sync,ask,analyze,open:openDrawer,close:closeDrawer};
const form=$('research-ai-form'),input=$('research-ai-question');form?.addEventListener('submit',e=>{e.preventDefault();const q=input.value.trim();if(q){input.value='';ask(q);}});document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.aiPrompt||'')));
$('ai-fab')?.addEventListener('click',()=>{if($('research-ai')?.hidden)openDrawer();else closeDrawer();});$('ai-close')?.addEventListener('click',closeDrawer);document.querySelector('a[href="#research-ai"]')?.addEventListener('click',e=>{e.preventDefault();openDrawer();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('research-ai')?.hidden)closeDrawer();});
sync(window.FinancialMarket?.context?.().symbol||new URLSearchParams(location.search).get('symbol')||'MBB');
})();