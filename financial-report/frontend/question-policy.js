(function(root){'use strict';
// Shared, deterministic question policy for both online and local fallback.
const STOP=new Set(('la gi nghia la gi dinh nghia kh per ten em anh chi ban minh toi chung ta cho biet giai thich phan tich danh gia tinh hinh bao nhieu hien tai hom nay moi nhat gan day cua ve voi theo va tai sao vi sao nhu the nao may duoc ko khong o trong luc khi gia tri so lieu chi so cua doanh nghiep cong ty co phieu ma chung khoan').split(' '));
const TERMS_STOP=new Set([...STOP,'tin','tuc','su','kien','moi','cap','nhat','thi','truong','thong','bao','thong','tin','lien','quan','ngay','nay','du','bao','nam','quy']);
function norm(s){return String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase().replace(/[^a-z0-9+]+/g,' ').trim();}
function has(s,word){return (' '+s+' ').includes(' '+norm(word)+' ');}
function periodInfo(q){
 const s=norm(q),years=[...new Set((s.match(/\b20\d\d\b/g)||[]))],qs=[],q1=/\bquy\s*([1-4])\s*(20\d\d)\b/g,q2=/\b(20\d\d)\s*(?:q|quy)\s*([1-4])\b/g;
 let m;while((m=q1.exec(s)))qs.push(m[2]+'-Q'+m[1]);while((m=q2.exec(s)))qs.push(m[1]+'-Q'+m[2]);
 return{years,quarters:[...new Set(qs)],isQuarter:/\bquy\b|\bq[1-4]\b/.test(s),hasPeriod:years.length>0||qs.length>0};
}
function route(question,ranked=[]){
 const s=norm(question),strong=(ranked||[]).filter(x=>x.score>=25);
 const definition=/\bla gi\b|\bnghia la gi\b|\bkhai niem\b|\bdinh nghia\b|\bcong thuc\b|\bcach tinh\b|\bdo cai gi\b|\bthe hien gi\b/.test(s);
 const amount=/\bbao nhieu\b|\bgia tri\b|\bso lieu\b|\bmuc nao\b|\bmuc bao nhieu\b|\bhien tai\b|\bky nay\b/.test(s);
 const comparison=/\bso sanh\b|\bkhac gi\b|\bkhac nhau\b|\bky truoc\b|\bcung ky\b|\bqoq\b|\byoy\b|\bversus\b|\bvs\b/.test(s);
 const news=/\btin tuc\b|\btin moi\b|\btin ve\b|\btin doanh nghiep\b|\bsu kien\b|\bcong bo thong tin\b|\bbai bao\b|\bnews\b|\bbao cao ctck\b/.test(s);
 const forecast=/\bdu bao\b|\bforecast\b|\bt[+]3\b|\bt[+]4\b|\bt[+]5\b|\bxac suat tang\b|\bgia muc tieu\b/.test(s);
 const risk=/\brui ro\b|\bcanh bao\b|\bbat thuong\b|\bye[u]? diem\b|\bcang thang\b/.test(s);
 const macro=/\bnhnn\b|\bngan hang nha nuoc\b|\blai suat\b|\bovernight\b|\bomo\b|\bty gia\b|\blam phat\b|\bgdp\b|\bpmi\b|\bfdi\b|\bvi mo\b|\besg\b|\bcung tien\b|\bm2\b|\bkinh te vi mo\b/.test(s);
 const technical=/\bky thuat\b|\brsi\b|\bmacd\b|\bbollinger\b|\batr\b|\badx\b|\bsupertrend\b|\bvwap\b|\bchi bao\b|\bscanner\b|\bchien luoc\b|\bquet ma\b/.test(s);
 const financial=/\bbctc\b|\btai chinh\b|\bdoanh thu\b|\bloi nhuan\b|\bdong tien\b|\bvon chu\b|\btai san\b|\bno phai tra\b|\bno xau\b|\bphai thu\b|\bton kho\b|\bthanh khoan\b|\bdu no\b|\bbao cao tai chinh\b/.test(s);
 const movement=/\bgia co phieu\b|\bgia chung khoan\b|\bphien hom nay\b|\bphien nay\b|\bdiem so\b|\bdong luc phien\b|\bbien dong gia\b|\btang gia\b|\bgiam gia\b|\bvi sao\b|\bnguyen nhan\b/.test(s);
 const deep=/\bphan tich chuyen sau\b|\bphan tich toan dien\b|\bho so nghien cuu\b|\bdanh gia tong the\b|\btong hop\b|\bdeep dive\b/.test(s);
 const time=periodInfo(question);
 // A compound question must not silently answer only one of several named concepts.
 if(strong.length>=2&&(definition||comparison||/\bva\b|\bhay\b/.test(s)))return'multiConcept';
 if(definition)return'concept';
 if(deep)return'memo';
 if(forecast)return'forecast';
 if(news)return'news';
 if(risk)return'risk';
 if(macro)return'macro';
 if(comparison&&(financial||strong.length))return'compare';
 if(amount&&strong.length&&!movement)return'metric';
 if(amount&&financial)return'metric';
 if(technical)return'technical';
 if(movement)return'movement';
 if(financial)return'financial';
 if(strong.length)return'concept';
 if(time.hasPeriod&&amount)return'metric';
 return'unknown';
}
function topicTokens(q,symbol=''){
 const ignore=new Set(TERMS_STOP),ticker=norm(symbol);
 return[...new Set(norm(q).split(' ').filter(t=>t.length>=3&&!ignore.has(t)&&t!==ticker&&!/^20\d\d$/.test(t)&&!/^q[1-4]$/.test(t)))];
}
function scoreText(query,content){
 const terms=topicTokens(query),hay=' '+norm(content)+' ';
 if(!terms.length)return 0;
 const matches=terms.filter(t=>hay.includes(' '+t+' ')).length;
 return matches/terms.length;
}
function searchRows(question,data,{minCoverage=0.6,limit=8}={}){
 const terms=topicTokens(question),out=[];
 if(!terms.length||!data)return[];
 for(const section of data.sections||[])for(const row of section.rows||[]){
  const label=' '+norm(row.label)+' ',matched=terms.filter(t=>label.includes(' '+t+' ')).length,score=matched/terms.length;
  // Do not match "total assets" to a generic row sharing only "assets".
  if(score<minCoverage||matched<Math.min(2,terms.length))continue;
  out.push({row,score,section:section.id||''});
 }
 return out.sort((a,b)=>b.score-a.score||String(a.row.label).length-String(b.row.label).length).slice(0,limit);
}
function selectNews(question,items,{symbol='',companyOnly=false,limit=8}={}){
 const s=norm(question),generic=/\btin\b|\bnews\b|\bsu kien\b|\bcong bo\b/.test(s),topic=topicTokens(question,symbol);
 // Common company names in the query are identification, not topical matching requirements.
 const out=[];
 for(const row of Array.isArray(items)?items:[]){
  const symbols=Array.isArray(row.symbols)?row.symbols.map(x=>String(x).toUpperCase()):[];
  const companyHit=Boolean(symbol)&&(symbols.includes(String(symbol).toUpperCase())||(!symbols.length&&has(norm(row.title),symbol)));
  if(companyOnly&&!companyHit)continue;
  const text=(row.title||'')+' '+(row.summary||'')+' '+(Array.isArray(row.topics)?row.topics.join(' '):'');
  const matched=topic.filter(t=>(' '+norm(text)+' ').includes(' '+t+' ')).length;
  const topical=topic.length?matched/topic.length:0;
  if(topic.length&&topical===0)continue;
  if(!topic.length&&!generic)continue;
  if(!topic.length&&companyOnly&&!companyHit)continue;
  out.push({...row,_relevance:topical*100+(companyHit?10:0)});
 }
 return out.sort((a,b)=>b._relevance-a._relevance||Date.parse(b.publishedAt||0)-Date.parse(a.publishedAt||0)).slice(0,limit).map(({_relevance,...row})=>row);
}
function priceQuality(quote,symbol='',question='',now=new Date()){
 if(!quote||!Number.isFinite(Number(quote.price))||Number(quote.price)<=0)return{usable:false,reason:'Chưa có giá hợp lệ'};
 if(symbol&&quote.symbol&&String(quote.symbol).toUpperCase()!==String(symbol).toUpperCase())return{usable:false,reason:'Dữ liệu giá không đúng mã'};
 const raw=quote.sourceTime||quote.collectedAt,ts=Date.parse(raw||'');
 if(!Number.isFinite(ts)||ts>now.getTime()+5*60000)return{usable:false,reason:'Thiếu hoặc sai thời gian giá'};
 const fmt=(d)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
 const today=fmt(now),snapshot=fmt(new Date(ts)),s=norm(question);
 // A quote from an earlier date may be displayed only as a historical snapshot.
 const wantsCurrent=/\bhom nay\b|\bphien nay\b|\btrong phien\b|\brealtime\b|\blive\b/.test(s);
 const old=wantsCurrent&&today!==snapshot;
 return{usable:!old,reason:old?'Chưa có snapshot hợp lệ cho phiên đang hỏi':'',asOf:snapshot,sourceTime:raw,historical:today!==snapshot};
}
root.FinQueryQuestionPolicy={version:'QUESTION_POLICY_V1',norm,route,periodInfo,topicTokens,scoreText,searchRows,selectNews,priceQuality};
if(typeof module!=='undefined'&&module.exports)module.exports=root.FinQueryQuestionPolicy;
})(typeof window==='undefined'?globalThis:window);
