(()=>{
'use strict';
const PREF='vmews-lang';
let lang=localStorage.getItem(PREF)||'en';
if(!['en','vi'].includes(lang))lang='en';
const original=new WeakMap();
let applying=false;

const D={
'Vietnam Market Early Warning System':['Vietnam Market Risk Monitor','Hệ thống cảnh báo rủi ro thị trường Việt Nam'],
'Risk Radar':['Radar','Radar'],
'Analyze':['Analyze','Phân tích'],
'Validate':['Validate','Kiểm tra'],
'Governance':['Notes','Ghi chú'],
'RISK MANAGER':['RISK MANAGER','QUẢN TRỊ RỦI RO'],
'VIETNAM EQUITY RISK · EARLY WARNING':['VIETNAM EQUITY RISK MONITOR','THEO DÕI RỦI RO CỔ PHIẾU VIỆT NAM'],
'Detect deterioration.':['Spot rising risk.','Phát hiện rủi ro tăng.'],
'Act before losses accelerate.':['Act before losses deepen.','Xử lý trước khi lỗ sâu hơn.'],
'VMEWS is a risk-monitoring system for Vietnamese equities. It does not predict a target price and it does not issue buy/sell calls. It identifies deteriorating risk states, explains the evidence, checks whether similar states historically preceded deep drawdowns, and translates the result into risk-control actions.':['VMEWS tracks risk in Vietnamese stocks. It does not give price targets or buy/sell calls. It shows which names need attention, why risk is rising, what happened in similar past cases, and what controls to review.','VMEWS theo dõi rủi ro của cổ phiếu Việt Nam. Hệ thống không đưa giá mục tiêu hay khuyến nghị mua/bán. Hệ thống cho biết mã nào cần chú ý, vì sao rủi ro tăng, các trường hợp tương tự trong quá khứ đã diễn biến thế nào và cần xem lại biện pháp kiểm soát nào.'],
'1 · DETECT':['1 · DETECT','1 · PHÁT HIỆN'],
'2 · EXPLAIN':['2 · EXPLAIN','2 · GIẢI THÍCH'],
'3 · VALIDATE':['3 · VALIDATE','3 · KIỂM TRA'],
'4 · ACT':['4 · ACT','4 · XỬ LÝ'],
'Which names require attention?':['Which names need attention?','Mã nào cần chú ý?'],
'What is driving the warning?':['Why is risk rising?','Vì sao rủi ro tăng?'],
'Did similar states precede drawdowns?':['What happened in similar past cases?','Các trường hợp tương tự trước đây ra sao?'],
'What should risk management review?':['What should the risk team review?','Bộ phận rủi ro cần xem lại gì?'],
'PRICE SOURCE':['PRICE DATA','DỮ LIỆU GIÁ'],
'Yahoo Finance EOD · verified production feed':['Yahoo Finance · daily close','Yahoo Finance · giá đóng cửa ngày'],
'FUNDAMENTALS':['FUNDAMENTALS','CƠ BẢN'],
'Vnstock · when available':['Vnstock · when available','Vnstock · khi có dữ liệu'],
'MODEL DESIGN':['MODEL','MÔ HÌNH'],
'Point-in-time · No look-ahead':['As-of-date · No future data','Theo ngày · Không dùng dữ liệu tương lai'],
'OUTPUT':['USE','MỤC ĐÍCH'],
'Risk controls · Not trading signals':['Risk review · No trade signal','Kiểm soát rủi ro · Không phải tín hiệu giao dịch'],
'RISK MANDATE':['KEY QUESTIONS','CÂU HỎI CHÍNH'],
'What this system is designed to answer':['What the system checks','Hệ thống kiểm tra gì'],
'Is market or single-name risk deteriorating?':['Is risk rising?','Rủi ro có đang tăng không?'],
'Is the warning supported by multiple independent evidence modules?':['Do several signals point the same way?','Có nhiều tín hiệu cùng cho thấy rủi ro không?'],
'What happened after comparable historical states?':['What happened in similar past cases?','Các trường hợp tương tự trước đây diễn biến thế nào?'],
'Should exposure, concentration, monitoring or escalation controls be reviewed?':['Should exposure or monitoring be reviewed?','Có cần xem lại mức độ nắm giữ hoặc cách theo dõi không?'],
'Composite scores are risk indices, not probabilities. Historical analog event rates are empirical evidence from matched past states, not guaranteed forecasts.':['Scores are risk indicators, not probabilities. Historical match rates describe past cases; they are not forecasts.','Điểm số là chỉ báo rủi ro, không phải xác suất. Tỷ lệ lịch sử chỉ mô tả các trường hợp tương tự trong quá khứ, không phải dự báo.'],
'RISK MANAGER CONSOLE':['RISK CONSOLE','BẢNG THEO DÕI RỦI RO'],
'Detect → Explain → Validate → Act':['Detect → Explain → Check → Act','Phát hiện → Giải thích → Kiểm tra → Xử lý'],
'Start with the current risk radar. Investigate only the names that need attention, validate the warning on point-in-time history, then map it into a documented risk-control response.':['Start with the radar. Review names that need attention, check past evidence, then decide what risk control to review.','Bắt đầu từ radar. Xem các mã cần chú ý, kiểm tra dữ liệu quá khứ, sau đó xác định biện pháp kiểm soát cần xem lại.'],
'Initializing…':['Loading…','Đang tải…'],
'DETECT':['DETECT','PHÁT HIỆN'],
'EXPLAIN':['EXPLAIN','GIẢI THÍCH'],
'VALIDATE':['CHECK','KIỂM TRA'],
'ACT':['ACT','XỬ LÝ'],
'Market + watchlist':['Market + watchlist','Thị trường + danh sách theo dõi'],
'Drivers + evidence':['Main drivers','Nguyên nhân chính'],
'Replay + holdout':['History + test','Lịch sử + kiểm tra'],
'Risk controls':['Risk controls','Kiểm soát rủi ro'],
'STEP 01 · DETECT':['STEP 01 · DETECT','BƯỚC 01 · PHÁT HIỆN'],
'What requires attention now?':['What needs attention now?','Hiện tại cần chú ý gì?'],
'RED and YELLOW are pre-drawdown warning states. ACTIVE DRAWDOWN is separated because loss containment is operationally different from early warning.':['RED and YELLOW are warning states. ACTIVE DRAWDOWN means the loss is already large and needs separate handling.','ĐỎ và VÀNG là trạng thái cảnh báo. ĐANG GIẢM SÂU nghĩa là mức giảm đã lớn và cần xử lý riêng.'],
'VNINDEX RISK REGIME':['VNINDEX RISK','RỦI RO VNINDEX'],
'LOADING':['LOADING','ĐANG TẢI'],
'Requesting point-in-time market regime…':['Loading market risk…','Đang tải rủi ro thị trường…'],
'RISK PRIORITY':['PRIORITY','ƯU TIÊN'],
'Waiting for watchlist':['Waiting for data','Đang chờ dữ liệu'],
'The radar will surface the highest-risk names first.':['Highest-risk names appear first.','Mã có rủi ro cao hơn sẽ hiện trước.'],
'MONITORED NAMES':['WATCHLIST','DANH SÁCH THEO DÕI'],
'Refresh risk radar':['Refresh','Làm mới'],
'Up to 8 names/request · Vnstock request protection':['Up to 8 names per request','Tối đa 8 mã mỗi lần'],
'RED · ESCALATE':['RED · REVIEW NOW','ĐỎ · XEM NGAY'],
'high pre-drawdown risk':['high risk','rủi ro cao'],
'YELLOW · WATCH':['YELLOW · WATCH','VÀNG · THEO DÕI'],
'deterioration detected':['risk is rising','rủi ro đang tăng'],
'GREEN · NORMAL':['GREEN · NORMAL','XANH · BÌNH THƯỜNG'],
'no escalation threshold':['no warning threshold','chưa chạm ngưỡng cảnh báo'],
'ACTIVE DRAWDOWN':['ACTIVE DRAWDOWN','ĐANG GIẢM SÂU'],
'loss containment mode':['manage current loss','kiểm soát mức lỗ hiện tại'],
'CURRENT RISK RANKING':['CURRENT RISK RANKING','XẾP HẠNG RỦI RO HIỆN TẠI'],
'Escalation queue':['Priority list','Danh sách ưu tiên'],
'Risk score ≠ crash probability':['Risk score is not crash probability','Điểm rủi ro không phải xác suất giảm giá'],
'Security':['Security','Mã'],
'Status':['Status','Trạng thái'],
'Risk':['Risk','Rủi ro'],
'Close / live':['Close / live','Đóng cửa / hiện tại'],
'5D move':['5D move','Biến động 5 ngày'],
'Technical':['Technical','Kỹ thuật'],
'Analog':['History','Lịch sử'],
'Market':['Market','Thị trường'],
'Module coverage':['Data coverage','Độ phủ dữ liệu'],
'Escalation evidence':['Main reason','Lý do chính'],
'Starting risk radar…':['Loading risk data…','Đang tải dữ liệu rủi ro…'],
'STEP 02 · EXPLAIN':['STEP 02 · ANALYZE','BƯỚC 02 · PHÂN TÍCH'],
'Investigate one security':['Analyze one security','Phân tích một mã'],
'Use current data or freeze the model at a historical as-of date. Historical requests exclude current fundamentals when publication timing cannot be verified.':['Use current data or choose a past date. Past-date runs do not use current fundamentals when timing cannot be verified.','Dùng dữ liệu hiện tại hoặc chọn một ngày trong quá khứ. Khi không xác định được thời điểm công bố, mô hình sẽ không dùng dữ liệu cơ bản hiện tại cho ngày quá khứ.'],
'SYMBOL':['SYMBOL','MÃ'],
'MODEL AS-OF':['AS-OF DATE','NGÀY PHÂN TÍCH'],
'FROM':['FROM','TỪ'],
'TO':['TO','ĐẾN'],
'Run risk analysis':['Analyze','Phân tích'],
'FPT case':['FPT example','Ví dụ FPT'],
'PNJ case':['PNJ example','Ví dụ PNJ'],
'RISK ASSESSMENT':['RISK SUMMARY','TỔNG QUAN RỦI RO'],
'WHY IS RISK ELEVATED?':['WHY?','VÌ SAO?'],
'Independent evidence modules':['Risk drivers','Các yếu tố rủi ro'],
'Unavailable modules are excluded, not imputed.':['Missing data is excluded.','Dữ liệu thiếu sẽ được loại khỏi điểm số.'],
'STEP 03 · VALIDATE':['STEP 03 · CHECK','BƯỚC 03 · KIỂM TRA'],
'Forward-risk context and out-of-sample evidence':['Historical context and test results','Bối cảnh lịch sử và kết quả kiểm tra'],
'Analog tail-event rates are matched-history frequencies. Predictive quality is tested separately with chronological holdout validation.':['Historical match rates show what happened after similar past states. A later time period is used to test the model separately.','Tỷ lệ lịch sử cho biết điều gì đã xảy ra sau các trạng thái tương tự. Một giai đoạn sau được dùng để kiểm tra mô hình riêng.'],
'RISK PATH':['RISK PATH','DIỄN BIẾN RỦI RO'],
'Price and technical warning history':['Price and risk history','Lịch sử giá và rủi ro'],
'DESCRIPTIVE REPLAY':['PAST CASES','TRƯỜNG HỢP QUÁ KHỨ'],
'POINT-IN-TIME REPLAY':['PAST SIGNALS','TÍN HIỆU QUÁ KHỨ'],
'Signals before historical ≥12% 20-session drawdowns':['Signals before past 20-day drawdowns of 12% or more','Tín hiệu trước các đợt giảm từ 12% trong 20 phiên'],
'T-20 / T-10 / T-5 / event start':['20 / 10 / 5 days before / start','Trước 20 / 10 / 5 ngày / bắt đầu'],
'MODEL VALIDATION':['MODEL CHECK','KIỂM TRA MÔ HÌNH'],
'Chronological holdout test':['Test on later data','Kiểm tra trên dữ liệu giai đoạn sau'],
'Calibrate the structural EWS threshold on the earlier sample, then measure Precision, Recall, F1, false-alarm rate and AUC only on the later holdout.':['Set the warning threshold on earlier data, then test Precision, Recall, F1, false alarms and AUC on later data.','Đặt ngưỡng cảnh báo bằng dữ liệu giai đoạn trước, sau đó kiểm tra Precision, Recall, F1, cảnh báo sai và AUC trên giai đoạn sau.'],
'Run holdout validation':['Run test','Chạy kiểm tra'],
'Run after selecting a security.':['Select a security first.','Chọn một mã trước.'],
'Model-risk scope:':['Test scope:','Phạm vi kiểm tra:'],
'STEP 04 · ACT':['STEP 04 · ACT','BƯỚC 04 · XỬ LÝ'],
'Risk-control response':['Risk controls to review','Biện pháp cần xem lại'],
'The system proposes controls for review. It does not place trades and does not convert a risk score into an automatic sell decision.':['The system suggests controls to review. It does not place trades or create automatic sell decisions.','Hệ thống gợi ý biện pháp cần xem lại. Hệ thống không đặt lệnh và không tự động đưa quyết định bán.'],
'GREEN':['GREEN','XANH'],
'Normal monitoring':['Normal monitoring','Theo dõi bình thường'],
'No escalation threshold currently met.':['No warning threshold is met.','Chưa chạm ngưỡng cảnh báo.'],
'Maintain approved limits':['Keep approved limits','Giữ hạn mức đã duyệt'],
'Normal daily monitoring':['Daily monitoring','Theo dõi hàng ngày'],
'Reassess after material deterioration':['Review if risk rises','Xem lại khi rủi ro tăng'],
'YELLOW':['YELLOW','VÀNG'],
'Enhanced watch':['Closer watch','Theo dõi sát hơn'],
'Deterioration detected; evidence not yet sufficient for RED.':['Risk is rising, but not enough for RED.','Rủi ro đang tăng nhưng chưa đủ để chuyển ĐỎ.'],
'Daily review':['Review daily','Xem hàng ngày'],
'Check concentration and liquidity':['Check concentration and liquidity','Kiểm tra tập trung và thanh khoản'],
'Define RED escalation trigger':['Set RED trigger','Xác định ngưỡng chuyển ĐỎ'],
'RED':['RED','ĐỎ'],
'Formal escalation':['Immediate review','Xem xét ngay'],
'Multi-factor deterioration requires exposure review.':['Several risk signals are elevated. Review exposure.','Nhiều tín hiệu rủi ro đang tăng. Cần xem lại mức độ nắm giữ.'],
'No passive risk increase':['Do not increase risk without review','Không tăng rủi ro khi chưa xem xét'],
'-10% / -15% stress review':['Review -10% / -15% stress','Kiểm tra kịch bản -10% / -15%'],
'Assign owner and review date':['Assign owner and next review','Chỉ định người phụ trách và lần xem tiếp theo'],
'Loss containment':['Manage current loss','Kiểm soát mức lỗ hiện tại'],
'Already in deep drawdown; no longer an early-warning state.':['The loss is already large; this is no longer an early warning.','Mức giảm đã lớn; đây không còn là cảnh báo sớm.'],
'Review remaining loss capacity':['Review remaining loss capacity','Xem lại khả năng chịu lỗ còn lại'],
'Liquidity / exit-capacity assessment':['Check liquidity and exit capacity','Kiểm tra thanh khoản và khả năng thoát vị thế'],
'Escalate limit breaches':['Escalate limit breaches','Báo cáo khi vượt hạn mức'],
'GOVERNANCE':['MODEL NOTES','GHI CHÚ MÔ HÌNH'],
'Data, assumptions and audit trail':['Data and model notes','Dữ liệu và ghi chú mô hình'],
'Verify what the model actually saw, which modules were unavailable, and whether the selected as-of date prevents look-ahead.':['Check the data used, missing inputs and the selected as-of date.','Kiểm tra dữ liệu đã dùng, dữ liệu thiếu và ngày phân tích đã chọn.'],
'FINANCIAL FRAGILITY':['FUNDAMENTALS','CƠ BẢN'],
'Available fundamentals':['Available fundamentals','Dữ liệu cơ bản hiện có'],
'NEWS SENTIMENT':['NEWS','TIN TỨC'],
'Evidence in request window':['News in selected period','Tin trong giai đoạn đã chọn'],
'MODEL EVIDENCE':['MODEL NOTE','GHI CHÚ MÔ HÌNH'],
'Vietnam Market Early Warning System · Risk-management research portfolio':['Vietnam Market Risk Monitor · Risk management demo','Theo dõi rủi ro thị trường Việt Nam · Bản demo quản trị rủi ro'],
'Point-in-time evidence · Explainable risk controls':['As-of-date data · Clear risk controls','Dữ liệu theo ngày · Kiểm soát rủi ro rõ ràng'],
'Not investment advice':['Not investment advice','Không phải khuyến nghị đầu tư'],
'No usable securities returned for this request.':['No usable data returned.','Không có dữ liệu phù hợp.'],
'None':['None','Không có'],
'Not available':['Not available','Không có dữ liệu'],
'High risk evidence':['High','Cao'],
'Elevated evidence':['Elevated','Tăng'],
'Moderate evidence':['Moderate','Trung bình'],
'Low evidence':['Low','Thấp'],
'No escalation signal in current watchlist':['No warning in the current watchlist','Danh sách hiện tại chưa có cảnh báo'],
'Maintain normal monitoring and review again when new completed market data arrive.':['Keep normal monitoring.','Tiếp tục theo dõi bình thường.'],
'No completed replay episodes':['No past cases found','Chưa có trường hợp quá khứ phù hợp'],
'No qualifying historical ≥12% 20-session drawdown episode is fully observable inside the point-in-time replay history.':['No complete past 20-day drawdown case of 12% or more was found in this history.','Không tìm thấy đủ dữ liệu cho trường hợp quá khứ giảm từ 12% trong 20 phiên.'],
'Descriptive replay only. Predictive performance is measured separately in the chronological holdout below.':['Past-case view only. Model performance is tested separately below.','Phần này chỉ xem trường hợp quá khứ. Hiệu quả mô hình được kiểm tra riêng bên dưới.'],
'INSUFFICIENT VALIDATION':['NOT ENOUGH DATA','CHƯA ĐỦ DỮ LIỆU'],
'VALIDATION FAILED':['TEST FAILED','KIỂM TRA LỖI'],
'Run holdout validation to measure out-of-sample screening performance for this security.':['Run the later-data test for this security.','Chạy kiểm tra trên dữ liệu giai đoạn sau cho mã này.'],
'Building point-in-time samples and testing the chronological holdout…':['Running the model test…','Đang chạy kiểm tra mô hình…'],
'Run holdout validation':['Run test','Chạy kiểm tra'],
'Running holdout…':['Running…','Đang chạy…'],
'Composite risk':['Risk score','Điểm rủi ro'],
'EOD close':['Close','Đóng cửa'],
'Live overlay':['Live price','Giá hiện tại'],
'20D momentum':['20D momentum','Động lượng 20 ngày'],
'60D drawdown':['60D drawdown','Mức giảm 60 ngày'],
'RSI 14':['RSI 14','RSI 14'],
'QTRR RESPONSE LEVEL':['RESPONSE LEVEL','MỨC XỬ LÝ'],
'Monitoring cadence':['Review frequency','Tần suất xem lại'],
'Decision rule':['Rule','Nguyên tắc'],
'Risk review, not an automatic trade':['Risk review only','Chỉ dùng để xem xét rủi ro'],
'Controls to review':['Controls to review','Biện pháp cần xem lại'],
'NORMAL MONITORING':['NORMAL','BÌNH THƯỜNG'],
'ENHANCED WATCH':['WATCH','THEO DÕI'],
'ESCALATE':['REVIEW NOW','XEM NGAY'],
'LOSS CONTAINMENT':['MANAGE LOSS','KIỂM SOÁT LỖ'],
'Model date':['Model date','Ngày mô hình'],
'Analog matches':['Past matches','Số trường hợp tương tự'],
'Historical analog stress':['Historical match','So khớp lịch sử'],
'News sentiment':['News','Tin tức'],
'Financial fragility':['Fundamentals','Cơ bản'],
'Technical deterioration':['Technical','Kỹ thuật'],
'VNINDEX regime':['VNINDEX','VNINDEX'],
'Macro / cross-asset':['Macro','Vĩ mô']
};

const patterns=[
[/^Risk radar ready · (.+)$/,(m,l)=>l==='vi'?`Radar sẵn sàng · ${m[1]}`:`Radar ready · ${m[1]}`],
[/^Requesting current risk states from Vnstock…$/,(m,l)=>l==='vi'?'Đang tải dữ liệu rủi ro…':'Loading risk data…'],
[/^Loading verified production risk data…$/,(m,l)=>l==='vi'?'Đang tải dữ liệu rủi ro…':'Loading risk data…'],
[/^Running point-in-time risk analysis for ([A-Z0-9]+)…$/,(m,l)=>l==='vi'?`Đang phân tích ${m[1]}…`:`Analyzing ${m[1]}…`],
[/^([A-Z0-9]+) · (GREEN|YELLOW|RED|GRAY) · risk (\d+)\/100$/,(m,l)=>{const c=l==='vi'?({GREEN:'XANH',YELLOW:'VÀNG',RED:'ĐỎ',GRAY:'GIẢM SÂU'}[m[2]]):m[2];return l==='vi'?`${m[1]} · ${c} · Rủi ro ${m[3]}/100`:`${m[1]} · ${c} · Risk ${m[3]}/100`}],
[/^(RED · ESCALATE|YELLOW · WATCH|GREEN · NORMAL|ACTIVE DRAWDOWN) · (\d+)$/,(m,l)=>{const c={"RED · ESCALATE":['RED · REVIEW','ĐỎ · XEM NGAY'],"YELLOW · WATCH":['YELLOW · WATCH','VÀNG · THEO DÕI'],"GREEN · NORMAL":['GREEN · NORMAL','XANH · BÌNH THƯỜNG'],"ACTIVE DRAWDOWN":['ACTIVE DRAWDOWN','ĐANG GIẢM SÂU']}[m[1]];return `${c[l==='vi'?1:0]} · ${m[2]}`}],
[/^(\d+) name(?:s)? require escalation$/,(m,l)=>l==='vi'?`${m[1]} mã cần xem ngay`:`${m[1]} name${m[1]==='1'?'':'s'} need review`],
[/^(\d+) name(?:s)? on enhanced watch$/,(m,l)=>l==='vi'?`${m[1]} mã cần theo dõi sát`:`${m[1]} name${m[1]==='1'?'':'s'} on watch`],
[/^(\d+) name(?:s)? already in active drawdown$/,(m,l)=>l==='vi'?`${m[1]} mã đang giảm sâu`:`${m[1]} name${m[1]==='1'?'':'s'} in active drawdown`],
[/^Review concentration, new-risk approval and downside stress for RED names first\.$/,(m,l)=>l==='vi'?'Ưu tiên xem mức tập trung, rủi ro mới và kịch bản giảm của các mã ĐỎ.':'Review RED names first: concentration, new risk and downside stress.'],
[/^Increase monitoring and review whether limits, liquidity and concentration remain appropriate\.$/,(m,l)=>l==='vi'?'Theo dõi sát hơn và xem lại hạn mức, thanh khoản, mức tập trung.':'Monitor more closely and review limits, liquidity and concentration.'],
[/^Use loss-containment controls\. This is not a pre-crash early-warning state\.$/,(m,l)=>l==='vi'?'Tập trung kiểm soát mức lỗ hiện tại. Đây không còn là cảnh báo sớm.':'Focus on current loss control. This is no longer an early warning.'],
[/^(\d+)\/(\d+) names · (.+)$/,(m,l)=>l==='vi'?`${m[1]}/${m[2]} mã · ${m[3]}`:`${m[1]}/${m[2]} names · ${m[3]}`],
[/^Fundamentals (\d+)\/100$/,(m,l)=>l==='vi'?`Cơ bản ${m[1]}/100`:`Fundamentals ${m[1]}/100`],
[/^News sentiment (\d+)\/100$/,(m,l)=>l==='vi'?`Tin tức ${m[1]}/100`:`News ${m[1]}/100`],
[/^Historical analog (\d+)\/100$/,(m,l)=>l==='vi'?`Lịch sử ${m[1]}/100`:`History ${m[1]}/100`],
[/^Technical (\d+)\/100$/,(m,l)=>l==='vi'?`Kỹ thuật ${m[1]}/100`:`Technical ${m[1]}/100`],
[/^Request (.+) → (.+)$/,(m,l)=>l==='vi'?`Khoảng dữ liệu ${m[1]} → ${m[2]}`:`Data range ${m[1]} → ${m[2]}`],
[/^Vnstock rows$/,(m,l)=>l==='vi'?'Số dòng dữ liệu':'Data rows'],
[/^Price$/,(m,l)=>l==='vi'?'Giá':'Price'],
[/^Fundamental$/,(m,l)=>l==='vi'?'Cơ bản':'Fundamentals'],
[/^News$/,(m,l)=>l==='vi'?'Tin tức':'News'],
[/^Macro$/,(m,l)=>l==='vi'?'Vĩ mô':'Macro'],
[/^(5|20|60) TRADING DAYS$/,(m,l)=>l==='vi'?`${m[1]} PHIÊN`:`${m[1]} TRADING DAYS`],
[/^Historical tail-event rate among (\d+) matched states$/,(m,l)=>l==='vi'?`Tỷ lệ sự kiện trong ${m[1]} trường hợp lịch sử tương tự`:`Event rate across ${m[1]} similar past cases`],
[/^Tail threshold (.+) · analog score (.+)\/100$/,(m,l)=>l==='vi'?`Ngưỡng ${m[1]} · điểm lịch sử ${m[2]}/100`:`Threshold ${m[1]} · history score ${m[2]}/100`],
[/^Technical risk (\d+)$/,(m,l)=>l==='vi'?`Rủi ro kỹ thuật ${m[1]}`:`Technical risk ${m[1]}`],
[/^Realized next-20-session drawdown (.+)$/,(m,l)=>l==='vi'?`Mức giảm thực tế 20 phiên sau ${m[1]}`:`Next-20-day drawdown ${m[1]}`],
[/^Freeze model here$/,(m,l)=>l==='vi'?'Phân tích tại ngày này':'Use this date'],
[/^avg technical risk · n=(\d+)$/,(m,l)=>l==='vi'?`rủi ro kỹ thuật TB · n=${m[1]}`:`avg technical risk · n=${m[1]}`]
];

function tr(src,l=lang){
 const s=src.trim();
 if(!s)return src;
 if(D[s])return D[s][l==='vi'?1:0];
 for(const [re,fn] of patterns){const m=s.match(re);if(m)return fn(m,l)}
 return src;
}

function translateNode(n){
 if(n.nodeType!==Node.TEXT_NODE)return;
 const p=n.parentElement;
 if(!p||['SCRIPT','STYLE','TEXTAREA','INPUT','OPTION'].includes(p.tagName))return;
 if(!original.has(n))original.set(n,n.nodeValue);
 const src=original.get(n);
 const lead=(src.match(/^\s*/)||[''])[0],tail=(src.match(/\s*$/)||[''])[0];
 const core=src.trim();
 const out=tr(core,lang);
 if(core&&out!==core)n.nodeValue=lead+out+tail;
 else if(lang==='en'&&D[core])n.nodeValue=lead+D[core][0]+tail;
}
function walk(root=document.body){
 if(!root)return;
 const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
 let n;while((n=w.nextNode()))translateNode(n);
 document.documentElement.lang=lang==='vi'?'vi':'en';
 document.querySelectorAll('[data-lang]').forEach(b=>{b.classList.toggle('active',b.dataset.lang===lang);b.setAttribute('aria-pressed',String(b.dataset.lang===lang))});
 const title=lang==='vi'?'VMEWS — Theo dõi rủi ro thị trường Việt Nam':'VMEWS — Vietnam Market Risk Monitor';document.title=title;
}
function setLanguage(next){if(!['en','vi'].includes(next))return;lang=next;localStorage.setItem(PREF,lang);applying=true;walk();applying=false;}
function init(){
 document.addEventListener('click',e=>{const b=e.target.closest('[data-lang]');if(b)setLanguage(b.dataset.lang)});
 applying=true;walk();applying=false;
 const mo=new MutationObserver(ms=>{if(applying)return;applying=true;for(const m of ms){if(m.type==='characterData'){original.delete(m.target);translateNode(m.target)}else for(const n of m.addedNodes){if(n.nodeType===Node.TEXT_NODE)translateNode(n);else if(n.nodeType===Node.ELEMENT_NODE)walk(n)}}applying=false;});
 mo.observe(document.body,{subtree:true,childList:true,characterData:true});
 window.VMEWS_I18N={setLanguage,getLanguage:()=>lang};
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();