(()=>{"use strict";
const $=s=>document.querySelector(s);
const finite=x=>x!==null&&x!==undefined&&x!==""&&Number.isFinite(Number(x));
const pct=(x,d=0)=>finite(x)?`${(+x*100).toFixed(d)}%`:"—";
const textMap=new Map([
  ["T+5 expert contribution","Đóng góp mô hình · T+5"],
  ["Không có event mới trong cửa sổ PIT hiện tại. “Không có tin” không bị quy đổi thành neutral sentiment.","Chưa ghi nhận sự kiện mới đáng chú ý trong cửa sổ dữ liệu hiện tại."],
  ["Không có rumor claim đủ điều kiện trong cửa sổ hiện tại. Missing rumor không được coi là neutral signal.","Chưa ghi nhận thông tin lan truyền đủ điều kiện để theo dõi."],
  ["Không có expert contribution đủ điều kiện.","Chưa có thành phần bổ sung đủ mạnh để đóng góp vào dự báo này."],
  ["Horizon chưa vượt price-validation gate; contribution không được dùng để diễn giải một mức giá chưa hợp lệ.","Horizon này chưa đủ điều kiện để công bố mức giá dự báo."],
  ["Chưa validate","Chưa đủ điều kiện"],
  ["Price gate chưa PASS","Dữ liệu chưa đạt chuẩn công bố"],
  ["Historical T0 replay drilldown","Kiểm tra lại dự báo trong quá khứ"],
  ["Adjusted comparable","Giá so sánh điều chỉnh"],
  ["Actual raw","Giá thực tế"],
  ["Actual return","Biến động thực tế"],
  ["Origin raw","Giá tại T0"],
  ["Expected","Dự báo"],
  ["Prior 20","Động lượng 20 phiên"],
  ["Breadth 20","Độ rộng thị trường 20 phiên"],
  ["News / rumor","Tin / thông tin lan truyền"],
  ["Flow available","Dữ liệu dòng tiền"],
  ["Rank IC","IC xếp hạng"],
  ["Top-bottom spread","Chênh lệch nhóm cao-thấp"],
  ["Scenario MAE skill","Cải thiện sai số MAE"],
  ["Q20–Q80 coverage","Độ phủ Q20–Q80"],
  ["Brier skill","Chất lượng xác suất"],
  ["Price route","Nguồn giá"],
  ["VNStock primary","VNStock"],
  ["Current HOSE coverage","Độ phủ HOSE hiện tại"],
  ["Event corpus","Kho sự kiện"],
  ["Flow archive","Dữ liệu dòng tiền"],
  ["Accounting PIT","Dữ liệu BCTC theo thời điểm"],
  ["Model gates","Kiểm định mô hình"],
  ["Model promotion","Phạm vi dự báo được duyệt"]
]);
function cleanText(s){
  if(!s)return s;
  let t=s;
  for(const[a,b]of textMap)t=t.split(a).join(b);
  t=t.replace(/P\(tăng\) chưa vượt direction gate/g,"xác suất hướng chưa đủ độ tin cậy")
     .replace(/Direction gate REVIEW/g,"Chưa đủ độ tin cậy")
     .replace(/Expected return/g,"Biến động kỳ vọng")
     .replace(/Calibration n/g,"Mẫu hiệu chỉnh")
     .replace(/Adjusted close/g,"Giá điều chỉnh")
     .replace(/Raw close/g,"Giá đóng cửa")
     .replace(/Volume/g,"Khối lượng")
     .replace(/direct forecast/g,"dự báo")
     .replace(/direct T\+1…T\+5/g,"T+1…T+5")
     .replace(/Active:/g,"Thành phần:")
     .replace(/price PASS/g,"Giá PASS")
     .replace(/price REVIEW/g,"Giá REVIEW")
     .replace(/direction PASS/g,"Hướng PASS")
     .replace(/direction REVIEW/g,"Hướng REVIEW")
     .replace(/Expert output/g,"Dự báo thành phần")
     .replace(/cal n=/g,"mẫu=")
     .replace(/sealed n=/g,"mẫu OOS=")
     .replace(/Without /g,"Loại ")
     .replace(/Current /g,"Hiện tại ")
     .replace(/immutable validated snapshot/g,"snapshot đã kiểm định")
     .replace(/period statements excluded without publication timestamp/g,"chưa dùng số liệu kỳ khi thiếu thời điểm công bố")
     .replace(/numerical enabled/g,"đã bật dữ liệu định lượng")
     .replace(/current symbols/g,"mã hiện tại")
     .replace(/articles/g,"bài")
     .replace(/official/g,"chính thức")
     .replace(/rumor/g,"lan truyền")
     .replace(/foreign/g,"khối ngoại")
     .replace(/prop/g,"tự doanh")
     .replace(/checks/g,"kiểm tra")
     .replace(/price T\+h:/g,"T+h:");
  return t;
}
function polishNode(el){
  if(!el||el.dataset?.polishLock==="1")return;
  const leaves=el.matches?.(".empty,#summary,#expertMeta,#btMeta,.sourceCard span,.sourceCard small,.forecastCard small,.forecastCard strong,.metric span,.metric small,#btDetail .eyebrow,#btDetail .metric span,#btDetail .metric small,#ablation .metric span,#tooltip span,#tooltip strong,#tooltip b,#status,#chartTitle")?[el]:[...el.querySelectorAll?.(".empty,#summary,#expertMeta,#btMeta,.sourceCard span,.sourceCard small,.forecastCard small,.forecastCard strong,.metric span,.metric small,#btDetail .eyebrow,#btDetail .metric span,#btDetail .metric small,#ablation .metric span,#tooltip span,#tooltip strong,#tooltip b,#status,#chartTitle")||[]];
  for(const x of leaves){
    if(x.children.length===0){const v=cleanText(x.textContent);if(v!==x.textContent)x.textContent=v}
  }
  const title=$("#driverTitle");if(title&&/^T\+\d+ expert contribution$/.test(title.textContent||""))title.textContent=(title.textContent||"").replace(/T\+(\d+) expert contribution/,"Đóng góp mô hình · T+$1");
}
function polishSummary(){
  const s=$("#summary");if(!s)return;
  let t=s.textContent||"";
  t=t.replace(/; q20–q80 /gi," · vùng dự báo ").replace(/; khoảng q20–q80 /gi," · vùng dự báo ");
  t=t.replace(/Full model T\+5 /g,"T+5 dự kiến ").replace(/VMEWS đang RED\. Risk chỉ override stance, không sửa numerical forecast\./g,"Rủi ro hệ thống đang ở mức cao.");
  t=t.replace(/T\+5 chưa vượt đầy đủ ranking \+ distribution \+ generalization gate\. Giá dự báo bị ẩn thay vì nội suy hoặc giả lập\./g,"T+5 hiện chưa đủ điều kiện để công bố mức giá dự báo.");
  t=cleanText(t);if(t!==s.textContent)s.textContent=t;
}
function refresh(){polishNode(document.body);polishSummary()}
async function renderMethodProof(){
  const box=$("#methodProof");if(!box)return;
  try{
    const [blind,embargo,model]=await Promise.all([
      fetch("./data/blind-holdout-gate-v12.json",{cache:"no-store"}).then(r=>r.json()),
      fetch("./data/embargo-gate-v12.json",{cache:"no-store"}).then(r=>r.json()),
      fetch("./data/forecast-model-v12.json",{cache:"no-store"}).then(r=>r.json())
    ]);
    const hs=embargo.horizons||[];
    const future=Math.max(0,...hs.map(x=>+(x.walkForwardChronology?.futureRowsUsedForTraining||0)),...hs.map(x=>+(x.walkForwardChronology?.futureMetaRowsUsedForTraining||0)),...hs.map(x=>+(x.walkForwardChronology?.futureCalibrationRowsUsedForTraining||0)));
    const holdoutRows=Object.values(blind.horizons||{}).map(x=>+(x.holdout?.rows||0)).filter(Number.isFinite);
    const direct=(model.promotion?.directPriceHorizons||[]).join(" · ");
    box.innerHTML=`
      <article class="proofCard"><span>Nhìn trước tương lai</span><b>${future===0?"0 dòng":"CẦN KIỂM TRA"}</b><small>train · meta · calibration</small></article>
      <article class="proofCard"><span>Sealed holdout</span><b>${blind.status||"—"}</b><small>${holdoutRows.length?Math.min(...holdoutRows).toLocaleString("vi-VN")+"+ mẫu / horizon":"T+1 → T+5"}</small></article>
      <article class="proofCard"><span>Walk-forward & embargo</span><b>${embargo.status||"—"}</b><small>label maturity theo từng T+h</small></article>
      <article class="proofCard"><span>Giá được phát hành</span><b>${direct?`T+${direct.replace(/ · /g," · T+")}`:"—"}</b><small>5 horizon kiểm định độc lập</small></article>`;
  }catch(e){box.innerHTML='<div class="empty">Chưa tải được bằng chứng kiểm định.</div>'}
}
function installObserver(){
  let queued=false;
  const obs=new MutationObserver(()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;refresh()})});
  obs.observe(document.body,{subtree:true,childList:true,characterData:true});
}
function installResponsiveFix(){
  if(document.getElementById("v12PolishResponsive"))return;
  const style=document.createElement("style");
  style.id="v12PolishResponsive";
  style.textContent='@media(max-width:430px){.top{gap:8px}.brand{font-size:10px;letter-spacing:.055em;min-width:0;flex:1 1 auto}.topMeta{min-width:0;max-width:145px;flex:0 1 145px}.topMeta .badge{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis}}';
  document.head.appendChild(style);
}
function init(){installResponsiveFix();refresh();renderMethodProof();installObserver();document.documentElement.classList.add("uiReady")}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
