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
function trendTag(n,positive=true){if(!Number.isFinite(n))return{label:'Không có số liệu kỳ này',tone:'neutral'};const good=positive?n>0:n<0;return{label:good?'Tích cực':n===0?'Đi ngang':'Cần theo dõi',tone:good?'positive':n===0?'neutral':'negative'};}

function card(label,value,sub='',t='neutral'){return`<div class="analysis-kpi"><span>${esc(label)}</span><strong class="${esc(t)}">${esc(value)}</strong>${sub?`<small>${esc(sub)}</small>`:''}</div>`;}
function table(rows){return`<div class="analysis-table">${rows.map(r=>`<div class="analysis-table-row"><span>${esc(r[0])}</span><b>${esc(r[1])}</b><em class="${esc(r[3]||'neutral')}">${esc(r[2]||'')}</em></div>`).join('')}</div>`;}
function section(title,body){return`<section class="analysis-block"><h4>${esc(title)}</h4>${body}</section>`;}
function prose(items){const parts=(items||[]).filter(Boolean);return parts.length?'<div class="analysis-narrative">'+parts.map(x=>'<p>'+esc(x)+'</p>').join('')+'</div>':'';}
function relationText(value,positive='tăng',negative='giảm'){if(!Number.isFinite(value))return'không có số liệu so sánh';if(Math.abs(value)<.15)return'gần như đi ngang';return value>0?positive+' '+num(Math.abs(value))+'%':negative+' '+num(Math.abs(value))+'%';}
function movementNarrative(ctx){
 const q=ctx.quote,d=ctx.driver;if(!q)return[];
 const ch=Number(q.changePct),dir=ch>0?'tăng':ch<0?'giảm':'đi ngang',rel=Number(d?.relativeStrengthPct),vol=Number(d?.volumeRatio20),mom=Number(d?.momentum5dPct),top=(d?.factors||[]).slice(0,3),headline=(ctx.news||[])[0],out=[];
 let first=state.symbol+' '+dir+' '+num(Math.abs(ch||0))+'% so với giá tham chiếu '+(Number.isFinite(q.reference)?nf.format(q.reference)+' đ':'của phiên trước')+', tương ứng '+(Number.isFinite(q.price)&&Number.isFinite(q.reference)?(q.price-q.reference>0?'+':'')+nf.format(q.price-q.reference)+' đ':'mức thay đổi hiện tại')+'.';
 if(Number.isFinite(rel))first+=' Sức mạnh tương đối '+(rel>=0?'dương '+num(rel)+' điểm %':'âm '+num(Math.abs(rel))+' điểm %')+' so với trung vị VN100, cho thấy '+(rel>=1?'cổ phiếu đang vận động mạnh hơn mặt bằng thị trường':rel<=-1?'cổ phiếu đang yếu hơn mặt bằng thị trường':'biến động khá sát nhịp chung')+'.';
 out.push(first);
 if(d){let second='Động lượng 5 phiên '+relationText(mom)+'. Thanh khoản đạt '+num(vol)+' lần bình quân 20 phiên'+(vol>=1.5?', tức dòng tiền đang hoạt động mạnh':vol>=.9?', ở vùng bình thường':' và đang thấp hơn nền giao dịch thông thường')+'.';if(top.length)second+=' Cụm tác động lớn nhất hiện là '+top.map(x=>x.label.toLowerCase()+' '+(x.contribution>0?'+':'')+num(x.contribution)).join(', ')+'.';out.push(second);}
 if(headline){out.push('Catalyst gần nhất là “'+headline.title+'” từ '+(headline.source||'nguồn báo chí')+'. Tin này được đọc cùng hướng giá, sức mạnh tương đối và thanh khoản: khi các biến trên cùng nghiêng một phía, tác động của catalyst lên diễn biến phiên được đánh giá mạnh hơn; khi chúng phân kỳ, yếu tố thị trường hoặc kỹ thuật đang chi phối nhiều hơn.');}
 else out.push('Diễn biến hiện được dẫn dắt chủ yếu bởi trạng thái thị trường, sức mạnh tương đối, động lượng và thanh khoản của chính mã; chưa có catalyst doanh nghiệp mới nổi bật trong luồng tin đang tải.');
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
 if(watch.length)return['Rủi ro hiện tập trung ở '+watch.map(x=>x.title.toLowerCase()).join(', ')+'. Đây là các biến cần theo dõi sát ở kỳ kế tiếp vì chúng đang lệch khỏi vùng thuận lợi.'];
 return['Bộ chỉ tiêu rủi ro cốt lõi đang ở trạng thái ổn định: dòng tiền, đòn bẩy và vốn lưu động chưa cho thấy điểm căng nổi bật trong kỳ hiện tại.'];
}
function compareNarrative(a,q){
 const out=[];if(a)out.push('So với '+a.previous+', năm '+a.period+' ghi nhận doanh thu '+relationText(a.change.revenue)+' và lợi nhuận sau thuế '+relationText(a.change.profit)+'; tổng tài sản '+relationText(a.change.assets)+' và vốn chủ sở hữu '+relationText(a.change.equity)+'.');
 if(q)out.push('Quý '+q.period+' cho thấy doanh thu '+relationText(q.qoq.revenue)+' so với quý trước và '+relationText(q.yoyChange.revenue)+' so với cùng kỳ; lợi nhuận '+relationText(q.qoq.profit)+' QoQ và '+relationText(q.yoyChange.profit)+' YoY.');
 return out;
}
const CONCEPTS={
 roe:{name:'ROE',aliases:['roe','return on equity'],text:'ROE đo mức lợi nhuận tạo ra trên vốn chủ sở hữu bình quân. Khi ROE tăng cùng biên lợi nhuận và dòng tiền kinh doanh, chất lượng sinh lời thường tốt hơn; nếu ROE tăng chủ yếu do vốn chủ mỏng hoặc nợ cao, cần đọc thêm đòn bẩy.',key:'roe'},
 roa:{name:'ROA',aliases:['roa','return on assets'],text:'ROA đo lợi nhuận tạo ra trên tổng tài sản bình quân. Chỉ số này phản ánh hiệu quả khai thác toàn bộ tài sản và hữu ích khi so sánh các doanh nghiệp có cấu trúc vốn khác nhau.',key:'roa'},
 fcf:{name:'FCF',aliases:['fcf','free cash flow','dong tien tu do'],text:'FCF là dòng tiền còn lại sau khi dòng tiền từ hoạt động kinh doanh trang trải chi đầu tư dài hạn. FCF dương và ổn định tạo dư địa trả nợ, cổ tức, mua lại cổ phiếu hoặc tái đầu tư.',key:null},
 ocf:{name:'OCF',aliases:['ocf','operating cash flow','dong tien hoat dong kinh doanh','dong tien hd'],text:'OCF là dòng tiền thuần từ hoạt động kinh doanh. So OCF với lợi nhuận sau thuế giúp kiểm tra khả năng chuyển lợi nhuận kế toán thành tiền thực.',key:null},
 grossmargin:{name:'Biên lợi nhuận gộp',aliases:['bien loi nhuan gop','gross margin','bien gop'],text:'Biên lợi nhuận gộp là phần doanh thu còn lại sau giá vốn. Biên tăng thường đến từ giá bán, cơ cấu sản phẩm hoặc chi phí đầu vào thuận lợi hơn.',key:'grossMargin'},
 netmargin:{name:'Biên lợi nhuận ròng',aliases:['bien loi nhuan rong','net margin','bien rong'],text:'Biên lợi nhuận ròng là tỷ lệ lợi nhuận sau thuế trên doanh thu. Nó phản ánh hiệu quả tổng hợp sau giá vốn, chi phí vận hành, tài chính và thuế.',key:'netMargin'},
 leverage:{name:'Đòn bẩy tài chính',aliases:['don bay','leverage','no tren tai san','no tren von'],text:'Đòn bẩy tài chính mô tả mức sử dụng nợ để tài trợ tài sản. Đòn bẩy làm tăng độ nhạy của lợi nhuận và dòng tiền với lãi suất, chu kỳ kinh doanh và khả năng tái cấp vốn.',key:'liabilitiesAssets'},
 receivables:{name:'Khoản phải thu',aliases:['phai thu','receivables'],text:'Khoản phải thu là phần doanh thu hoặc nghĩa vụ khách hàng chưa chuyển thành tiền. Tốc độ tăng phải thu so với doanh thu cho biết áp lực vốn lưu động và chất lượng thu tiền.',key:null},
 inventory:{name:'Hàng tồn kho',aliases:['ton kho','inventory'],text:'Hàng tồn kho là nguyên vật liệu, hàng hóa hoặc thành phẩm chưa được tiêu thụ. Tăng tồn kho có thể phục vụ mở rộng nhưng cũng làm vốn bị giam nếu tốc độ bán không theo kịp.',key:null},
 sma:{name:'SMA',aliases:['sma','simple moving average'],text:'SMA là giá đóng cửa trung bình của một số phiên cố định. Giá nằm trên SMA và SMA dốc lên thường phản ánh xu hướng tăng; cắt qua SMA là tín hiệu thay đổi trạng thái xu hướng.',technical:true},
 ema:{name:'EMA',aliases:['ema','exponential moving average'],text:'EMA là đường trung bình ưu tiên trọng số cho dữ liệu mới, phản ứng nhanh hơn SMA. EMA ngắn nằm trên EMA dài thường thể hiện động lượng tăng.',technical:true},
 wma:{name:'WMA',aliases:['wma','weighted moving average'],text:'WMA là trung bình động có trọng số tuyến tính, đặt trọng số lớn hơn cho các phiên gần nhất nên nhạy hơn SMA.',technical:true},
 vwma:{name:'VWMA',aliases:['vwma','volume weighted moving average'],text:'VWMA là trung bình giá có trọng số theo khối lượng. Giá vượt VWMA trong lúc khối lượng tăng thường cho thấy lực cầu có chất lượng tốt hơn một cú vượt chỉ dựa trên giá.',technical:true},
 rsi:{name:'RSI',aliases:['rsi','relative strength index'],text:'RSI đo động lượng trên thang 0–100. Dưới 30 thường là vùng quá bán, trên 70 là quá mua; vùng 45–55 trung tính. Mean reversion đáng chú ý khi RSI rời vùng cực trị đồng thời giá quay lại bên trong Bollinger hoặc lấy lại đường trung bình.',technical:true},
 macd:{name:'MACD',aliases:['macd','moving average convergence divergence'],text:'MACD đo chênh lệch giữa hai EMA. MACD cắt lên Signal thể hiện động lượng tăng cải thiện; histogram mở rộng cùng hướng cho thấy xung lực đang mạnh thêm.',technical:true},
 bollinger:{name:'Bollinger Bands',aliases:['bollinger','bollinger bands','bbands'],text:'Bollinger Bands gồm đường giữa và hai dải theo độ lệch chuẩn. Chạm dải ngoài phản ánh giá lệch xa trung bình; quay trở lại bên trong dải sau trạng thái quá mua/quá bán là tín hiệu mean reversion thường dùng.',technical:true},
 supertrend:{name:'Supertrend',aliases:['supertrend'],text:'Supertrend dùng ATR để xác định trạng thái xu hướng. Giá nằm trên đường Supertrend tương ứng trạng thái tăng; chuyển xuống dưới tương ứng trạng thái giảm.',technical:true},
 atr:{name:'ATR',aliases:['atr','average true range'],text:'ATR đo biên độ dao động tuyệt đối, không chỉ hướng. ATR tăng nghĩa là biến động đang mở rộng; ATR giảm nghĩa là biên độ đang co lại.',technical:true},
 adx:{name:'ADX',aliases:['adx','average directional index'],text:'ADX đo sức mạnh xu hướng. ADX trên khoảng 25 thường cho thấy xu hướng đã đủ rõ; hướng tăng hay giảm phải đọc cùng giá, MACD, DI hoặc Supertrend.',technical:true},
 stochastic:{name:'Stochastic',aliases:['stochastic','stoch'],text:'Stochastic đo vị trí giá đóng cửa trong biên cao–thấp gần đây. Vượt lên từ vùng dưới 20 thường hỗ trợ kịch bản hồi; đi xuống từ trên 80 thường cảnh báo động lượng nóng suy yếu.',technical:true},
 cci:{name:'CCI',aliases:['cci','commodity channel index'],text:'CCI đo mức lệch của giá so với trung bình thống kê. Trên +100 phản ánh động lượng mạnh lên, dưới -100 phản ánh áp lực giảm mạnh.',technical:true},
 roc:{name:'ROC',aliases:['roc','rate of change'],text:'ROC đo phần trăm thay đổi giá so với N phiên trước. ROC dương và tăng thể hiện động lượng tăng đang mở rộng; âm và giảm thể hiện động lượng giảm.',technical:true},
 willr:{name:'Williams %R',aliases:['williams r','williams %r','willr'],text:'Williams %R đo vị trí giá trong biên N phiên trên thang -100 đến 0. Dưới -80 là vùng quá bán, trên -20 là vùng quá mua.',technical:true},
 obv:{name:'OBV',aliases:['obv','on balance volume'],text:'OBV cộng hoặc trừ khối lượng theo hướng tăng giảm của giá. OBV đi cùng hướng giá củng cố xu hướng; phân kỳ giữa OBV và giá là tín hiệu cần chú ý.',technical:true},
 mfi:{name:'MFI',aliases:['mfi','money flow index'],text:'MFI kết hợp giá và khối lượng để đo áp lực dòng tiền. Trên 80 thường là vùng nóng, dưới 20 là vùng yếu; thoát khỏi vùng cực trị hỗ trợ tín hiệu mean reversion.',technical:true},
 cmf:{name:'CMF',aliases:['cmf','chaikin money flow'],text:'CMF đo dòng tiền tích lũy/phân phối từ vị trí đóng cửa và khối lượng. CMF trên 0 thiên về tích lũy, dưới 0 thiên về phân phối.',technical:true},
 volume:{name:'Khối lượng',aliases:['khoi luong','volume','kl tb20'],text:'Khối lượng cho biết mức độ tham gia của dòng tiền. So với trung bình 20 phiên giúp phân biệt một biến động có lực giao dịch mạnh hay chỉ diễn ra trên thanh khoản mỏng.',technical:true},
 reference:{name:'Giá tham chiếu',aliases:['gia tham chieu','tham chieu','reference price','gia phien truoc'],text:'Giá tham chiếu trên bảng giá là mức dùng để tính thay đổi phần trăm trong phiên; với cổ phiếu niêm yết thông thường đây là giá đóng cửa của phiên giao dịch trước.',market:true},
 relativestrength:{name:'Sức mạnh tương đối',aliases:['suc manh tuong doi','relative strength'],text:'Sức mạnh tương đối trong FinQuery là chênh lệch biến động của mã so với trung vị VN100 tại cùng snapshot. Giá trị dương nghĩa là mã mạnh hơn mặt bằng, âm nghĩa là yếu hơn.',market:true},
 volatility:{name:'Biến động 20 phiên',aliases:['bien dong 20 phien','volatility','do bien dong'],text:'Biến động 20 phiên đo độ phân tán của lợi suất gần đây. Mức cao nghĩa là biên dao động lớn và rủi ro ngắn hạn cao hơn.',market:true},
 gdp:{name:'GDP',aliases:['gdp','tong san pham trong nuoc'],text:'GDP đo giá trị gia tăng của nền kinh tế. Tăng trưởng GDP ảnh hưởng đến kỳ vọng doanh thu, lợi nhuận doanh nghiệp và khẩu vị rủi ro của thị trường.',macro:true},
 pmi:{name:'PMI',aliases:['pmi','purchasing managers index'],text:'PMI là chỉ số nhà quản trị mua hàng. Trên 50 thường thể hiện khu vực sản xuất mở rộng, dưới 50 thể hiện thu hẹp.',macro:true},
 m2:{name:'M2 / tổng cung tiền',aliases:['m2','cung tien','tong cung tien','money supply'],text:'M2 phản ánh lượng tiền rộng trong nền kinh tế. Tăng trưởng cung tiền ảnh hưởng đến thanh khoản hệ thống, tín dụng, lãi suất và định giá tài sản.',macro:true},
 credit:{name:'Tín dụng',aliases:['tin dung','credit growth','du no tin dung'],text:'Tín dụng phản ánh quy mô vốn ngân hàng cung cấp cho nền kinh tế. Tăng trưởng tín dụng cao hỗ trợ hoạt động kinh tế nhưng cũng cần đọc cùng chất lượng tài sản và lạm phát.',macro:true},
 fdi:{name:'FDI',aliases:['fdi','dau tu truc tiep nuoc ngoai'],text:'FDI là vốn đầu tư trực tiếp nước ngoài. Dòng FDI phản ánh sức hút sản xuất, công nghiệp và chuỗi cung ứng, đồng thời tác động đến ngoại tệ, việc làm và đầu tư.',macro:true},
 omo:{name:'OMO',aliases:['omo','thi truong mo','open market operations'],text:'OMO là nghiệp vụ thị trường mở của NHNN. Bơm ròng làm tăng thanh khoản VND ngắn hạn; hút ròng rút bớt phần thanh khoản dư. Tác động lên lãi suất liên ngân hàng phụ thuộc trạng thái cung–cầu vốn trước thời điểm điều tiết.',macro:true},
 overnight:{name:'Lãi suất ON',aliases:['lai suat on','overnight','lai suat qua dem'],text:'Lãi suất ON là lãi suất vay qua đêm trên thị trường liên ngân hàng. Nó phản ứng rất nhanh với trạng thái thiếu hoặc dư VND cục bộ và hoạt động điều tiết của NHNN.',macro:true},
 nhnn:{name:'NHNN',aliases:['nhnn','ngan hang nha nuoc'],text:'NHNN điều hành thanh khoản, lãi suất, tỷ giá và tín dụng thông qua nhiều công cụ như OMO, tín phiếu, tái cấp vốn, dự trữ bắt buộc và can thiệp ngoại hối.',macro:true},
 cpi:{name:'CPI / lạm phát',aliases:['cpi','lam phat','inflation'],text:'CPI đo biến động mặt bằng giá tiêu dùng. Lạm phát cao làm giảm dư địa nới lỏng tiền tệ và thường gây áp lực lên lãi suất danh nghĩa, chi phí vốn và định giá.',macro:true},
 fx:{name:'Tỷ giá',aliases:['ty gia','usd vnd','fx'],text:'Tỷ giá USD/VND phản ánh tương quan cung cầu ngoại tệ. Biến động tỷ giá ảnh hưởng đến doanh nghiệp xuất nhập khẩu, nợ ngoại tệ, lạm phát nhập khẩu và chính sách tiền tệ.',macro:true},
 meanreversion:{name:'Mean reversion',aliases:['mean reversion','hoi ve trung binh','quay ve trung binh'],text:'Mean reversion là trạng thái giá có xu hướng quay lại vùng trung bình sau khi lệch quá xa. Trong FinQuery, tín hiệu được đọc mạnh hơn khi RSI rời vùng quá mua/quá bán và giá quay trở lại bên trong Bollinger hoặc lấy lại đường trung bình.',technical:true},
 eps:{name:'EPS',aliases:['eps','earnings per share','lai tren co phieu'],text:'EPS là lợi nhuận thuộc về cổ đông phổ thông chia cho số cổ phiếu bình quân lưu hành. EPS tăng bền vững là nền tảng quan trọng cho tăng trưởng giá trị doanh nghiệp.',financial:true},
 pe:{name:'P/E',aliases:['p e','pe','price earnings'],text:'P/E là giá thị trường trên lợi nhuận mỗi cổ phiếu. P/E cao thường phản ánh kỳ vọng tăng trưởng cao hơn hoặc mức định giá đắt hơn so với lợi nhuận hiện tại; cần so với lịch sử và doanh nghiệp cùng ngành.',financial:true},
 pb:{name:'P/B',aliases:['p b','pb','price book'],text:'P/B là giá thị trường trên giá trị sổ sách mỗi cổ phiếu. Chỉ số này đặc biệt hữu ích với ngân hàng, bảo hiểm và doanh nghiệp có tài sản hữu hình lớn.',financial:true},
 ebitda:{name:'EBITDA',aliases:['ebitda'],text:'EBITDA là lợi nhuận trước lãi vay, thuế và khấu hao. Nó giúp quan sát hiệu quả hoạt động trước cấu trúc vốn và chính sách khấu hao, nhưng không thay thế dòng tiền.',financial:true},
 ebit:{name:'EBIT',aliases:['ebit'],text:'EBIT là lợi nhuận trước lãi vay và thuế. EBIT phản ánh sức sinh lời từ hoạt động trước tác động của cấu trúc tài trợ và thuế.',financial:true},
 currentratio:{name:'Current ratio',aliases:['current ratio','he so thanh toan hien hanh'],text:'Current ratio là tài sản ngắn hạn chia nợ ngắn hạn. Mức lớn hơn 1 thường cho thấy tài sản ngắn hạn bao phủ nợ ngắn hạn, nhưng chất lượng còn phụ thuộc vào phải thu và tồn kho.',financial:true},
 quickratio:{name:'Quick ratio',aliases:['quick ratio','he so thanh toan nhanh'],text:'Quick ratio đo khả năng thanh toán ngắn hạn sau khi loại phần tồn kho kém thanh khoản hơn. Chỉ số này hữu ích để đánh giá áp lực tiền mặt ngắn hạn.',financial:true},
 yoy:{name:'YoY',aliases:['yoy','year over year','cung ky'],text:'YoY là so sánh với cùng kỳ năm trước. Cách so này loại bớt yếu tố mùa vụ và phù hợp để đánh giá tốc độ tăng trưởng theo năm.',financial:true},
 qoq:{name:'QoQ',aliases:['qoq','quarter over quarter','quy truoc'],text:'QoQ là so sánh với quý liền trước. Chỉ số này phản ánh thay đổi ngắn hạn nhưng có thể chịu ảnh hưởng mùa vụ.',financial:true},
 cagr:{name:'CAGR',aliases:['cagr','compound annual growth rate'],text:'CAGR là tốc độ tăng trưởng kép bình quân năm giữa hai mốc thời gian. Nó hữu ích để tóm tắt xu hướng dài hạn nhưng không thể hiện độ biến động từng năm.',financial:true}
};
function conceptKey(question){const s=norm(question);let best=null,bestLen=0;for(const[key,d]of Object.entries(CONCEPTS)){for(const alias of d.aliases||[]){const a=norm(alias);if(a&&s.includes(a)&&a.length>bestLen){best=key;bestLen=a.length;}}}return best;}
function metricDefinition(row){
 const label=String(row?.label||''),s=norm(label);
 if(/tai san ngan han/.test(s))return label+' là nhóm tài sản dự kiến chuyển thành tiền, bán hoặc sử dụng trong chu kỳ kinh doanh ngắn hạn; thường gồm tiền, phải thu, tồn kho và đầu tư ngắn hạn.';
 if(/tong.*tai san|tong cong tai san/.test(s))return label+' là tổng nguồn lực kinh tế doanh nghiệp kiểm soát tại thời điểm báo cáo, bằng tổng nợ phải trả cộng vốn chủ sở hữu.';
 if(/no phai tra|tong no/.test(s))return label+' là nghĩa vụ hiện tại doanh nghiệp phải thanh toán cho chủ nợ, nhà cung cấp, người lao động, cơ quan thuế hoặc bên cho vay.';
 if(/von chu so huu/.test(s))return label+' là phần giá trị thuộc về cổ đông sau khi lấy tổng tài sản trừ tổng nợ phải trả.';
 if(/doanh thu|thu nhap/.test(s))return label+' phản ánh quy mô thu nhập ghi nhận trong kỳ theo hoạt động tương ứng; khi phân tích cần đọc cùng biên lợi nhuận, phải thu và dòng tiền.';
 if(/loi nhuan|lai lo/.test(s))return label+' phản ánh phần kết quả còn lại sau các nhóm doanh thu và chi phí liên quan; chất lượng lợi nhuận nên đọc cùng OCF và các khoản bất thường.';
 if(/chi phi/.test(s))return label+' là khoản làm giảm lợi ích kinh tế trong kỳ. Tốc độ tăng chi phí so với doanh thu cho biết mức độ co giãn của biên lợi nhuận.';
 if(/phai thu/.test(s))return label+' là giá trị doanh nghiệp có quyền thu từ khách hàng hoặc đối tác. Tăng nhanh hơn doanh thu thường làm vốn lưu động bị chiếm dụng nhiều hơn.';
 if(/ton kho/.test(s))return label+' là hàng hóa, nguyên vật liệu hoặc sản phẩm chưa được tiêu thụ. Xu hướng tồn kho cần đọc cùng doanh thu, giá vốn và vòng quay.';
 if(/tien va tuong duong tien|tien mat/.test(s))return label+' phản ánh nguồn tiền có tính thanh khoản cao, dùng để đáp ứng nghĩa vụ ngắn hạn và nhu cầu vận hành.';
 if(/du phong/.test(s))return label+' là khoản điều chỉnh kế toán cho tổn thất hoặc nghĩa vụ ước tính. Số âm thường thể hiện khoản dự phòng được khấu trừ khỏi giá trị tài sản liên quan.';
 if(/khau hao/.test(s))return label+' là phần giá trị tài sản cố định được phân bổ vào chi phí qua thời gian sử dụng; đây là chi phí phi tiền mặt ở thời điểm ghi nhận.';
 if(/luu chuyen|dong tien/.test(s))return label+' phản ánh dòng tiền thực thu hoặc thực chi của nhóm hoạt động tương ứng, giúp kiểm tra khả năng chuyển lợi nhuận kế toán thành tiền.';
 return label+' là một chỉ tiêu được lấy trực tiếp từ bộ báo cáo tài chính của doanh nghiệp. Giá trị nên được đọc theo chuỗi nhiều kỳ và cùng các chỉ tiêu liên quan thay vì chỉ nhìn một mốc đơn lẻ.';
}
function localMetricHit(question,data){if(!data)return null;const s=norm(question),terms=s.split(' ').filter(x=>x.length>2);let best=null;for(const r of rows(data)){const label=norm(r.label),score=terms.reduce((sum,t)=>sum+(label.includes(t)?1:0),0);if(score&&(best===null||score>best.score))best={score,row:r};}return best;}
function technicalNarrative(t,key){
 if(!t?.values)return[];
 const v=t.values,b=t.bar||{},r=t.regime||{},parts=[];
 const one=(name,value,detail)=>Number.isFinite(value)?name+' '+num(value)+(detail||''):null;
 if(key==='rsi'||!key)parts.push(Number.isFinite(v.rsi)?'RSI '+num(v.rsi)+(v.rsi>=70?' đang ở vùng quá mua':v.rsi<=30?' đang ở vùng quá bán':v.rsi>=55?' đang ở vùng động lượng tích cực':v.rsi<=45?' đang ở vùng động lượng yếu':' đang ở vùng trung tính')+'.':null);
 if(key==='macd'||!key)parts.push(Number.isFinite(v.macd)&&Number.isFinite(v.signal)?'MACD '+num(v.macd)+' '+(v.macd>v.signal?'đứng trên':'đứng dưới')+' Signal '+num(v.signal)+', histogram '+num(v.hist)+(v.hist>0?' dương':' âm')+'.':null);
 if(['sma','ema','wma','vwma'].includes(key)||!key){const line=key&&Number.isFinite(v[key])?v[key]:v.sma;if(Number.isFinite(line)&&Number.isFinite(b.close))parts.push('Giá '+nf.format(b.close)+' đ đang '+(b.close>=line?'trên':'dưới')+' '+(key?CONCEPTS[key]?.name:'SMA')+' '+nf.format(line)+' đ.');}
 if(key==='bollinger'||key==='meanreversion'||!key){if(Number.isFinite(v.lower)&&Number.isFinite(v.upper)&&Number.isFinite(b.close))parts.push('Bollinger: giá ở '+(b.close<v.lower?'ngoài dải dưới':b.close>v.upper?'ngoài dải trên':b.close>=v.middle?'nửa trên của dải':'nửa dưới của dải')+'. '+(r.detail?String(r.detail).split(' · ').find(x=>x.startsWith('Mean reversion'))||'':''));}
 if(key==='supertrend'||!key)parts.push(Number.isFinite(v.supertrendDir)?'Supertrend đang '+(v.supertrendDir>0?'TĂNG':'GIẢM')+(Number.isFinite(v.supertrend)?' tại '+nf.format(v.supertrend)+' đ':'')+'.':null);
 if(key==='adx'||!key)parts.push(Number.isFinite(v.adx)?'ADX '+num(v.adx)+(v.adx>=25?' xác nhận xu hướng đủ mạnh.':' cho thấy xu hướng còn yếu hoặc đang đi ngang.') :null);
 if(key==='stochastic'||!key)parts.push(Number.isFinite(v.stoch)?'Stochastic '+num(v.stoch)+(v.stoch>=80?' ở vùng cao.':v.stoch<=20?' ở vùng thấp.':' ở vùng trung tính.') :null);
 if(key==='mfi'||!key)parts.push(Number.isFinite(v.mfi)?'MFI '+num(v.mfi)+(v.mfi>=80?' cho thấy dòng tiền đang nóng.':v.mfi<=20?' cho thấy dòng tiền đang yếu.':' ở vùng cân bằng.') :null);
 if(key==='cmf'||!key)parts.push(Number.isFinite(v.cmf)?'CMF '+num(v.cmf)+(v.cmf>0?' nghiêng về tích lũy.':' nghiêng về phân phối.') :null);
 if(r.bias)parts.unshift('Khung '+t.timeframe+' hiện có thiên hướng '+r.bias+'.');
 return parts.filter(Boolean);
}
function conceptHTML(question,a,q,annual,quarterly){
 const key=conceptKey(question),d=key?CONCEPTS[key]:null;
 if(d){let current='',m=market();if(a){if(key==='fcf')current=' Với '+state.symbol+', FCF năm '+a.period+' ước tính '+money(a.values.fcf)+'.';else if(key==='ocf')current=' Với '+state.symbol+', OCF năm '+a.period+' là '+money(a.values.ocf)+', tương đương '+num(a.ratios.ocfIncome)+'% lợi nhuận sau thuế.';else if(key==='leverage')current=' Với '+state.symbol+', nợ phải trả tương đương '+num(a.ratios.liabilitiesAssets)+'% tổng tài sản.';else if(key==='receivables')current=' Với '+state.symbol+', phải thu năm '+a.period+' là '+money(a.values.receivables)+', thay đổi '+pct(a.change.receivables)+' so với năm trước.';else if(key==='inventory')current=' Với '+state.symbol+', tồn kho năm '+a.period+' là '+money(a.values.inventory)+'.';else if(d.key&&Number.isFinite(a.ratios[d.key]))current=' Với '+state.symbol+', '+d.name+' năm '+a.period+' là '+num(a.ratios[d.key])+'%.';}if(key==='reference'&&m.quote)current=' '+state.symbol+' hiện có giá tham chiếu '+nf.format(m.quote.reference)+' đ, giá hiện tại '+nf.format(m.quote.price)+' đ, chênh '+(m.quote.price-m.quote.reference>0?'+':'')+nf.format(m.quote.price-m.quote.reference)+' đ.';if(d.technical)return prose([d.text+current,...technicalNarrative(m.technical,key)])+movementHTML({quote:m.quote,driver:m.driver,technical:m.technical,news:m.news||[]});if(d.macro)return prose([d.text+current])+macroHTML(question,m);return prose([d.text+current])+financialHTML(a,q);}
 const qHit=localMetricHit(question,quarterly),aHit=localMetricHit(question,annual),hit=qHit||aHit;if(hit){const data=qHit?quarterly:annual,row=hit.row,ps=periods(data).slice(-6),vals=ps.filter(p=>Number.isFinite(val(row,p))).map(p=>p+': '+point(val(row,p),row.unit));return prose([metricDefinition(row)+' Với '+state.symbol+', chuỗi gần nhất là '+vals.join('; ')+'.'])+section('Chuỗi dữ liệu gần nhất',table(vals.map(x=>{const parts=x.split(': ');return[parts[0],parts.slice(1).join(': '),'','neutral']})));}
 return prose(['Câu hỏi đang chạm tới một khái niệm ngoài danh mục chuẩn của FinQuery. Hệ thống vẫn sẽ tìm trong toàn bộ tên chỉ tiêu BCTC, dữ liệu kỹ thuật, bảng giá và dữ liệu vĩ mô đang tải để trả lời theo dữ liệu thực tế.'])+searchHTML(question,annual,quarterly);
}
function headlineList(items){if(!items?.length)return'';return section('Tin liên quan gần nhất',`<div class="analysis-news">${items.slice(0,5).map(n=>{const u=/^https?:\/\//.test(n.url||'')?n.url:'#';return`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`}).join('')}</div>`);}
function movementHTML(ctx){
 const q=ctx.quote,d=ctx.driver,t=ctx.technical;if(!q&&!d)return section('Biến động phiên','<div class="analysis-empty">Snapshot thị trường của mã này đang được cập nhật.</div>');
 const kpis=[card('Giá',q?nf.format(q.price)+' đ':'—','Snapshot gần nhất'),card('Biến động',q?pct(q.changePct):'—','So với tham chiếu',tone(q?.changePct)),card('Điểm động lực',d?`${d.score>0?'+':''}${num(d.score)}/100`:'—',d?`Độ tin cậy ${num(d.confidenceScore)}/100`:'' ,tone(d?.score)),card('KL / TB20',d&&Number.isFinite(d.volumeRatio20)?num(d.volumeRatio20)+'x':'—','Mức hoạt động tương đối',d?.volumeRatio20>1?'positive':'neutral')].join('');
 const factors=(d?.factors||[]).map(f=>[f.label,`${f.contribution>0?'+':''}${num(f.contribution)}`,`w ${Math.round((f.weight||0)*100)}%`,tone(f.contribution)]);
 const details=d?table([
  ['Thị trường chung',pct(d.marketMedianChangePct),'Trung vị VN100',tone(d.marketMedianChangePct)],
  ['Sức mạnh tương đối',pct(d.relativeStrengthPct),'so với thị trường',tone(d.relativeStrengthPct)],
  ['Động lượng 5 phiên',pct(d.momentum5dPct),'xu hướng ngắn hạn',tone(d.momentum5dPct)],
  ['Biến động 20 phiên',Number.isFinite(d.volatility20dPct)?num(d.volatility20dPct)+'%':'—','độ lệch chuẩn','neutral'],
  ['Vị trí trong biên phiên',Number.isFinite(d.rangePositionPct)?num(d.rangePositionPct)+'%':'—','0% thấp · 100% cao','neutral']
 ]):'';
 const technical=t?section('Trạng thái kỹ thuật hiện tại',prose(technicalNarrative(t,null))):'';return`${prose(movementNarrative(ctx))}<div class="analysis-kpis">${kpis}</div>${technical}${factors.length?section('Phân rã động lực',table(factors)):''}${section('Bối cảnh định lượng',details)}${headlineList(ctx.news)}`;
}
function financialHTML(a,q){
 if(!a)return section('Sức khỏe tài chính','<div class="analysis-empty">Bộ dữ liệu hiện không có BCTC năm cho mã này.</div>');
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
 const signals=riskSignals(a,q);if(!signals.length)return section('Rủi ro định lượng','<div class="analysis-empty">Bộ dữ liệu hiện không có đủ trường để tính nhóm cảnh báo này.</div>');
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
 const stop=new Set(['tai','sao','nhu','the','nao','hien','nay','cua','cho','voi','mot','nhung','cac','bao','nhieu','gi','la']),terms=norm(question).split(' ').filter(x=>x.length>2&&!stop.has(x)),datasets=[['Năm',annual],['Quý',quarterly]],hits=[];
 for(const [label,data] of datasets){if(!data)continue;for(const r of rows(data)){const n=norm(r.label),score=terms.reduce((a,t)=>a+(n.includes(t)?1:0),0);if(!score)continue;const ps=periods(data).slice(-6),vals=ps.filter(p=>Number.isFinite(val(r,p))).map(p=>`${p}: ${point(val(r,p),r.unit)}`);if(vals.length)hits.push({score,label,row:r,vals});}}
 hits.sort((a,b)=>b.score-a.score);
 const m=market(),macro=window.FinMacro?.context?.(),macroHits=[];
 for(const ds of Object.values(macro?.datasets||{})){const cols=ds.columns||[],title=norm(ds.title),columnHits=cols.filter(col=>terms.some(t=>norm(col).includes(t)));const score=terms.reduce((a,t)=>a+(title.includes(t)?1:0),0)+columnHits.length;if(!score)continue;const last=(ds.rows||[]).at(-1)||{},selected=columnHits.length?columnHits.slice(0,5):(ds.numericColumns||[]).slice(0,5);macroHits.push({score,title:ds.title,values:selected.filter(k=>last[k]!==undefined).map(k=>k+': '+String(last[k]))});}
 macroHits.sort((a,b)=>b.score-a.score);
 const news=(m.marketNews||[]).map(n=>({n,score:terms.reduce((a,t)=>a+(norm(n.title).includes(t)?1:0),0)})).filter(x=>x.score).sort((a,b)=>b.score-a.score||Date.parse(b.n.publishedAt)-Date.parse(a.n.publishedAt)).slice(0,5);
 const blocks=[];
 if(hits.length)blocks.push(section('Chỉ tiêu BCTC liên quan',`<div class="analysis-search-results">${hits.slice(0,12).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.label)}</span><p>${esc(h.vals.join(' · '))}</p></div>`).join('')}</div>`));
 if(macroHits.length)blocks.push(section('Dữ liệu vĩ mô liên quan',`<div class="analysis-search-results">${macroHits.slice(0,6).map(h=>`<div><strong>${esc(h.title)}</strong><p>${esc(h.values.join(' · '))}</p></div>`).join('')}</div>`));
 if(news.length)blocks.push(section('Tin liên quan',`<div class="analysis-news">${news.map(({n})=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`).join('')}</div>`));
 if(blocks.length)return prose(['FinQuery đã rà toàn bộ dữ liệu doanh nghiệp, vĩ mô và luồng tin đang tải theo nội dung câu hỏi.'])+blocks.join('');
 return prose(['Câu hỏi này không khớp tên trường dữ liệu trực tiếp. Hãy diễn đạt theo đối tượng cần phân tích, ví dụ chỉ báo kỹ thuật, BCTC, lãi suất, NHNN, thanh khoản, tăng trưởng, định giá hoặc một chỉ tiêu cụ thể; FinQuery sẽ tự định tuyến sang phần dữ liệu tương ứng.']);
}
function macroDatasetFor(question,macro){if(!macro?.datasets)return null;const s=norm(question),id=/\bpmi\b/.test(s)?'pmi':/\bfdi\b/.test(s)?'fdi':/gdp/.test(s)?'gdp_growth':/cung tien|m2|money supply/.test(s)?'money_supply':/tin dung|credit/.test(s)?'credit_sector':'macro_overview';return macro.datasets[id]?{id,...macro.datasets[id]}:null;}
function macroNews(question,items){const terms=norm(question).split(' ').filter(x=>x.length>2&&!['tai','sao','giam','tang','nhu','the','nao','hien','nay'].includes(x));return(items||[]).map(n=>{const s=norm(n.title),score=terms.reduce((a,t)=>a+(s.includes(t)?1:0),0);return{...n,score};}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||Date.parse(b.publishedAt)-Date.parse(a.publishedAt)).slice(0,5);}
function macroHTML(question,m){
 const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro),matched=macroNews(question,m.marketNews||[]),paragraphs=[];
 if(ds){const rs=ds.rows||[],last=rs.at(-1),prev=rs.at(-2),numeric=ds.numericColumns||[];const chosen=numeric.find(k=>norm(question).split(' ').some(t=>t.length>2&&norm(k).includes(t)))||numeric[0];if(last&&chosen&&typeof last[chosen]==='number'){let sentence='Dữ liệu VBMA gần nhất ghi nhận '+chosen+' ở mức '+num(last[chosen])+'.';if(prev&&typeof prev[chosen]==='number'&&prev[chosen]!==0){const change=(last[chosen]/prev[chosen]-1)*100;sentence+=' So với kỳ liền trước, chỉ tiêu '+relationText(change)+'.';}paragraphs.push(sentence);}}
 if(matched.length){const first=matched[0];paragraphs.push('Tin nổi bật nhất liên quan câu hỏi là “'+first.title+'” từ '+(first.source||'nguồn chính thống')+'. FinQuery đặt sự kiện này vào đúng thứ tự thời gian của chuỗi dữ liệu: trạng thái thanh khoản/lãi suất trước sự kiện → hành động điều tiết → phản ứng của lãi suất, tỷ giá hoặc thị trường sau đó. Nhờ vậy phần giải thích tập trung vào cơ chế thay vì lặp lại tiêu đề tin.');if(matched[1])paragraphs.push('Tin bổ sung “'+matched[1].title+'” giúp xác định bối cảnh rộng hơn. Nếu hai nguồn cùng mô tả một hướng thay đổi của thanh khoản, lãi suất hoặc kỳ vọng chính sách, FinQuery ưu tiên cơ chế chung đó trong phần kết luận.');}
 else paragraphs.push('Phần vĩ mô được đọc theo chuỗi cơ chế: thanh khoản hệ thống → lãi suất liên ngân hàng → điều tiết OMO/tín phiếu → tỷ giá và kỳ vọng lãi suất → tác động đến ngân hàng, định giá và dòng tiền cổ phiếu.');
 let sources='';if(matched.length)sources=section('Tin thị trường liên quan',`<div class="analysis-news">${matched.map(n=>`<a href="${esc(n.url||'#')}" target="_blank" rel="noopener noreferrer"><span>${esc(n.title)}</span><small>${esc(n.source||'')} · ${esc(String(n.publishedAt||'').slice(0,10))}</small></a>`).join('')}</div>`);
 return prose(paragraphs)+sources;
}
function classify(q){const s=norm(q);if((/la gi|nghia la gi|khai niem|giai thich|hieu the nao|cong thuc|cach doc|y nghia/.test(s))&&(conceptKey(q)||s.length>3))return'concept';if(/nhnn|ngan hang nha nuoc|lai suat|overnight|\bon\b|omo|thanh khoan|ty gia|lam phat|\bgdp\b|\bpmi\b|\bfdi\b|cung tien|m2|tin dung|vi mo/.test(s))return'macro';if(/vi sao|nguyen nhan|tang|giam|bien dong|phien|gia co phieu|dong luc/.test(s))return'movement';if(/rui ro|canh bao|bat thuong|yeu diem/.test(s))return'risk';if(/so sanh|ky truoc|cung ky|qoq|yoy/.test(s))return'compare';if(/suc khoe|tai chinh|tong quan|doanh thu|loi nhuan|dong tien|no|roe|roa|bien loi nhuan|fcf|ocf|phai thu|ton kho/.test(s))return'financial';if(conceptKey(q))return'concept';return'search';}
function analyze(question){
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 const ctx={quote:m.quote||null,driver:m.driver||null,technical:m.technical||null,news:m.news||[],marketNews:m.marketNews||[]};
 const body=type==='macro'?macroHTML(question,m):type==='movement'?movementHTML(ctx):type==='concept'?conceptHTML(question,a,q,annual,quarterly):type==='financial'?financialHTML(a,q):type==='risk'?riskHTML(a,q):type==='compare'?comparisonHTML(a,q):searchHTML(question,annual,quarterly);
 return{type,html:body||'<div class="analysis-empty">Không có trường dữ liệu phù hợp trong bộ dữ liệu đang tải cho câu hỏi này.</div>'};
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