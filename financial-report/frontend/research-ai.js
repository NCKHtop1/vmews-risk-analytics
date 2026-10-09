(function(){'use strict';
const $=id=>document.getElementById(id);
const DOLPHIN_VERSION='DOLPHIN_V6';
const AI_MODE_KEY='finquery_dolphin_mode';
const state={symbol:'',history:[],busy:false,directKey:'',model:'',modelCandidates:[],mode:'normal',lastQuestion:'',currentController:null,geminiReady:false,lastGeminiError:''};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const nf=new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1});
const pct=n=>Number.isFinite(n)?`${n>0?'+':''}${nf.format(n)}%`:'—';
const num=n=>Number.isFinite(n)?nf.format(n):'—';
const tone=n=>!Number.isFinite(n)?'neutral':n>0?'positive':n<0?'negative':'neutral';
const ACADEMIC_LENSES=[
 {id:'ohlson1995',frameworks:['corporate','bank'],defaults:['corporate','bank'],title:'Ohlson (1995) · accounting-based equity valuation',citation:'Ohlson, J.A. (1995), Earnings, Book Values, and Dividends in Equity Valuation',url:'https://onlinelibrary.wiley.com/doi/10.1111/j.1911-3846.1995.tb00461.x',patterns:[/dinh gia|valuation|book value|gia tri so sach|pb|p b|roe|loi nhuan|earnings/],use:'Dùng như khung liên hệ lợi nhuận, giá trị sổ sách và thông tin khác với giá trị vốn chủ.',caveat:'Đây là benchmark lý thuyết kế toán-định giá, không phải công thức dự báo giá ngắn hạn cho một cổ phiếu.'},
 {id:'sloan1996',frameworks:['corporate'],defaults:['corporate'],title:'Sloan (1996) · cash flow vs accrual persistence',citation:'Sloan, R.G. (1996), Do Stock Prices Fully Reflect Information in Accruals and Cash Flows About Future Earnings?',url:'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2598',patterns:[/dong tien|ocf|fcf|accrual|loi nhuan|earnings|phai thu|ton kho|chat luong loi nhuan/],use:'Dùng để tách chất lượng lợi nhuận tạo bằng tiền khỏi phần phụ thuộc nhiều vào accrual/vốn lưu động.',caveat:'Kết quả gốc là bằng chứng thực nghiệm trên dữ liệu lịch sử; không được suy diễn thành dự báo chắc chắn cho doanh nghiệp Việt Nam.'},
 {id:'dechowDichev2002',frameworks:['corporate'],defaults:[],title:'Dechow & Dichev (2002) · accrual quality',citation:'Dechow, P.M. & Dichev, I.D. (2002), The Quality of Accruals and Earnings: The Role of Accrual Estimation Errors',url:'https://doi.org/10.2308/accr.2002.77.s-1.35',patterns:[/accrual|phai thu|ton kho|von luu dong|working capital|chat luong loi nhuan|earnings quality/],use:'Dùng để giải thích vì sao biến động vốn lưu động và sai số ước tính accrual có thể làm chất lượng lợi nhuận kém bền vững hơn.',caveat:'FinQuery chỉ được liên hệ định tính nếu chưa có mô hình accrual-quality đầy đủ; không tự gán điểm học thuật.'},
 {id:'piotroski2000',frameworks:['corporate'],defaults:['corporate'],title:'Piotroski (2000) · fundamental financial signals',citation:'Piotroski, J.D. (2000), Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers',url:'https://doi.org/10.2307/2672906',patterns:[/suc khoe tai chinh|fundamental|co ban|roe|roa|dong tien|don bay|bien loi nhuan|financial strength/],use:'Dùng như lăng kính tổng hợp profitability, leverage/liquidity và operating efficiency từ báo cáo tài chính.',caveat:'Không được gọi điểm sức khỏe FinQuery là F-score Piotroski nếu không tính đúng định nghĩa gốc và mẫu áp dụng tương ứng.'},
 {id:'modiglianiMiller1958',frameworks:['corporate'],defaults:[],title:'Modigliani & Miller (1958) · capital structure benchmark',citation:'Modigliani, F. & Miller, M.H. (1958), The Cost of Capital, Corporation Finance and the Theory of Investment',url:'https://www.jstor.org/stable/1809766',patterns:[/don bay|no vay|no phai tra|capital structure|wacc|chi phi von|lai vay/],use:'Dùng như benchmark để tách giá trị hoạt động khỏi tác động của cấu trúc tài trợ và chi phí vốn.',caveat:'Các mệnh đề gốc dựa trên giả định mạnh; trong thực tế phải xét thuế, distress, agency và bất cân xứng thông tin.'},
 {id:'famaFrench2015',frameworks:['corporate','bank'],defaults:[],title:'Fama & French (2015) · profitability and investment factors',citation:'Fama, E.F. & French, K.R. (2015), A Five-Factor Asset Pricing Model',url:'https://www.sciencedirect.com/science/article/pii/S0304405X14002323',patterns:[/factor|profitability|dau tu|investment|expected return|loi suat ky vong|cross section/],use:'Dùng như lăng kính cross-sectional về profitability và investment khi bàn tới lợi suất kỳ vọng hoặc định vị tương đối.',caveat:'Không được dùng mô hình nhân tố để suy ra trực tiếp target price hay lợi suất chắc chắn của một mã nếu thiếu dữ liệu factor exposure.'},
 {id:'hoSaunders1981',frameworks:['bank'],defaults:['bank'],title:'Ho & Saunders (1981) · determinants of bank interest margins',citation:'Ho, T.S.Y. & Saunders, A. (1981), The Determinants of Bank Interest Margins: Theory and Empirical Evidence',url:'https://doi.org/10.2307/2330377',patterns:[/nim|bien lai|spread|chi phi von|cost of funds|lai suat|interest margin/],use:'Dùng để giải thích NIM/spread trong quan hệ với cấu trúc tài sản-nợ, biến động lãi suất, cạnh tranh và rủi ro trung gian.',caveat:'Không quy toàn bộ NIM của một ngân hàng vào một biến duy nhất; phải đọc cùng CASA, cost of funds, asset yield và chất lượng tín dụng.'},
 {id:'jegadeeshTitman1993',frameworks:['corporate','bank'],defaults:[],title:'Jegadeesh & Titman (1993) · momentum evidence',citation:'Jegadeesh, N. & Titman, S. (1993), Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency',url:'https://doi.org/10.1111/j.1540-6261.1993.tb04702.x',patterns:[/momentum|dong luong|xu huong|winner|loser|suc manh tuong doi/],use:'Dùng để đặt hiện tượng momentum vào bối cảnh nghiên cứu thực nghiệm về lợi suất quá khứ và lợi suất sau đó.',caveat:'Nghiên cứu gốc dùng chân trời nhiều tháng; không được đồng nhất máy móc momentum 5 phiên của FinQuery với hiệu ứng 3-12 tháng.'},
 {id:'loMamayskyWang2000',frameworks:['corporate','bank'],defaults:[],title:'Lo, Mamaysky & Wang (2000) · systematic technical analysis',citation:'Lo, A.W., Mamaysky, H. & Wang, J. (2000), Foundations of Technical Analysis',url:'https://doi.org/10.1111/0022-1082.00265',patterns:[/technical|ky thuat|rsi|macd|breakout|ho tro|khang cu|pattern|chart/],use:'Dùng để nhấn mạnh rằng tín hiệu kỹ thuật cần được định nghĩa có hệ thống và kiểm định thống kê thay vì đọc hình chủ quan.',caveat:'Bằng chứng về một số pattern có giá trị thông tin gia tăng không đồng nghĩa mọi indicator đều có sức dự báo ổn định ở mọi thị trường.'}
];
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
function val(row,period){const v=row?.values?.[period];if(v===null||v===undefined||String(v).trim()==='')return null;const n=Number(v);return Number.isFinite(n)?n:null;}
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
 if(ctx.scanner?.signals?.length){const labels=ctx.scanner.signals.map(x=>x.label).slice(0,4);out.push('Technical Scanner đang ghi nhận: '+labels.join('; ')+'. Mức ưu tiên '+num(ctx.scanner.priority)+'/100, RSI14 '+num(ctx.scanner.rsi14)+', volume/TB20 '+num(ctx.scanner.volumeRatio20)+'x. Đây là tín hiệu sàng lọc cần xác nhận trên chart, không phải lệnh mua/bán.');}
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
const K=window.FinQueryKnowledge||{find(){return null;},search(){return [];},explainLabel(){return'Chỉ tiêu chưa có định nghĩa được kiểm chứng.';}};
const QP=window.FinQueryQuestionPolicy||null;
function technicalMetric(concept,m){const t=m?.technical,i=t?.indicators||{};if(!concept||!t)return null;const map={rsi:'rsi',macd:'macd',bollinger:'middle',atr:'atr',adx:'adx',stochastic:'stoch',supertrend:'supertrend',obv:'obv',mfi:'mfi',cmf:'cmf',sma:'sma',ema:'ema'};const key=map[concept.id];return key&&Number.isFinite(i[key])?{value:i[key],period:t.timeframe,key}:null;}
function currentConceptValue(concept,a,q,annual,m){if(!concept)return null;if(concept.metric&&a){if(Object.prototype.hasOwnProperty.call(a.ratios,concept.metric)&&Number.isFinite(a.ratios[concept.metric]))return{value:a.ratios[concept.metric],period:a.period,unit:'%'};if(Object.prototype.hasOwnProperty.call(a.values,concept.metric)&&Number.isFinite(a.values[concept.metric]))return{value:a.values[concept.metric],period:a.period,unit:'money'};}if(concept.id==='reference'&&Number.isFinite(m?.quote?.reference))return{value:m.quote.reference,period:'phiên hiện tại',unit:'VND'};return technicalMetric(concept,m);}
function dynamicMetricHit(question,annual,quarterly){
 const hits=[];
 for(const [scope,data] of [['Năm',annual],['Quý',quarterly]]){
  if(!data)continue;
  for(const hit of QP?.searchRows?.(question,data,{minCoverage:.8,limit:6})||[]){
   if(!(' '+norm(question)+' ').includes(' '+norm(hit.row.label)+' '))continue;
   const p=latest(data);if(!p||!Number.isFinite(val(hit.row,p)))continue;
   hits.push({...hit,scope,data});
  }
 }
 return hits.sort((a,b)=>b.score-a.score||String(a.row.label).length-String(b.row.label).length)[0]||null;
}
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
 const ranked=K.search?.(question,4)||[],concept=K.find?.(question)||null,dyn=!concept?dynamicMetricHit(question,annual,quarterly):null;if(!concept&&!dyn)return'';
 if(dyn){const p=latest(dyn.data),prev=previousPeriod(dyn.data,p),v=val(dyn.row,p),old=val(dyn.row,prev),g=growth(v,old),definition=K.explainLabel?.(dyn.row.label)||'Đây là chỉ tiêu có trong dữ liệu FinQuery.';return prose([dyn.row.label+': '+definition+' Với '+state.symbol+', kỳ '+p+' ghi nhận '+point(v,dyn.row.unit)+(Number.isFinite(g)?', '+relationText(g)+' so với '+prev:'')+'.'])+section('Dữ liệu đang có',table([[dyn.row.label,point(v,dyn.row.unit),prev?('so với '+prev+' '+pct(g)):'',tone(g)]]));}
 const current=currentConceptValue(concept,a,q,annual,m),paragraphs=[concept.definition,concept.formula?'Công thức: '+concept.formula+'.':'',concept.read||'',...conceptDiagnosis(concept,a,q)];
 if(current){let value=current.unit==='%'?num(current.value)+'%':current.unit==='money'?money(current.value):current.unit==='VND'?nf.format(current.value)+' đồng':num(current.value);let sentence='Với '+state.symbol+', '+concept.title+' tại '+current.period+' đang ở mức '+value+'.';if(concept.metric&&annual&&a?.previous){const old=val(find(annual,concept.metric),a.previous);if(Number.isFinite(old)){const diff=current.value-old;sentence+=' So với '+a.previous+', chỉ tiêu '+(diff>=0?'tăng ':'giảm ')+num(Math.abs(diff))+' điểm.';}}paragraphs.push(sentence);}
 if(m?.technical&&['rsi','macd','bollinger','atr','adx','stochastic','supertrend','obv','mfi','cmf','sma','ema','meanReversion','volume','cci','roc','willr','vwap'].includes(concept.id)&&m.technical.snapshot)paragraphs.push(m.technical.snapshot.title+'. '+m.technical.snapshot.detail);
 // Related concepts must never be presented as an answer to an unrelated definition query.
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
 const results=[];
 for(const [scope,data] of [['Năm',annual],['Quý',quarterly]]){
  if(!data)continue;
  for(const hit of QP?.searchRows?.(question,data,{minCoverage:.8,limit:8})||[]){
   const values=periods(data).slice(-8).filter(p=>Number.isFinite(val(hit.row,p))).map(p=>({period:p,value:val(hit.row,p)}));
   if(values.length)results.push({...hit,scope,data,values});
  }
 }
 return results.sort((a,b)=>b.score-a.score);
}
function newsSearch(question,items){
 return QP?.selectNews?.(question,items,{symbol:state.symbol,companyOnly:false,limit:8})||[];
}
function searchHTML(question,annual,quarterly,m){
 const concept=K.find?.(question);if(concept)return conceptHTML(question,annualSnapshot(annual),quarterSnapshot(quarterly),annual,quarterly,m);
 const hits=localMetricSearch(question,annual,quarterly),newsHits=newsSearch(question,[...(m.news||[]),...(m.marketNews||[])]);
 const paragraphs=[];
 if(hits.length){const h=hits[0],last=h.values.at(-1),prev=h.values.at(-2),g=prev?growth(last.value,prev.value):null;paragraphs.push(h.row.label+' của '+state.symbol+' ở '+last.period+' là '+point(last.value,h.row.unit)+(Number.isFinite(g)?', '+relationText(g)+' so với '+prev.period:'')+'. '+(K.explainLabel?.(h.row.label)||''));}
 if(newsHits.length){const n=newsHits[0];paragraphs.push('Tin phù hợp nhất với câu hỏi là “'+n.title+'” từ '+(n.source||'nguồn báo chí')+' công bố '+String(n.publishedAt||'').slice(0,16).replace('T',' ')+'.'+(n.summary?' Nội dung tóm tắt: '+n.summary:''));}
 if(m.technical?.snapshot)paragraphs.push('Trạng thái kỹ thuật hiện tại: '+m.technical.snapshot.title+'. '+m.technical.snapshot.detail);
 if(paragraphs.length){let details='';if(hits.length)details+=section('Chuỗi dữ liệu liên quan',`<div class="analysis-search-results">${hits.slice(0,8).map(h=>`<div><strong>${esc(h.row.label)}</strong><span>${esc(h.scope)}</span><p>${esc(h.values.map(x=>x.period+': '+point(x.value,h.row.unit)).join(' · '))}</p></div>`).join('')}</div>`);if(newsHits.length)details+=headlineList(newsHits);return prose(paragraphs)+details;}
 // No semantic match: fail closed rather than manufacture a plausible but unrelated definition.
 if(/la gi|nghia la gi|khai niem|cong thuc|cach tinh|dinh nghia/.test(norm(question)))return prose(['FinQuery chưa xác định được chính xác thuật ngữ được hỏi trong kho kiến thức đã kiểm chứng. Vui lòng nêu cụm từ đầy đủ; hệ thống sẽ không thay thế bằng định nghĩa khác.']);
 const tech=m.technical?.snapshot?m.technical.snapshot.title+'. '+m.technical.snapshot.detail:'',marketText=m.quote?state.symbol+' đang '+(m.quote.changePct>=0?'tăng ':'giảm ')+num(Math.abs(m.quote.changePct))+'% so với tham chiếu '+(Number.isFinite(m.quote.reference)?nf.format(m.quote.reference)+' đồng':'hiện tại')+'.':'';
 return prose([marketText,tech,'Câu hỏi được xử lý theo dữ liệu thực của mã đang xem: giá, chỉ báo kỹ thuật, BCTC và tin liên quan đang có trong FinQuery.'].filter(Boolean));
}
function macroDatasetFor(question,macro){if(!macro?.datasets)return null;const s=norm(question),esg=/\besg\b|moi truong|xa hoi|quan tri|governance|environment|social/.test(s),corporate=Object.entries(macro.datasets).find(([id,ds])=>id.startsWith('company_esg_')||ds?.companySymbol),id=esg?(corporate?.[0]||'esg_world_bank'):/\bpmi\b/.test(s)?'pmi':/\bfdi\b/.test(s)?'fdi':/gdp/.test(s)?'gdp_growth':/cung tien|m2|money supply/.test(s)?'money_supply':/tin dung|credit/.test(s)?'credit_sector':'macro_overview';return macro.datasets[id]?{id,...macro.datasets[id]}:null;}
function macroNews(question,items){return newsSearch(question,items).slice(0,5);}
function macroHTML(question,m){
 const macro=window.FinMacro?.context?.(),ds=macroDatasetFor(question,macro),matched=macroNews(question,m.marketNews||[]),paragraphs=[];
 if(ds){const rs=ds.rows||[],last=rs.at(-1),prev=rs.at(-2),numeric=ds.numericColumns||[],tokens=norm(question).split(' '),chosen=numeric.find(k=>tokens.some(t=>t.length>2&&(norm(k).includes(t)||norm(ds.metricLabels?.[k]||'').includes(t))))||numeric[0];if(last&&chosen&&typeof last[chosen]==='number'){const label=ds.metricLabels?.[chosen]||chosen,provider=ds.source||'nguồn dữ liệu';let sentence=provider+' gần nhất ghi nhận '+label+' ở '+num(last[chosen])+'.';if(prev&&typeof prev[chosen]==='number'&&prev[chosen]!==0){const change=(last[chosen]/prev[chosen]-1)*100;sentence+=' So với mốc liền trước, '+label+' '+relationText(change)+'.';}paragraphs.push(sentence);}}
 if(matched.length){const first=matched[0],second=matched[1],qt=Date.parse(m.quote?.sourceTime||m.quote?.collectedAt||''),nt=Date.parse(first.publishedAt||''),timing=Number.isFinite(qt)&&Number.isFinite(nt)?(qt-nt)/3600000:null;let sentence='Tin gần nhất liên quan tới câu hỏi là “'+first.title+'” từ '+(first.source||'nguồn báo chí')+'.';if(Number.isFinite(timing))sentence+=timing>=0?' Tin xuất hiện trước snapshot khoảng '+num(Math.abs(timing))+' giờ, nên đã nằm trong bối cảnh thông tin thị trường ở thời điểm giá hiện tại.':' Tin xuất hiện sau snapshot khoảng '+num(Math.abs(timing))+' giờ, nên phù hợp hơn để theo dõi phản ứng ở phiên kế tiếp.';if(first.summary)sentence+=' Nội dung RSS: '+first.summary;paragraphs.push(sentence);if(second)paragraphs.push('Bối cảnh thứ hai là “'+second.title+'”. Khi đọc các sự kiện NHNN, OMO, lãi suất ON hay tín dụng, Dolphin AI sắp xếp theo thứ tự trạng thái thanh khoản trước sự kiện → hành động điều tiết → phản ứng lãi suất và thị trường sau sự kiện để xác định cơ chế đang chi phối.');}
 else paragraphs.push(ds?.companySymbol?'Với câu hỏi ESG doanh nghiệp, Dolphin AI ưu tiên KPI do ngân hàng công bố theo từng năm và giữ nguyên external assessment của từng provider; không tự quy đổi Moody’s, VNSI, WWF, S&P hay Sustainalytics thành một điểm chung.':ds?.id==='esg_world_bank'?'Với câu hỏi ESG cấp quốc gia, Dolphin AI đọc chuỗi World Bank Sovereign ESG của Việt Nam theo toàn bộ năm có dữ liệu và không nội suy các năm bị thiếu.':'Với câu hỏi vĩ mô này, Dolphin AI đọc dữ liệu VBMA đang mở trước, sau đó ghép với chuỗi tin thị trường theo thời điểm. Trọng tâm là diễn biến trước và sau sự kiện: thanh khoản, lãi suất, tín dụng và phản ứng của thị trường.');
 const external=macro?.corporateEsg?.externalAssessments||[];if(ds?.companySymbol&&external.length){paragraphs.push('Đánh giá bên ngoài gần nhất đang lưu: '+external.slice(-4).map(x=>(x.provider||'Nguồn')+' '+(x.year||'')+': '+(x.value||x.assessmentType||'đã công bố')).join(' · ')+'.');}
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
// Deliberately separate a definition, a measured value and a multi-part query.
function multiConceptHTML(question){
 const matches=(K.search?.(question,12)||[]).filter(x=>x.score>=25);
 const selected=matches.filter((x,i)=>matches.findIndex(y=>y.c.id===x.c.id)===i).slice(0,5);
 if(selected.length<2)return conceptHTML(question,annualSnapshot(raw()?.annual),quarterSnapshot(raw()?.quarterly),raw()?.annual,raw()?.quarterly,market());
 return selected.map(({c})=>section(c.title,prose([c.definition,c.formula?'Công thức: '+c.formula+'.':null,c.read]))).join('');
}
const FINANCIAL_TARGETS=[
 ['currentAssets','Tài sản ngắn hạn',/\btai san ngan han\b|\bcurrent assets\b/,'currentAssets'],
 ['nonCurrentAssets','Tài sản dài hạn',/\btai san dai han\b|\bnon current assets\b/,'nonCurrentAssets'],
 ['currentLiabilities','Nợ ngắn hạn',/\bno ngan han\b|\bcurrent liabilities\b/,'currentLiabilities'],
 ['assets','Tổng tài sản',/\btong tai san\b|\btong cong tai san\b/,'assets'],
 ['liabilities','Nợ phải trả',/\bno phai tra\b|\btong no\b/,'liabilities'],
 ['equity','Vốn chủ sở hữu',/\bvon chu\b|\bequity\b/,'equity'],
 ['revenue','Doanh thu thuần',/\bdoanh thu\b|\brevenue\b/,'revenue'],
 ['profit','Lợi nhuận sau thuế',/\bloi nhuan\b|\blnst\b|\bnet income\b/,'profit'],
 ['cash','Tiền và tương đương tiền',/\btien va tuong duong tien\b|\btien mat\b/,'cash'],
 ['receivables','Khoản phải thu',/\bphai thu\b|\breceivables\b/,'receivables'],
 ['inventory','Hàng tồn kho',/\bhang ton kho\b|\bton kho\b|\binventory\b/,'inventory'],
 ['ocf','Dòng tiền kinh doanh',/\bdong tien kinh doanh\b|\bdong tien hd kd\b|\bocf\b|\bcfo\b/,'ocf'],
 ['capex','CAPEX',/\bcapex\b|\bchi dau tu\b/,'capex'],
 ['roe','ROE',/\broe\b/,'roe'],
 ['roa','ROA',/\broa\b/,'roa'],
 ['grossMargin','Biên lợi nhuận gộp',/\bbien loi nhuan gop\b|\bbien gop\b/,'grossMargin'],
 ['netMargin','Biên lợi nhuận ròng',/\bbien loi nhuan rong\b|\bbien rong\b/,'netMargin'],
 ['nii','Thu nhập lãi thuần',/\bnii\b|\bthu nhap lai thuan\b/,'nii'],
 ['toiBank','Tổng thu nhập hoạt động',/\btoi\b|\btong thu nhap hoat dong\b/,'toiBank'],
 ['nim','NIM',/\bnim\b|\bbien lai rong\b/,'nim'],
 ['npl','Nợ xấu',/\bnpl\b|\bno xau\b/,'npl'],
 ['cir','CIR',/\bcir\b|\bcost to income\b/,'cir'],
 ['car','CAR',/\bcar\b|\ban toan von\b/,'car']
];
const ROW_PATTERNS={
 currentAssets:/^tai san ngan han$/,nonCurrentAssets:/^tai san dai han$/,currentLiabilities:/^no ngan han$/,
 nii:/^thu nhap lai thuan$/,toiBank:/^tong thu nhap hoat dong$/,nim:/\bnim\b|^bien lai rong/,npl:/\bnpl\b|^ty le no xau/,cir:/^cir\b|ty le chi phi.*thu nhap/,car:/^car\b|^ty le an toan von/
};
function askTargets(question){
 const s=norm(question),matched=FINANCIAL_TARGETS.filter(([, ,pattern])=>pattern.test(s));
 // Explicitly requested named metrics are not interchangeable.
 if(matched.some(x=>x[0]==='currentAssets'||x[0]==='nonCurrentAssets'))return matched.filter(x=>x[0]!=='assets');
 if(matched.some(x=>x[0]==='currentLiabilities'))return matched.filter(x=>x[0]!=='liabilities');
 return matched;
}
function exactMetricRow(data,key){
 if(!data)return null;
 const special=ROW_PATTERNS[key];if(special)return rows(data).find(r=>special.test(norm(r.label)))||null;
 if(key==='revenue')return rows(data).find(r=>/^doanh thu thuan$|^doanh thu ban hang va cung cap dich vu$/.test(norm(r.label)))||null;
 if(key==='profit')return find(data,'profit');
 return find(data,key);
}
function metricHTML(question,annual,quarterly,m){
 const s=norm(question),period=QP?.periodInfo?.(question)||{years:[],quarters:[],isQuarter:false},specified=[...period.quarters,...(!period.quarters.length?period.years:[])];
 const wantsQuarter=period.isQuarter||period.quarters.length>0;
 const data=wantsQuarter?quarterly:annual;
 const datasetType=wantsQuarter?'quý':'năm',series=specified.length?specified:(data?[latest(data)]:[]);
 let targets=askTargets(question);
 if(!targets.length){
  const closest=(K.search?.(question,3)||[]).find(x=>x.score>=30);
  if(closest){targets=[[closest.c.id,closest.c.title,/./,closest.c.id]];}
 }
 if(!data||!series.length)return prose(['Chưa có BCTC '+datasetType+' để trả lời đúng kỳ và chỉ tiêu đang hỏi.']);
 if(!targets.length){
  const hits=QP?.searchRows?.(question,data,{minCoverage:.85,limit:3})||[];
  targets=hits.length?[['dynamic',hits[0].row.label,/./,'dynamic']]:[];
 }
 if(!targets.length)return prose(['Không xác định được chính xác chỉ tiêu BCTC được hỏi. FinQuery sẽ không tự thay bằng một chỉ tiêu khác.']);
 const output=[];
 for(const [id,title,,key] of targets.slice(0,5)){
  const row=key==='dynamic'?(QP?.searchRows?.(question,data,{minCoverage:.85,limit:1})||[])[0]?.row:exactMetricRow(data,key);
  if(!row){output.push(title+': chưa có trường số liệu đối chiếu được trong BCTC '+datasetType+'.');continue;}
  for(const p of series){
   const v=val(row,p);
   output.push(title+' ('+row.label+') của '+state.symbol+' kỳ '+p+': '+(Number.isFinite(v)?point(v,row.unit):'chưa có số liệu hợp lệ')+'.');
  }
 }
 return prose(output)+(output.some(x=>!x.includes('chưa có'))?'<small>Nguồn: BCTC '+esc(state.symbol)+' · kỳ gốc được ghi rõ ở từng chỉ tiêu; không tự thay kỳ thiếu bằng kỳ khác.</small>':'');
}
function newsHTML(question,m){
 const s=norm(question),global=/\btin thi truong\b|\btoan thi truong\b|\bvi mo\b/.test(s),items=global?m.marketNews||[]:m.news||[];
 const found=QP?.selectNews?.(question,items,{symbol:state.symbol,companyOnly:!global,limit:6})||[];
 if(!found.length)return prose(['Chưa có tin '+(global?'thị trường':'được xác nhận thuộc '+state.symbol)+' phù hợp câu hỏi và bộ dữ liệu đang tải.']);
 return prose(['Các tin phù hợp nhất trong dữ liệu FinQuery (không đồng nghĩa đã được xác minh nguyên nhân tác động giá):'])+headlineList(found);
}
function forecastHTML(question){
 const info=window.FinForecast?.context?.()||null;
 const summary=info?.summary||null;
 if(!summary||info?.status==='stale'||info?.eligible===false)return prose(['Không có dự báo được xác minh đúng mã, đúng ngày và đúng chân trời trong ngữ cảnh Dolphin hiện tại. Vui lòng mở Forecast Core để kiểm tra trạng thái dữ liệu. FinQuery không tự suy diễn giá mục tiêu hoặc xác suất.']);
 return prose(['Dữ liệu dự báo phải được kiểm tra trên Forecast Core theo phiên gốc và chân trời T+3/T+4/T+5. Không xuất ra con số nếu chưa đối chiếu được nguồn gốc của dự báo.']);
}
function technicalHTML(question,m){
 const priceCheck=QP?.priceQuality?.(m.quote,state.symbol,question);if(priceCheck&&!priceCheck.usable)return prose([priceCheck.reason+'. Không thể dùng chỉ báo như tín hiệu kỹ thuật trong phiên hiện tại.']);
 const concept=K.find?.(question),v=concept?technicalMetric(concept,m):null,asOf=m.technical?.sourceTime||m.quote?.sourceTime||'';
 const indicators=(K.search?.(question,12)||[]).filter(x=>x.score>=25&&['rsi','macd','bollinger','atr','adx','stochastic','supertrend','mfi','cmf','obv','sma','ema','vwap','cci','roc','willr'].includes(x.c.id));
 if(indicators.length>1){const readings=indicators.slice(0,5).map(x=>({c:x.c,v:technicalMetric(x.c,m)})).filter(x=>x.v).map(x=>x.c.title+' = '+num(x.v.value)+' ('+(x.v.period||'khung hiện tại')+')');return readings.length?prose([...readings,'Nguồn snapshot: '+String(asOf||'không xác định')+'.']):prose(['Chưa có giá trị hợp lệ cho các chỉ báo kỹ thuật được hỏi.']);}
 if(v)return prose([concept.title+' của '+state.symbol+' ('+(v.period||'khung đang xem')+') = '+num(v.value)+'. Dữ liệu kỹ thuật gốc: '+String(asOf||'không rõ thời điểm')+'.']);
 if(m.technical?.snapshot)return prose(['Trạng thái kỹ thuật của '+state.symbol+': '+m.technical.snapshot.title+'. '+m.technical.snapshot.detail,'Nguồn snapshot: '+String(asOf||'chưa xác định')+'.']);
 return prose(['Chưa có snapshot kỹ thuật hợp lệ cho mã được hỏi.']);
}
function marketRiskHTML(){
 const d=window.FinRiskMonitor?.context?.()||null;
 const score=Number(d?.overall?.score);
 if(d?.status!=='ok'||!Number.isFinite(score))return prose(['Chưa có snapshot giám sát rủi ro thị trường hợp lệ để kết luận.']);
 const quoteTime=market()?.quote?.sourceTime||market()?.quoteBundleSourceTime,sourceTime=d.sourceTime||'';
 const aligned=quoteTime&&sourceTime&&Math.abs(Date.parse(quoteTime)-Date.parse(sourceTime))<=20*60000;
 if(quoteTime&&!aligned)return prose(['Snapshot rủi ro thị trường chưa đồng bộ với thời điểm giá; không dùng điểm rủi ro này để diễn giải trạng thái hiện tại.']);
 const level=d.overall?.level?.label||'chưa phân loại';
 return prose(['Rủi ro thị trường trong snapshot '+String(sourceTime||'không xác định')+': '+num(score)+'/100; mức '+level+'. Đây là điểm giám sát theo mô hình, không phải xác suất thị trường giảm hay khuyến nghị giao dịch.']);
}
function classify(q){
 return QP?.route?.(q,K.search?.(q,12)||[])||'unknown';
}
function analyze(question){
 const requested=window.FinResearchAgent?.resolveTargetSymbols?.(question)||[];
 if(requested.length>1)return{type:'multiSymbol',html:prose(['Câu hỏi yêu cầu nhiều mã ('+requested.join(', ')+'). Chế độ dữ liệu cục bộ hiện không tải BCTC độc lập cho tất cả mã cùng lúc; không thể so sánh chính xác khi thiếu dữ liệu.'])};
 const r=raw(),m=market(),annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null,a=annualSnapshot(annual),q=quarterSnapshot(quarterly),type=classify(question);
 if(requested.length===1&&requested[0]!==state.symbol)return{type,html:prose(['Dữ liệu '+requested[0]+' chưa được đồng bộ với mã đang hiển thị ('+state.symbol+'). FinQuery không dùng số liệu của mã khác để trả lời.'])};
 const validQuote=QP?.priceQuality?.(m.quote,state.symbol,question);
 if(type==='movement'&&validQuote&&!validQuote.usable)return{type,html:prose([validQuote.reason+'. Hệ thống không dùng giá sai mã hoặc phiên cũ để trả lời câu hỏi về phiên hiện tại.'])};
 const ctx={quote:validQuote?.usable===false?null:m.quote||null,driver:m.driver||null,technical:m.technical||null,scanner:m.scanner?.current||null,news:m.news||[],marketNews:m.marketNews||[]};
 const body=type==='macro'?macroHTML(question,m):type==='movement'?movementHTML(ctx):type==='concept'?conceptHTML(question,a,q,annual,quarterly,m):type==='multiConcept'?multiConceptHTML(question):type==='metric'||type==='multiMetric'?(K.find?.(question)&&['rsi','macd','bollinger','atr','adx','stochastic','supertrend','mfi','cmf','obv','sma','ema','vwap','cci','roc','willr'].includes(K.find(question).id)?technicalHTML(question,m):metricHTML(question,annual,quarterly,m)):type==='news'?newsHTML(question,m):type==='forecast'?forecastHTML(question):type==='technical'?technicalHTML(question,m):type==='financial'?financialHTML(a,q):type==='risk'?(/thi truong|vnindex|vn index|rung lac thi truong/.test(norm(question))?marketRiskHTML():riskHTML(a,q)):type==='compare'?(askTargets(question).length?metricHTML(question,annual,quarterly,m):comparisonHTML(a,q)):type==='memo'?memoHTML(question,a,q,m):prose(['FinQuery chưa xác định được đủ dữ liệu đáng tin cậy để trả lời trực tiếp câu hỏi này bằng chế độ cục bộ. Kết nối Gemini để xử lý câu hỏi mở; không sử dụng số liệu hoặc thuật ngữ khác thay thế.']);
 return{type,html:body||prose(['Chưa có dữ liệu phù hợp để trả lời chính xác; không tự suy diễn.'])};
}

const GOOGLE_AI_ORIGIN='https://generativelanguage.googleapis.com/v1beta';
const GEMINI_SESSION_KEY='vmews_solution_ai_browser_session';
const STABLE_MODEL_ORDER={normal:['gemini-3.5-flash-lite','gemini-3.1-flash-lite','gemini-3.8-flash','gemini-3.7-flash','gemini-3.6-flash','gemini-3.5-flash'],deep:['gemini-3.8-flash','gemini-3.7-flash','gemini-3.6-flash','gemini-3.5-flash','gemini-3.5-flash-lite','gemini-3.1-flash-lite']};
const TRANSIENT_GEMINI_STATUS=new Set([408,429,500,502,503,504]);
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
 const stable=(STABLE_MODEL_ORDER[mode==='deep'?'deep':'normal']||[]).find(name=>pool.includes(name)&&!blocked.has(name));if(stable)return stable;
 const lite=pool.filter(x=>/flash[-_.]?lite/i.test(x)).sort((a,b)=>modelVersionScore(b)-modelVersionScore(a));
 const full=pool.filter(x=>/flash/i.test(x)&&!/flash[-_.]?lite/i.test(x)).sort((a,b)=>modelVersionScore(b)-modelVersionScore(a));
 return mode==='deep'?(full[0]||lite[0]||''):(lite[0]||full[0]||'');
}
function modelPlan(mode=state.mode){
 const first=pickModel(mode,state.modelCandidates),plan=first?[first]:[];
 if(mode==='deep'){const lite=pickModel('normal',state.modelCandidates,plan);if(lite)plan.push(lite);}
 const pool=[...new Set(state.modelCandidates||[])];
 const score=name=>{const stable=/preview|experimental|exp-/i.test(name)?0:10000,lite=/flash[-_.]?lite/i.test(name),fit=mode==='deep'?(lite?0:1000):(lite?1000:0);return stable+fit+modelVersionScore(name);};
 for(const candidate of pool.filter(x=>!plan.includes(x)).sort((a,b)=>score(b)-score(a)))plan.push(candidate);
 return plan.slice(0,6);
}

function sessionSecret(){
 if(state.directKey)return state.directKey;
 try{return sessionStorage.getItem(GEMINI_SESSION_KEY)?.trim()||'';}catch{return'';}
}
function rememberSession(secret){
 state.directKey=String(secret||'').trim();state.geminiReady=false;state.lastGeminiError='';
 try{sessionStorage.setItem(GEMINI_SESSION_KEY,state.directKey);}catch{}
}
function forgetSession(){
 state.directKey='';state.model='';state.modelCandidates=[];state.geminiReady=false;state.lastGeminiError='';
 try{sessionStorage.removeItem(GEMINI_SESSION_KEY);}catch{}
}
function providerMessage(status,details=''){
 const detail=String(details||'').replace(/\s+/g,' ').trim().slice(0,260);
 if(status===401)return'HTTP 401 · khóa Gemini không hợp lệ, hết hiệu lực hoặc không được chấp nhận'+(detail?' · '+detail:'');
 if(status===403)return'HTTP 403 · dự án/key không được phép generateContent'+(detail?' · '+detail:'');
 if(status===429)return'HTTP 429 · Gemini đang chạm rate limit/quota';
 if(status===404)return'HTTP 404 · model Gemini không khả dụng với dự án hiện tại'+(detail?' · '+detail:'');
 if(status===503)return'HTTP 503 · Gemini đang quá tải tạm thời';
 if(status>=500)return'HTTP '+status+' · dịch vụ Gemini tạm thời chưa sẵn sàng';
 return 'HTTP '+status+(detail?' · '+detail:'');
}
function transientGemini(status){return TRANSIENT_GEMINI_STATUS.has(Number(status));}
async function geminiFetch(url,options={},timeoutMs=30000){
 const parent=options.signal,ctl=new AbortController();let timedOut=false;
 const onAbort=()=>ctl.abort();if(parent){if(parent.aborted)ctl.abort();else parent.addEventListener('abort',onAbort,{once:true});}
 const timer=setTimeout(()=>{timedOut=true;ctl.abort();},timeoutMs);
 try{return await fetch(url,{...options,signal:ctl.signal});}
 catch(error){if(timedOut){const err=new Error('Gemini phản hồi quá chậm; Dolphin đang thử model dự phòng.');err.status=504;err.code='GEMINI_TIMEOUT';throw err;}throw error;}
 finally{clearTimeout(timer);if(parent)parent.removeEventListener('abort',onAbort);}
}
function availableModels(payload){
 return (payload?.models||[]).filter(item=>{
  const name=String(item.name||'').replace(/^models\//,'');
  const supported=item.supportedGenerationMethods||item.supportedActions||[];
  return name.startsWith('gemini-')&&/flash/i.test(name)&&!/image|audio|tts|live|embedding|robotics/i.test(name)&&(supported.length===0||supported.includes('generateContent')||supported.includes('generate_content'));
 }).map(item=>String(item.name||'').replace(/^models\//,''));
}
async function geminiGenerate(secret,model,body,timeoutMs=30000){
 const response=await geminiFetch(GOOGLE_AI_ORIGIN+'/models/'+encodeURIComponent(model)+':generateContent',{method:'POST',mode:'cors',cache:'no-store',headers:{'Content-Type':'application/json','x-goog-api-key':secret},body:JSON.stringify(body),...(state.currentController?.signal?{signal:state.currentController.signal}:{})},timeoutMs);
 const payload=await response.json().catch(()=>({}));
 if(!response.ok){const err=new Error(providerMessage(response.status,payload?.error?.message));err.status=response.status;err.model=model;err.providerDetails=String(payload?.error?.message||'');throw err;}
 return payload;
}
function retryDelay(attempt){return Math.min(5000,700*(2**attempt))+Math.floor(Math.random()*300);}
function waitGemini(ms){
 const signal=state.currentController?.signal;
 return new Promise((resolve,reject)=>{
  if(signal?.aborted){const e=new Error('Đã dừng');e.name='AbortError';reject(e);return;}
  const timer=setTimeout(done,ms);
  function done(){signal?.removeEventListener('abort',abort);resolve();}
  function abort(){clearTimeout(timer);signal?.removeEventListener('abort',abort);const e=new Error('Đã dừng');e.name='AbortError';reject(e);}
  signal?.addEventListener('abort',abort,{once:true});
 });
}
async function geminiGenerateResilient(secret,model,body,timeoutMs=30000,attempts=2){
 let lastError;
 for(let attempt=0;attempt<Math.max(1,attempts);attempt++){
  try{return await geminiGenerate(secret,model,body,timeoutMs);}
  catch(error){
   lastError=error;
   if(error?.name==='AbortError'||!transientGemini(error?.status)||attempt>=attempts-1)throw error;
   renderGeminiStatus('Gemini '+model+' đang bận · tự thử lại '+(attempt+2)+'/'+attempts+'…');
   await waitGemini(retryDelay(attempt));
  }
 }
 throw lastError;
}
function probeGenerationConfig(model){
 const generationConfig={maxOutputTokens:256,temperature:0};
 if(/^gemini-3(?:\.|-)/i.test(model))generationConfig.thinkingConfig={thinkingLevel:'low'};
 else if(/^gemini-2\.5-(?:flash|flash-lite)/i.test(model))generationConfig.thinkingConfig={thinkingBudget:0};
 return generationConfig;
}
function emptyGeminiReason(payload){
 const candidate=payload?.candidates?.[0]||{},finish=String(candidate.finishReason||candidate.finish_reason||'').trim();
 const usage=payload?.usageMetadata||payload?.usage_metadata||{};
 const thoughts=Number(usage.thoughtsTokenCount??usage.thoughts_token_count);
 const output=Number(usage.candidatesTokenCount??usage.candidates_token_count);
 return [finish&&('finish='+finish),Number.isFinite(thoughts)&&('thoughts='+thoughts),Number.isFinite(output)&&('output='+output)].filter(Boolean).join(', ')||'empty response';
}
async function probeGemini(secret){
 const plan=modelPlan(state.mode),errors=[];
 for(const model of plan){
  try{
   const payload=await geminiGenerateResilient(secret,model,{contents:[{role:'user',parts:[{text:'Reply with exactly OK'}]}],generationConfig:probeGenerationConfig(model)},20000,2);
   const result=providerAnswer(payload);
   if(result.text){state.model=model;state.geminiReady=true;state.lastGeminiError='';return model;}
   errors.push(model+' · '+emptyGeminiReason(payload));
  }catch(error){errors.push(model+' · '+String(error?.message||error));if(error?.status===401)throw error;}
 }
 const err=new Error(errors.at(-1)||'Gemini không trả lời probe generateContent.');err.status=errors.length?503:0;throw err;
}
async function validateGemini(secret,{probe=true}={}){
 const response=await geminiFetch(GOOGLE_AI_ORIGIN+'/models?pageSize=100',{method:'GET',mode:'cors',cache:'no-store',headers:{'x-goog-api-key':secret}},15000);
 const payload=await response.json().catch(()=>({}));
 if(!response.ok){const err=new Error(providerMessage(response.status,payload?.error?.message));err.status=response.status;throw err;}
 state.modelCandidates=availableModels(payload);
 const model=pickModel(state.mode,state.modelCandidates);
 if(!model)throw new Error('Dự án Google chưa có mô hình Gemini Flash hỗ trợ generateContent.');
 state.model=model;
 if(probe)return probeGemini(secret);
 return model;
}
function compactRows(data,question,limit=18,deep=false){
 if(!data)return[];
 const ps=periods(data).slice(-8),terms=norm(question).split(' ').filter(x=>x.length>2&&!STOP_WORDS.has(x)),chosen=new Map(),allRows=rows(data);
 const add=(row,score)=>{if(!row)return;const key=String(row.section||'')+'|'+String(row.label||'');const prior=chosen.get(key);if(!prior||score>prior.score)chosen.set(key,{row,score});};
 for(const row of allRows){const label=norm(row.label),score=terms.reduce((sum,t)=>sum+(label.includes(t)?3:0),0);if(score)add(row,score);}
 for(const key of ['revenue','profit','assets','liabilities','equity','cash','ocf','capex','roe','roa','grossMargin','netMargin','quick','liabilitiesAssets','liabilitiesEquity','revGrowth','profitGrowth'])add(find(data,key),4);
 if(deep){
  const focus=[/nim|bien lai rong|net interest margin/,/cir|chi phi.*thu nhap|cost.*income/,/npl|no xau/,/ldr|loan.*deposit|du no.*tien gui/,/casa|khong ky han/,/bao phu no xau|llr|loan loss coverage/,/car|an toan von|capital adequacy/,/tin dung|cho vay khach hang|du no cho vay/,/tien gui khach hang/,/du phong|provision/,/thu nhap lai|thu nhap ngoai lai|dich vu/,/eps|pe|p e|pb|p b|book value|gia tri so sach/,/bien loi nhuan|margin/,/dong tien|luu chuyen tien/];
  for(const row of allRows){const label=norm(row.label),score=focus.reduce((sum,re)=>sum+(re.test(label)?1:0),0);if(score)add(row,7+score);}
  for(const row of allRows)add(row,.5);
 }
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
function academicLenses(question,knowledge,deep=false){
 const text=norm(question),framework=knowledge?.framework||'general',scored=[];
 for(const lens of ACADEMIC_LENSES){
  if(!(lens.frameworks||[]).includes(framework))continue;
  let score=(deep&&(lens.defaults||[]).includes(framework))?2:0;
  for(const re of lens.patterns||[])if(re.test(text))score+=4;
  if(score>0)scored.push({lens,score});
 }
 scored.sort((a,b)=>b.score-a.score||a.lens.title.localeCompare(b.lens.title,'vi'));
 return scored.slice(0,deep?5:2).map(({lens})=>({id:lens.id,title:lens.title,citation:lens.citation,url:lens.url,use:lens.use,caveat:lens.caveat}));
}
function researchKnowledge(question,annual,quarterly,deep=false){
 const kb=window.FinQueryKnowledge;if(!kb)return{framework:'general',concepts:[]};
 const all=[...rows(annual),...rows(quarterly)],labels=norm(all.map(r=>r.label||'').join(' '));
 const bank=/thu nhap lai thuan|tien gui khach hang|cho vay khach hang|du phong rui ro tin dung|no xau/.test(labels);
 const selected=new Map(),add=c=>{if(c?.id&&!selected.has(c.id))selected.set(c.id,c);};
 for(const hit of kb.search?.(question,deep?12:6)||[])add(hit.c);
 const ids=bank
  ?['nii','nim','casa','costOfFunds','ldr','npl','llr','creditCost','cir','car','roe','roa','pb','bvps']
  :['grossMargin','netMargin','operatingMargin','ocf','fcf','capex','receivables','inventory','workingCapital','liabilitiesAssets','roic','roe','roa','pe','evEbitda'];
 if(deep)for(const id of ids)add(kb.byId?.[id]);
 return{framework:bank?'bank':'corporate',concepts:[...selected.values()].slice(0,deep?20:8).map(c=>({id:c.id,title:c.title,definition:c.definition,formula:c.formula,read:c.read}))};
}
function buildLLMContext(question){
 const r=raw(),m=market(),insights=window.FinInsights?.context?.()||{},annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null;
 const deep=state.mode==='deep'||inferredQuestionMode(question)==='deep',rowLimit=deep?140:24;
 const a=annualSnapshot(annual),q=quarterSnapshot(quarterly),companyNews=cleanNews(m.news||[],deep?12:8),macro=compactMacro(question),knowledge=researchKnowledge(question,annual,quarterly,deep),academic=academicLenses(question,knowledge,deep);
 return{
  scope:'financial-report',contextVersion:DOLPHIN_VERSION,symbol:state.symbol||m.symbol||'',mode:new URLSearchParams(location.search).get('mode')||null,researchDepth:deep?'deep':'normal',
  generatedAt:new Date().toISOString(),
  dataPolicy:{financialNumbers:'FINQUERY_VERIFIED_ONLY',calculations:'LOCAL_ENGINE_ONLY',llmRole:'interpret_compare_explain',missingData:'STATE_MISSING_DO_NOT_INVENT'},
  marketSnapshot:m.quote||null,movementDrivers:m.driver||null,marketContext:m.market||null,technical:m.technical||null,technicalScanner:m.scanner||null,
  localFinancialData:{annualSummary:a,quarterSummary:q,annualRows:compactRows(annual,question,rowLimit,deep),quarterRows:compactRows(quarterly,question,rowLimit,deep)},
  knowledgeBase:knowledge,
  academicContext:{policy:'FRAMEWORK_ONLY_NOT_COMPANY_EVIDENCE',references:academic},
  macroSnapshot:macro,recentNews:companyNews,sectorNews:cleanNews(m.sectorNews||m.marketNews||[],deep?10:6),
  corporateEvents:Array.isArray(insights.corporateEvents)?insights.corporateEvents.slice(0,deep?16:10):[],
  brokerResearch:Array.isArray(insights.brokerResearch)?insights.brokerResearch.slice(0,deep?12:8):[],brokerConsensus:insights.consensus||null,
  researchSourceHealth:Array.isArray(insights.sourceHealth)?insights.sourceHealth.slice(0,20):[],eventSourceHealth:Array.isArray(insights.eventSourceHealth)?insights.eventSourceHealth.slice(0,12):[],provenance:provenanceAnchors()
 };
}
function provenanceAnchors(){
 const r=raw(),m=market(),insights=window.FinInsights?.context?.()||{},annual=r?.annual||(!r?.quarterly?r?.data:null),quarterly=r?.quarterly||null;
 return[
  {tag:'BCTC',label:'BCTC FinQuery',asOf:annual?.updatedAt||annual?.checkedAt||latest(annual)||null},
  {tag:'QUARTER',label:'BCTC quý',asOf:quarterly?.updatedAt||quarterly?.checkedAt||latest(quarterly)||null},
  {tag:'MARKET',label:'Giá thị trường',asOf:m.quote?.sourceTime||m.quote?.collectedAt||null},
  {tag:'SCANNER',label:'Technical Scanner',asOf:m.scanner?.sourceTime||m.scanner?.checkedAt||null},
  {tag:'NEWS',label:'Tin doanh nghiệp',asOf:m.newsCheckedAt||null},
  {tag:'RESEARCH',label:'Báo cáo CTCK / sự kiện',asOf:insights.updatedAt||null}
 ].filter(x=>x.asOf);
}
function sourcesForLLM(){
 const deep=state.mode==='deep',m=market(),insights=window.FinInsights?.context?.()||{},company=cleanNews(m.news||[],deep?10:5).map(x=>({...x,category:'COMPANY'})),sector=cleanNews(m.sectorNews||m.marketNews||[],deep?8:4).map(x=>({...x,category:'SECTOR'}));
 const research=(insights.brokerResearch||[]).filter(x=>/^https?:\/\//i.test(x.sourceUrl||'')).slice(0,deep?8:4).map(x=>({title:(x.broker||'CTCK')+' · '+(x.title||state.symbol),url:x.sourceUrl,publisher:x.broker||'CTCK',publishedAt:x.publishedAt||'',category:'BROKER_RESEARCH'}));
 const events=(insights.corporateEvents||[]).filter(x=>/^https?:\/\//i.test(x.source?.url||'')).slice(0,deep?6:3).map(x=>({title:x.title||'Sự kiện doanh nghiệp',url:x.source.url,publisher:x.source.publisher||'Nguồn doanh nghiệp',publishedAt:x.date||'',category:'CORPORATE_EVENT'}));
 return [...research,...events,...company,...sector].slice(0,deep?28:12).map(x=>({title:x.title,url:x.url,publisher:x.publisher||x.source,publishedAt:x.publishedAt,category:x.category}));
}
function dolphinSystemInstruction(){
 return[
  'Bạn là Dolphin AI của FinQuery, trợ lý nghiên cứu tài chính doanh nghiệp Việt Nam.',
  'Luôn trả lời bằng tiếng Việt tự nhiên, trực tiếp, tránh văn phong chung chung kiểu AI.',
  'Dữ liệu trong context.localFinancialData, marketSnapshot, movementDrivers, technical và technicalScanner là dữ liệu neo. Không tự tạo, thay đổi hoặc ước đoán số liệu nếu dữ liệu neo không có.',
  'technicalScanner là bộ lọc MACD/RSI/volume theo snapshot thị trường. Đây là tín hiệu sàng lọc, không phải khuyến nghị mua/bán; chỉ dùng khi sourceTime phù hợp với marketSnapshot và luôn nêu điều kiện xác nhận/rủi ro nếu người dùng hỏi về tín hiệu.',
  'Không tự tính lại ROA, ROE, biên lợi nhuận, tăng trưởng hoặc các tỷ số khi FinQuery đã cung cấp giá trị. Nếu thiếu chỉ tiêu như NIM, CIR, LDR thì nói rõ chưa có trong dữ liệu hiện tại.',
  'Luôn phân biệt số năm và số quý; gắn nhận định với kỳ cụ thể. Không annualize nếu context không cung cấp quy tắc.',
  'Nếu câu hỏi là follow-up ngắn, dùng lịch sử gần nhất và symbol hiện tại để hiểu mã này, quý này, chỉ số đó.',
  'Tin và Google Search chỉ là lớp bằng chứng bổ sung. Không dùng nguồn web để ghi đè số BCTC hoặc giá đã neo trong FinQuery.',
  'Mỗi đoạn có số liệu hoặc nhận định thực chứng phải gắn nguồn ở cuối câu bằng một hoặc nhiều tag [BCTC], [QUARTER], [MARKET], [SCANNER], [NEWS], [RESEARCH] hoặc [WEB]. Khi dùng khung nghiên cứu trong academicContext để giải thích cơ chế, nêu tác giả/năm trong câu và gắn [ACADEMIC]. Không gắn tag dữ liệu nếu câu chỉ là giải thích khái niệm.',
  'academicContext chỉ là lớp khung học thuật. Không được biến kết quả nghiên cứu trên mẫu/thị trường khác thành bằng chứng rằng doanh nghiệp hiện tại chắc chắn sẽ có cùng kết quả; luôn giữ caveat của từng reference.',
  'Phân biệt recentNews là tin doanh nghiệp đã lọc chặt với sectorNews là bối cảnh ngành. Không được gọi sectorNews là tin của doanh nghiệp.',
  'corporateEvents là các sự kiện có ngày và nguồn; khi nhắc tới phải giữ đúng ngày/loại sự kiện và không tự suy diễn tác động.',
  'brokerResearch là quan điểm của công ty chứng khoán bên thứ ba. Luôn nêu rõ tên CTCK và ngày báo cáo khi dùng khuyến nghị, giá mục tiêu, luận điểm hoặc rủi ro.',
  'Tuyệt đối không biến khuyến nghị MUA/KHẢ QUAN/TRUNG LẬP/BÁN của CTCK thành khuyến nghị của FinQuery hoặc Dolphin.',
  'Chỉ nêu target trung vị/thấp/cao khi brokerConsensus đã cung cấp; không tự bình quân giá mục tiêu từ dữ liệu thiếu.',
  'Nếu hỏi nguyên nhân biến động giá, tách rõ dữ kiện quan sát được khỏi nguyên nhân có bằng chứng. Không khẳng định quan hệ nhân quả chỉ từ tương quan.',
  'Nếu dữ liệu không đủ, nêu đúng dữ liệu nào đang thiếu và vẫn trả lời phần có thể kiểm chứng.',
  'Không đưa ra khuyến nghị mua/bán hoặc cam kết lợi nhuận. Có thể phân tích kịch bản, rủi ro, điều kiện xác nhận và điểm cần theo dõi.',
  'Trả lời theo cấu trúc phù hợp với câu hỏi; không ép mọi câu trả lời vào cùng một mẫu.',
  'knowledgeBase trong context là khung kiến thức tài chính dùng để diễn giải số liệu đúng bản chất. Không được dùng định nghĩa chung thay cho bằng chứng thực tế của doanh nghiệp.',
  'Nếu knowledgeBase.framework là bank, đọc theo khung ngân hàng: tăng trưởng tín dụng và huy động; NII/NIM và chi phí vốn; CASA/LDR; chất lượng tài sản NPL, nợ nhóm 2, dự phòng và LLR; credit cost; CIR; CAR; ROA/ROE; P/B/BVPS nếu có. Không áp máy móc OCF/FCF như doanh nghiệp sản xuất.',
  'Nếu knowledgeBase.framework là corporate, đọc theo khung doanh nghiệp: tăng trưởng doanh thu/lợi nhuận; biên gộp/hoạt động/ròng; vốn lưu động; OCF/FCF và CAPEX; đòn bẩy; hiệu quả vốn ROE/ROA/ROIC; định giá và chu kỳ ngành nếu dữ liệu có.',
  state.mode==='deep'?'Ở chế độ Phân tích sâu, phải tận dụng tối đa dữ liệu thực tế có trong FinQuery và các nguồn web đáng tin cậy; không dừng phân tích chỉ vì thiếu một vài chỉ tiêu. Hãy viết như một equity research note có luận điểm trung tâm, bằng chứng nhiều kỳ, chất lượng lợi nhuận/tăng trưởng, yếu tố ngành-vĩ mô, catalyst, rủi ro, kỹ thuật và các kịch bản cần theo dõi. Mỗi đoạn phân tích chính phải vận hành tự nhiên theo chuỗi: luận điểm → bằng chứng → cơ chế tài chính/kinh tế → phản biện hoặc giới hạn → hàm ý cần theo dõi. Không lặp mẫu máy móc. Nếu academicContext có reference phù hợp, phải có ít nhất một đoạn liên hệ học thuật đúng phạm vi và một đoạn phản biện/counter-thesis. Nếu dữ liệu đủ, ưu tiên khoảng 1.800-3.000 từ thay vì trả lời ngắn.':'Ở chế độ nhanh, ưu tiên trực tiếp và đủ ý nhưng vẫn dùng dữ liệu thực tế thay vì nhận xét chung chung.',
  state.mode==='deep'?'Khi có URL báo cáo CTCK, sự kiện hoặc bài tin trong context, hãy đọc nội dung nguồn bằng URL Context nếu công cụ khả dụng; đồng thời dùng Google Search để tìm thông tin mới hơn, ưu tiên công bố doanh nghiệp, HOSE/HNX/SSC, cơ quan nhà nước, báo cáo CTCK và nguồn báo chí tài chính uy tín. Đối chiếu ngày dữ liệu và ngày xuất bản trước khi kết luận.':''
 ].join('\n');
}
function shouldSearchWeb(question){
 const s=norm(question);
 if(state.mode==='deep'||inferredQuestionMode(question)==='deep')return true;
 return /hom nay|phien nay|moi nhat|tin|nhnn|ngan hang nha nuoc|lai suat|vi mo|ty gia|lam phat|gdp|pmi|fdi|tai sao gia|vi sao gia|bien dong|su kien|chinh sach/.test(s);
}
function inferredQuestionMode(question){
 const s=norm(question);
 return /phan tich chuyen sau|phan tich toan dien|ho so nghien cuu|doi chieu nguon/.test(s)?'deep':null;
}
function geminiPrompt(question,agentContext=null,researchDossier=null){
 const deep=state.mode==='deep'||inferredQuestionMode(question)==='deep',sources=sourcesForLLM();
 const researchBrief=deep
  ?'YÊU CẦU PHÂN TÍCH SÂU: Hãy đọc toàn bộ dữ liệu liên quan trong FINQUERY CONTEXT, đặc biệt các dòng BCTC năm/quý, market, technical, scanner, sự kiện, báo cáo CTCK và tin tức. Sau đó dùng Google Search để bổ sung dữ liệu mới và dùng URL Context để đọc sâu các URL trong danh sách nguồn khi công cụ khả dụng. Ưu tiên nguồn gốc/primary source. Bài trả lời phải dài, chi tiết, có cấu trúc theo luận điểm, chỉ ra xu hướng nhiều kỳ, chất lượng tăng trưởng, rủi ro, catalyst và kịch bản. Mỗi phần phải nối số liệu với cơ chế thay vì chỉ liệt kê; phải có counter-thesis/điều kiện làm luận điểm sai. Nếu FINQUERY CONTEXT.academicContext có reference phù hợp, dùng reference đó như khung giải thích và nêu rõ giới hạn áp dụng; không trả lời kiểu vài đoạn tổng quát.'
  :'YÊU CẦU: Trả lời trực tiếp nhưng phải dựa trên số liệu và bằng chứng thực tế đang có.';
 return[
  'CÂU HỎI NGƯỜI DÙNG:\n'+question,
  'LỊCH SỬ GẦN NHẤT:\n'+JSON.stringify(state.history.slice(-8)),
  'FINQUERY CONTEXT:\n'+JSON.stringify(agentContext||buildLLMContext(question)),
  'NGUỒN ĐÃ CÓ TRONG TRANG - HÃY ĐỌC URL KHI PHÂN TÍCH SÂU:\n'+JSON.stringify(sources),
  researchDossier?('RESEARCH DOSSIER TỪ VÒNG NGHIÊN CỨU TRƯỚC:\n'+researchDossier):'',
  researchBrief,
  'Hãy trả lời câu hỏi dựa trên dữ liệu neo trước. Nếu có RESEARCH DOSSIER, coi đó là bản đồ bằng chứng chứ không phải kết luận bắt buộc: phải kiểm tra lại với FINQUERY CONTEXT, chỉ giữ luận điểm có bằng chứng và nêu rõ mâu thuẫn/độ không chắc chắn. Nếu FINQUERY CONTEXT có agent.validation, phải tuân theo cảnh báo validation và không sử dụng evidence đã bị loại. Web là lớp bổ sung/cross-check, không được ghi đè số BCTC hoặc giá neo của FinQuery nếu không chỉ rõ khác biệt thời điểm.'
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
  const urlRows=candidate.urlContextMetadata?.urlMetadata||candidate.url_context_metadata?.url_metadata||[];
  if(urlRows.length)readUrls=true;
  for(const row of urlRows){const url=row.retrievedUrl||row.retrieved_url||row.url;if(url)add(url,row.title||'Nguồn đã đọc');}
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
function mergeSources(...groups){
 const seen=new Set(),out=[];for(const group of groups)for(const item of group||[]){const url=safeExternalUrl(item?.url);if(!url||seen.has(url))continue;seen.add(url);out.push({...item,url});}
 return out.slice(0,12);
}
async function callResearchDossier(question,secret,model,agentContext){
 const sources=agentContext?.agent?.sourceHints||sourcesForLLM(),hasUrls=sources.some(x=>/^https?:\/\//i.test(x?.url||''));
 const prompt=[
  'Bạn là research analyst vòng 1 của Dolphin AI. Nhiệm vụ là lập HỒ SƠ BẰNG CHỨNG, không viết câu trả lời cuối cùng và không trình bày chuỗi suy nghĩ.',
  'CÂU HỎI: '+question,
  'FINQUERY CONTEXT: '+JSON.stringify(agentContext),
  'NGUỒN CÓ URL: '+JSON.stringify(sources),
  'Hãy đọc dữ liệu theo nhiều kỳ, dùng Google Search để bổ sung thông tin mới và URL Context để đọc nguồn đã có khi khả dụng.',
  'Trả về research dossier bằng tiếng Việt, tập trung vào: (1) phạm vi và độ mới dữ liệu; (2) các xu hướng tài chính quan trọng nhiều kỳ; (3) chất lượng tăng trưởng/lợi nhuận; (4) framework ngân hàng hoặc doanh nghiệp tương ứng; (5) academicContext nào thực sự phù hợp, cơ chế mà nghiên cứu đó gợi ý và giới hạn khi áp dụng sang doanh nghiệp/thị trường hiện tại; (6) market/technical/scanner; (7) sự kiện, tin, báo cáo CTCK và bối cảnh ngành-vĩ mô; (8) bằng chứng ủng hộ và phản bác các luận điểm; (9) mâu thuẫn dữ liệu; (10) dữ liệu còn thiếu; (11) danh sách 5-10 insight có giá trị nhất cho senior analyst.',
  'Chỉ ghi nhận dữ kiện, so sánh và bất định có thể kiểm chứng. Không đưa khuyến nghị mua/bán.'
 ].join('\n\n');
 const generation={maxOutputTokens:3200,temperature:.08,...(/^gemini-3(?:\.|-)/i.test(model)?{thinkingConfig:{thinkingLevel:'medium'}}:{})};
 const toolPlans=hasUrls?[[{googleSearch:{}},{urlContext:{}}],[{googleSearch:{}}],[]]:[[{googleSearch:{}}],[]];
 let payload=null,lastError=null;
 for(const tools of toolPlans){
  try{payload=await geminiGenerateResilient(secret,model,{systemInstruction:{parts:[{text:'Bạn là analyst nghiên cứu dữ liệu. Không tiết lộ chuỗi suy nghĩ; chỉ xuất hồ sơ bằng chứng có thể kiểm tra.'}]},contents:[{role:'user',parts:[{text:prompt}]}],generationConfig:generation,...(tools.length?{tools}:{})},52000,2);break;}
  catch(error){lastError=error;if(error?.name==='AbortError'||![400,403,404,429,500,502,503,504].includes(Number(error?.status)))throw error;}
 }
 if(!payload)throw lastError||new Error('Không tạo được research dossier.');
 const result=providerAnswer(payload);if(!result.text)throw new Error('Research dossier trống.');
 return{...result,model};
}
async function callGeminiModel(question,secret,model,allowSearch=true,agentContext=null,researchDossier=null){
 const deep=state.mode==='deep'||inferredQuestionMode(question)==='deep',search=allowSearch&&shouldSearchWeb(question),knownSources=agentContext?.agent?.sourceHints||sourcesForLLM(),readKnown=allowSearch&&deep&&knownSources.some(x=>/^https?:\/\//i.test(x?.url||''));
 const input=geminiPrompt(question,agentContext,researchDossier);
 const generation={maxOutputTokens:deep?7000:1800,temperature:deep?.16:.12,...(/^gemini-3(?:\.|-)/i.test(model)?{thinkingConfig:{thinkingLevel:deep?'medium':'low'}}:{})};
 const body=tools=>({systemInstruction:{parts:[{text:dolphinSystemInstruction()}]},contents:[{role:'user',parts:[{text:input}]}],generationConfig:generation,...(tools.length?{tools}:{})});
 const toolPlans=[];
 if(search&&readKnown)toolPlans.push([{googleSearch:{}},{urlContext:{}}]);
 if(search)toolPlans.push([{googleSearch:{}}]);
 else if(readKnown)toolPlans.push([{urlContext:{}}]);
 toolPlans.push([]);
 let payload=null,lastError=null;
 for(const tools of toolPlans){
  try{payload=await geminiGenerateResilient(secret,model,body(tools),deep?62000:36000,2);break;}
  catch(error){lastError=error;if(![400,403,404,429,500,502,503,504].includes(Number(error?.status)))throw error;}
 }
 if(!payload)throw lastError||new Error('Gemini chưa phản hồi.');
 const result=providerAnswer(payload);
 if(!result.text){const err=new Error('Gemini chưa trả về nội dung phân tích.');err.status=503;err.model=model;throw err;}
 state.geminiReady=true;state.lastGeminiError='';state.model=model;
 const sourceMode=result.searched&&result.readUrls?'NATIVE_WEB_URL_CONTEXT':result.searched?'NATIVE_WEB_SEARCH':result.readUrls?'URL_CONTEXT':'FINQUERY_GROUNDED';
 return{answer:result.text,provider:'Gemini',model,sourceMode,readUrls:result.readUrls,sources:result.sources,queries:result.queries,anchors:provenanceAnchors(),academicSources:(agentContext?.academicContext?.references||[]).slice(0,5)};
}
function auditDeepAnswer(answer,agentContext){
 const text=String(answer||'').trim(),paras=text.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean),words=(text.match(/[A-Za-zÀ-ỹ0-9]+/g)||[]).length;
 const sourceTag=/\[(?:BCTC|QUARTER|MARKET|SCANNER|NEWS|RESEARCH|WEB|ACADEMIC)\]/;
 const empirical=paras.filter(p=>/\d|%|tỷ|triệu|đồng|qoq|yoy|roe|roa|nim|npl|casa|ldr|cir/i.test(p)&&!/^#{1,4}\s/.test(p));
 const missingTags=empirical.filter(p=>!sourceTag.test(p));
 const refs=agentContext?.academicContext?.references||[],academicRequired=refs.length>0;
 const hasAcademic=!academicRequired||(/\[ACADEMIC\]/.test(text)&&refs.some(r=>{const key=norm(String(r.title||r.citation||'').split(/[·,(]/)[0]);return key&&norm(text).includes(key.split(' ')[0]);}));
 const normalized=norm(text),hasCounter=/tuy nhien|nguoc lai|phan bien|counter thesis|dieu kien.*sai|dieu kien.*yeu|luan diem.*yeu|rui ro.*luan diem|mat khac|han che/.test(normalized);
 const hasMechanism=/co che|vi |do |dan den|keo theo|truyen dan|dong luc|bien loi nhuan|chi phi von|von luu dong|don bay|thanh khoan|cung cau|lai suat/.test(normalized);
 const headings=(text.match(/^#{1,4}\s+/gm)||[]).length,invalid=/\bundefined\b|\bNaN\b/.test(text);
 const missingRatio=empirical.length?missingTags.length/empirical.length:0;
 let score=100;if(words<650)score-=20;if(empirical.length<2)score-=20;if(headings<3&&paras.length<7)score-=10;if(missingRatio>.25)score-=25;else if(missingRatio>0)score-=10;if(!hasCounter)score-=15;if(!hasMechanism)score-=10;if(!hasAcademic)score-=15;if(invalid)score-=35;
 score=Math.max(0,score);
 return{pass:score>=80&&words>=650&&empirical.length>=2&&!invalid&&missingRatio<=.25&&hasCounter&&hasMechanism&&hasAcademic,score,words,paragraphs:paras.length,empiricalParagraphs:empirical.length,missingEvidenceTags:missingTags.length,missingRatio:Number(missingRatio.toFixed(3)),academicRequired,hasAcademic,hasCounter,hasMechanism,headings,invalid};
}
async function repairDeepAnswer(question,answer,audit,secret,model,agentContext,researchDossier){
 const prompt=[
  'Bạn là senior editor vòng cuối của Dolphin AI. Hãy BIÊN TẬP lại câu trả lời, không tạo phân tích độc lập mới và không tiết lộ chuỗi suy nghĩ.',
  'CÂU HỎI: '+question,
  'BẢN NHÁP: '+answer,
  'QUALITY AUDIT: '+JSON.stringify(audit),
  'FINQUERY CONTEXT: '+JSON.stringify(agentContext),
  researchDossier?('RESEARCH DOSSIER: '+researchDossier):'',
  'Yêu cầu bắt buộc: giữ nguyên mọi số liệu đã được neo; không tự tính/thêm số mới nếu context không có. Mỗi đoạn có số liệu/nhận định thực chứng phải có tag nguồn phù hợp. Nếu academicContext có reference, dùng ít nhất một reference đúng phạm vi, nêu tác giả/năm, gắn [ACADEMIC] và nói rõ giới hạn áp dụng. Các đoạn chính phải nối luận điểm → bằng chứng → cơ chế → giới hạn/phản biện → hàm ý cần theo dõi một cách tự nhiên. Phải có counter-thesis hoặc điều kiện làm luận điểm yếu đi. Không biến tương quan thành nhân quả, không đưa khuyến nghị mua/bán.',
  'Giữ tiếng Việt tự nhiên, có chiều sâu nhưng tránh lặp ý, tránh câu sáo rỗng và tránh kéo dài chỉ để đủ chữ.'
 ].filter(Boolean).join('\n\n');
 const body={systemInstruction:{parts:[{text:dolphinSystemInstruction()}]},contents:[{role:'user',parts:[{text:prompt}]}],generationConfig:{maxOutputTokens:7000,temperature:.08,...(/^gemini-3(?:\.|-)/i.test(model)?{thinkingConfig:{thinkingLevel:'medium'}}:{})}};
 const payload=await geminiGenerateResilient(secret,model,body,62000,2),result=providerAnswer(payload);
 if(!result.text)throw new Error('Vòng biên tập chất lượng không trả về nội dung.');
 return result.text;
}
async function callLLM(question){
 let prepared=null;
 if(window.FinResearchAgent?.prepare){
  const requested=window.FinResearchAgent.resolveTargetSymbol?.(question)||'';
  if(requested&&requested!==state.symbol)renderGeminiStatus('Đang nạp dữ liệu '+requested+' theo câu hỏi…');
  prepared=await window.FinResearchAgent.prepare(question);
 }
 const secret=sessionSecret();
 if(!secret){const err=new Error('Dolphin chưa kết nối Gemini.');err.code='NO_GEMINI_KEY';throw err;}
 if(!state.modelCandidates.length||!state.geminiReady)await validateGemini(secret);
 const baseContext=buildLLMContext(question),sourceHints=sourcesForLLM();
 let agentContext=baseContext,agentAudit=null;
 if(window.FinResearchAgent?.run){
  try{
   const agentRun=await window.FinResearchAgent.run(question,{baseContext,sources:sourceHints,prepared});
   agentContext=agentRun?.context||baseContext;agentAudit=agentRun?.audit||null;
  }catch(error){
   agentContext={...baseContext,agent:{version:'FINQUERY_RESEARCH_AGENT_V1',status:'error',error:String(error?.message||error).slice(0,240)}};
  }
 }
 const candidates=modelPlan(state.mode);
 if(!candidates.length)throw new Error('Không tìm thấy Gemini Flash phù hợp.');
 const deep=state.mode==='deep'||inferredQuestionMode(question)==='deep';
 let dossier=null,dossierMeta=null;
 if(deep){
  try{
   renderGeminiStatus('Đang đọc toàn bộ dữ liệu liên quan và lập research dossier…');
   dossierMeta=await callResearchDossier(question,secret,candidates[0],agentContext);
   dossier=dossierMeta.text;
   renderGeminiStatus('Research dossier xong · đang tổng hợp như senior analyst…');
  }catch(error){
   if(error?.name==='AbortError')throw error;
   if(agentAudit)agentAudit.researchPass={status:'fallback',error:String(error?.message||error).slice(0,220)};
  }
 }
 let lastError;const attempted=[];
 for(let i=0;i<candidates.length;i++){
  const model=candidates[i];state.model=model;attempted.push(model);
  try{
   let answer=await callGeminiModel(question,secret,model,!dossier&&(deep||i===0),agentContext,dossier);
   let qualityAudit=deep?auditDeepAnswer(answer.answer,agentContext):null,qualityRepair={status:'not_needed'};
   if(deep&&qualityAudit&&!qualityAudit.pass){
    try{
     renderGeminiStatus('Đang rà soát chất lượng lập luận và biên tập vòng cuối…');
     const repaired=await repairDeepAnswer(question,answer.answer,qualityAudit,secret,model,agentContext,dossier);
     const repairedAudit=auditDeepAnswer(repaired,agentContext);
     if(repairedAudit.score>=qualityAudit.score){answer={...answer,answer:repaired};qualityRepair={status:'applied',before:qualityAudit.score,after:repairedAudit.score};qualityAudit=repairedAudit;}
     else qualityRepair={status:'kept_original',before:qualityAudit.score,after:repairedAudit.score};
    }catch(error){qualityRepair={status:'fallback',error:String(error?.message||error).slice(0,180)};}
   }
   return{...answer,agentAudit,qualityAudit,qualityRepair,researchPass:dossier?{status:'ok',model:dossierMeta?.model||candidates[0]}:{status:'fallback'},sources:mergeSources(dossierMeta?.sources,answer.sources),queries:[...new Set([...(dossierMeta?.queries||[]),...(answer.queries||[])])].slice(0,8)};
  }
  catch(error){
   lastError=error;state.lastGeminiError=String(error?.message||error);
   if(error?.name==='AbortError')throw error;
   const status=Number(error.status);
   if(status===401){state.geminiReady=false;throw error;}
   if(![403,404,429,500,502,503,504].includes(status))break;
   if(transientGemini(status)){state.geminiReady=true;renderGeminiStatus('Gemini '+model+' đang bận · chuyển model dự phòng…');}
  }
 }
 if(lastError&&transientGemini(lastError.status)){
  const err=new Error('Gemini đang quá tải tạm thời sau khi Dolphin đã retry và chuyển qua '+attempted.length+' model dự phòng. Khóa API vẫn kết nối.');
  err.status=lastError.status;err.code='GEMINI_TRANSIENT_EXHAUSTED';err.attemptedModels=attempted;throw err;
 }
 throw lastError||new Error('Gemini tạm thời chưa phản hồi.');
}
function inlineMarkdown(value){
 let out=esc(String(value||''));out=out.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');out=out.replace(/\[(BCTC|QUARTER|MARKET|SCANNER|NEWS|RESEARCH|WEB|ACADEMIC)\]/g,'<span class="ai-source-tag">$1</span>');return out;
}
function llmHTML(answer,meta={}){
 const lines=String(answer||'').trim().split(/\n/),blocks=[];let bullets=[];
 const flush=()=>{if(!bullets.length)return;blocks.push('<div class="research-case">'+bullets.map(x=>'<p>• '+inlineMarkdown(x)+'</p>').join('')+'</div>');bullets=[];};
 for(const rawLine of lines){const line=rawLine.trim();if(!line){flush();continue;}const h=line.match(/^#{1,4}\s+(.+)$/);if(h){flush();blocks.push('<h4>'+inlineMarkdown(h[1])+'</h4>');continue;}const b=line.match(/^[-*]\s+(.+)$/);if(b){bullets.push(b[1]);continue;}flush();blocks.push('<p>'+inlineMarkdown(line)+'</p>');}
 flush();
 const mode=meta.sourceMode==='NATIVE_WEB_URL_CONTEXT'?'FinQuery + Gemini + Web + đọc nguồn':meta.sourceMode==='NATIVE_WEB_SEARCH'?'FinQuery + Gemini + Web':meta.sourceMode==='URL_CONTEXT'?'FinQuery + Gemini + đọc nguồn':'FinQuery + Gemini';
 const sources=(meta.sources||[]).slice(0,6).map(s=>{const url=safeExternalUrl(s.url);return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.title||url)+'</a>':'';}).filter(Boolean);
 const academic=(meta.academicSources||[]).slice(0,5).map(s=>{const url=safeExternalUrl(s.url);return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer" title="'+esc(s.caveat||'')+'">'+esc(s.title||s.citation||url)+'</a>':'';}).filter(Boolean);
 const anchors=(meta.anchors||[]).map(a=>'<span class="ai-anchor"><b>'+esc(a.tag)+'</b>'+esc(a.label)+' · '+esc(String(a.asOf))+'</span>').join('');
 const qa=meta.qualityAudit?(' · kiểm định lập luận '+Math.round(meta.qualityAudit.score||0)+'/100'+(meta.qualityRepair?.status==='applied'?' · đã biên tập vòng cuối':'')):'';
 return '<section class="analysis-block"><div class="analysis-narrative">'+blocks.join('')+'</div>'+(anchors?'<div class="ai-provenance"><strong>Dấu vết dữ liệu</strong>'+anchors+'</div>':'')+(academic.length?'<div class="analysis-news"><strong>Khung học thuật tham chiếu</strong>'+academic.join('')+'<small>Khung học thuật dùng để giải thích cơ chế, không thay thế bằng chứng doanh nghiệp.</small></div>':'')+(sources.length?'<div class="analysis-news"><strong>Nguồn đối chiếu</strong>'+sources.join('')+'</div>':'')+'<small>'+esc(mode+' · '+modeLabel()+qa)+'</small></section>';
}
function nearBottom(box){return !box||box.scrollHeight-box.scrollTop-box.clientHeight<120;}
function scrollIfNeeded(box,wasNear=true){if(box&&wasNear)box.scrollTop=box.scrollHeight;}
function addUser(text){const box=$('research-ai-messages');if(!box)return;const was=nearBottom(box),a=document.createElement('article');a.className='research-ai-message user';a.innerHTML='<strong>Câu hỏi</strong><p>'+esc(text)+'</p>';box.append(a);scrollIfNeeded(box,was);}
function addAnalysis(result){const box=$('research-ai-messages');if(!box)return;const was=nearBottom(box),a=document.createElement('article');a.className='research-ai-message assistant analysis-result';a.innerHTML=result.html;box.append(a);scrollIfNeeded(box,was);return a;}
function addThinking(){return addAnalysis({html:'<div class="analysis-empty"><span class="loading-ring"></span><p>'+(state.mode==='deep'?'Dolphin đang đọc BCTC, market, research, tin và nguồn web trước khi lập luận…':'Dolphin đang phân tích '+esc(state.symbol||'mã đang xem')+'…')+'</p></div>'});}
function mountGeminiUI(){
 const drawer=$('research-ai');if(!drawer||$('dolphin-gemini-connect'))return;
 const box=document.createElement('section');box.id='dolphin-gemini-connect';box.className='dolphin-connect-card';
 box.innerHTML='<div class="dolphin-connect-head"><div><strong>Bật Dolphin AI thông minh</strong><small id="dolphin-gemini-status">Đang kiểm tra kết nối…</small></div><button id="dolphin-gemini-disconnect" class="dolphin-disconnect" type="button">Ngắt</button></div><div class="dolphin-mode-switch" aria-label="Chế độ AI"><button type="button" data-dolphin-mode="normal">⚡ Nhanh & tiết kiệm<small>Flash-Lite</small></button><button type="button" data-dolphin-mode="deep">✦ Phân tích sâu<small>Flash</small></button></div><div id="dolphin-gemini-guide" class="dolphin-connect-guide"><p><b>3 bước để bật AI:</b> lấy khóa miễn phí từ Google AI Studio, sao chép rồi kết nối.</p><div><a id="dolphin-gemini-get-key" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">1. Lấy khóa miễn phí ↗</a><button id="dolphin-gemini-paste" type="button">2. Dán khóa</button></div></div><div id="dolphin-gemini-form" class="dolphin-key-form"><input id="dolphin-gemini-key" type="password" autocomplete="off" spellcheck="false" placeholder="Dán khóa Gemini của Google"><button id="dolphin-gemini-save" type="button">3. Kết nối</button></div><small id="dolphin-gemini-note" class="dolphin-connect-note">Khóa chỉ giữ trong phiên trình duyệt này; không ghi vào GitHub.</small>';
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
 const secret=sessionSecret(),ready=Boolean(secret&&state.geminiReady),card=$('dolphin-gemini-connect'),status=$('dolphin-gemini-status'),form=$('dolphin-gemini-form'),guide=$('dolphin-gemini-guide'),disconnect=$('dolphin-gemini-disconnect'),note=$('dolphin-gemini-note');
 card?.classList.toggle('connected',ready);
 if(status)status.textContent=message||(ready?('Gemini phản hồi OK · '+(state.model||'model khả dụng')):(secret?'Key đã lưu nhưng Gemini chưa xác nhận generateContent.':'Chưa bật Gemini · làm 3 bước bên dưới'));
 if(form)form.hidden=Boolean(secret);if(guide)guide.hidden=Boolean(secret);if(disconnect)disconnect.hidden=!secret;
 if(note)note.textContent=ready?((state.model||'Gemini')+' · '+modeLabel()+' · dữ liệu tài chính lấy từ FinQuery.'):(secret?'Dolphin chỉ báo kết nối khi probe generateContent thực sự thành công.':'Khóa chỉ giữ trong phiên trình duyệt này; không ghi vào GitHub.');
 document.querySelectorAll('[data-dolphin-mode]').forEach(b=>b.classList.toggle('active',b.dataset.dolphinMode===state.mode));
}
async function connectGeminiFromUI(){
 const input=$('dolphin-gemini-key'),button=$('dolphin-gemini-save'),secret=String(input?.value||'').trim();if(!secret)return;
 if(button)button.disabled=true;renderGeminiStatus('Đang test generateContent thật với Google Gemini…');
 try{rememberSession(secret);const model=await validateGemini(secret);if(input)input.value='';renderGeminiStatus('Gemini phản hồi OK · '+model);}
 catch(error){state.geminiReady=false;state.lastGeminiError=String(error?.message||error);if(Number(error?.status)===401)forgetSession();if(input)input.value='';renderGeminiStatus('Không thể generateContent · '+state.lastGeminiError);}
 finally{if(button)button.disabled=false;}
}
async function refreshGeminiSession(){
 mountGeminiUI();const secret=sessionSecret();if(!secret)return;
 renderGeminiStatus('Đang kiểm tra lại generateContent…');
 try{const model=await validateGemini(secret);renderGeminiStatus('Gemini phản hồi OK · '+model);}
 catch(error){state.geminiReady=false;state.lastGeminiError=String(error?.message||error);renderGeminiStatus('Không thể generateContent · '+state.lastGeminiError);}
}
function ensureGlobalAILayer(){
 const body=document.body;if(!body)return;
 for(const id of ['ai-backdrop','research-ai','ai-fab']){const el=$(id);if(el&&el.parentElement!==body)body.append(el);}
}
function openDrawer(){ensureGlobalAILayer();const drawer=$('research-ai'),fab=$('ai-fab'),backdrop=$('ai-backdrop');if(!drawer)return false;if(backdrop)backdrop.hidden=false;drawer.hidden=false;requestAnimationFrame(()=>{backdrop?.classList.add('open');drawer.classList.add('open');});document.body.classList.add('dolphin-modal-open');mountGeminiUI();if(fab){fab.setAttribute('aria-expanded','true');fab.hidden=true;}setTimeout(()=>$('research-ai-question')?.focus(),100);return true;}
function closeDrawer(){const drawer=$('research-ai'),fab=$('ai-fab'),backdrop=$('ai-backdrop');if(!drawer)return;drawer.classList.remove('open');backdrop?.classList.remove('open');document.body.classList.remove('dolphin-modal-open');setTimeout(()=>{drawer.hidden=true;if(backdrop)backdrop.hidden=true;},160);if(fab){fab.setAttribute('aria-expanded','false');fab.hidden=false;}}
async function ask(question,preferredMode=null){
 const q=String(question||'').trim();if(!q||state.busy)return;
 const nextMode=preferredMode||inferredQuestionMode(q);if(nextMode)setAIMode(nextMode);
 state.lastQuestion=q;openDrawer();addUser(q);state.busy=true;state.currentController=new AbortController();
 const send=$('research-ai-send');if(send){send.disabled=false;send.textContent='Dừng';send.dataset.busy='1';}const waiting=addThinking();
 try{
  if(['concept','multiConcept'].includes(classify(q))){
   const local=analyze(q);waiting?.remove();addAnalysis(local);
   state.history.push({role:'user',content:q},{role:'assistant',content:'Đã trả lời từ định nghĩa được kiểm chứng trong FinQuery.'});
   return;
  }
  const payload=await callLLM(q);waiting?.remove();addAnalysis({html:llmHTML(payload.answer,payload)});
  state.history.push({role:'user',content:q},{role:'assistant',content:String(payload.answer).slice(0,2400)});state.history=state.history.slice(-8);renderGeminiStatus();
 }catch(error){
  waiting?.remove();if(error?.name==='AbortError'){addAnalysis({html:'<div class="analysis-empty">Đã dừng phân tích.</div>'});return;}
  const local=analyze(q),noKey=error?.code==='NO_GEMINI_KEY',transient=error?.code==='GEMINI_TRANSIENT_EXHAUSTED'||transientGemini(error?.status),detail=String(error?.message||'').slice(0,320);
  local.html='<div class="analysis-empty">'+(noKey?'Gemini chưa kết nối. Muốn bật AI, làm 3 bước ở phía trên. ':transient?'Gemini đang quá tải tạm thời; Dolphin đã tự retry và đổi model nhưng chưa nhận được phản hồi. FinQuery local đang tiếp tục. ':'Gemini lỗi: '+esc(detail||'không có phản hồi')+' · FinQuery local đang tiếp tục. ')+'</div>'+local.html;addAnalysis(local);
  if(error?.message&&!noKey){if(!transient)state.geminiReady=false;state.lastGeminiError=detail;renderGeminiStatus(transient?'Gemini đang bận · khóa vẫn kết nối · câu hỏi tiếp theo sẽ tự retry/failover.':detail);}
 }finally{state.busy=false;state.currentController=null;if(send){send.disabled=false;send.textContent='Phân tích';delete send.dataset.busy;}}
}
function sync(symbol){const next=symbol||'';if(state.symbol&&next&&next!==state.symbol)state.history=[];state.symbol=next;const title=$('research-ai-title'),fab=$('ai-fab');if(title)title.textContent=`Phân tích chuyên sâu · ${state.symbol||'VN100'}`;if(fab)fab.dataset.symbol=state.symbol||'VN100';}
window.FinQueryAI={version:DOLPHIN_VERSION,sync,ask,analyze,open:openDrawer,close:closeDrawer,ensureGlobalLayer:ensureGlobalAILayer,connect:connectGeminiFromUI,disconnect:()=>{forgetSession();renderGeminiStatus();},setMode:setAIMode,geminiStatus:()=>({keyStored:Boolean(sessionSecret()),connected:Boolean(sessionSecret()&&state.geminiReady),mode:state.mode,model:state.model||null,error:state.lastGeminiError||null})};
const form=$('research-ai-form'),input=$('research-ai-question'),sendButton=$('research-ai-send');
form?.addEventListener('submit',e=>{e.preventDefault();if(state.busy){state.currentController?.abort();return;}const q=input.value.trim();if(q){input.value='';input.style.height='';ask(q);}});
input?.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(input.scrollHeight,130)+'px';});
input?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&window.innerWidth>600){e.preventDefault();form?.requestSubmit();}});
document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.aiPrompt||'',b.dataset.aiMode||null)));
$('ai-fab')?.addEventListener('click',()=>{if($('research-ai')?.hidden)openDrawer();else closeDrawer();});$('ai-close')?.addEventListener('click',closeDrawer);$('ai-backdrop')?.addEventListener('click',closeDrawer);document.querySelector('a[href="#research-ai"]')?.addEventListener('click',e=>{e.preventDefault();openDrawer();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('research-ai')?.hidden)closeDrawer();});
restoreAIMode();sync(window.FinancialMarket?.context?.().symbol||new URLSearchParams(location.search).get('symbol')||'MBB');ensureGlobalAILayer();mountGeminiUI();void refreshGeminiSession();
})();