# FinQuery — sổ tay vận hành liên tục, QA và xử lý sự cố
Bản kiểm toán ngày 24/10/2026. Phạm vi: finquery.info.vn, GitHub Actions, Neon và Vercel.

## Nguyên tắc vận hành
- Tách biệt website hoạt động và mô hình dự báo được kiểm định; không vì giữ pipeline xanh mà hạ chuẩn sealed/walk-forward hay phát tín hiệu từ phiên stale.
- Tách production và QA; secrets chỉ tồn tại trong Neon/Vercel secret stores.
- Dữ liệu phải có nguồn, sourceTime, checkedAt, phiên HOSE, coverage, PIT và nhãn cached/stale minh bạch.
- Luôn có commit đã QA, bản deployment rollback và postdeploy smoke, không tự sửa giá hay model để làm biến mất cảnh báo.

## Bản đồ nguồn và lịch chạy
| Nhóm | Nguồn / kiểm tra | Chu kỳ / tình trạng |
| --- | --- | --- |
| Google Auth và user | Vercel finquery-web -> Neon finquery_auth | Health HTTP, session, owner RBAC; production smoke 3 lần/ngày |
| Hồ sơ user | /api/user/workspace | Watchlist và chiến lược per user, optimistic revision; quyền kiểm tra server-side |
| Giá HOSE | financial-market-data/market/quotes.json | Publisher phiên, giám sát ~15 phút, coverage tối thiểu 90%; trễ >30ph warning, >55ph critical trong khung đo |
| Intraday | financial-market-data/market/intraday-status.json | Publisher khoảng 10 phút; 90%-99% coverage là cảnh báo, <90% critical |
| Technical Scanner | market/strategy-indicators.json | Chỉ bar trùng source session mới được tạo alert; Discovery stale được xem như dữ liệu lịch sử |
| Risk V2 | market/risk-monitor.json | sourceDate phải cùng phiên giá; là trạng thái stress chứ không phải xác suất giảm |
| Forecast | data/forecast-session-v21.json | EOD guarded; không đủ medium horizon thì tiếp tục PRICE_ONLY_STALE_CORE, rankingEligible=false |
| BCTC | financial-report-data/data/manifest.json | GH cron ~4 giờ; >=90% annual/quarter coverage, >28 giờ không xuất manifest cảnh báo |
| Tin tức/macro | market/news-latest.json và macro.json | Publisher riêng; >4 giờ tin trong phiên warning; >72 giờ macro warning |
| ESG | market/esg-status.json | Theo dõi companiesWithMetrics, source success và backlog, không mặc định 100% coverage |
| Model live | data/live-track/track-record.json | Không tự gán ranking skill thành xác suất nếu calibration chưa ổn định |

Lịch chỉ là lịch chạy dự kiến; GitHub Actions có thể trễ và các nguồn bên ngoài có thể chậm.

## Xử lý P0 theo thứ tự
1. Kiểm tra workflow FinQuery workspace production smoke và FinQuery operations SLO and incident watchdog; đọc healthz, HTTP 401/403/307 cho truy cập chưa được phép.
2. Nếu login/Neon lỗi: kiểm tra Vercel READY, alias domain, branch Production và names của env vars (KHÔNG in giá trị). Nếu lỗi gắn với release mới, rollback về deployment đã có smoke thành công.
3. Nếu dữ liệu giá stale: so sánh latestSourceTime, expected HOSE session, quote coverage và Risk/Scanner sourceTime. Kiểm tra publisher market-price-live.yml và market-realtime-guard.yml, không biến giá giữ lại thành live.
4. Nếu forecast không hợp lệ: đối chiếu forecast-v13-daily-refresh.yml và horizon_price_gate_diagnostics. Không nới các gate walk-forward, sealed hoặc executable-skill, không phục hồi ranking bằng model stale. Xử lý ở challenger riêng theo issue #1503.
5. Nếu dữ liệu Intraday thiếu: kiểm tra timeout và danh sách mã lỗi, retry có giới hạn; bảo vệ publisher giá 111 mã hiện hành khỏi job backfill nặng.
6. Nếu macro/news/ESG thiếu: đánh dấu cached/quality warning, không zero-impute, không tính sự kiện chưa xác minh thành alpha mới.

## Chốt phát hành
- Mỗi thay đổi có PR, test đúng commit, policy QA và Publisher concurrency governance.
- GitHub Pages frontend phải đạt build + deploy + verify.
- Vercel triển khai bản đã QA, schema additive phải sẵn sàng; xác nhận domain alias và rollback point.
- Smoke production: healthz, anonymous session, admin 403, data 401, dashboard 307, login 200, workspace JS và workspace GET/PUT anonymous 401.
- Google OAuth thực bằng tài khoản người dùng cần UAT của tài khoản kiểm thử, không đồng nhất mock/unit QA với E2E signed-in.
- Incident critical sau release: khôi phục bản đã kiểm chứng, phân tích lại trên nhánh riêng, không vượt gate.

## Giám sát lâu dài và minh chứng
- scripts/finquery_ops_health.py phát hiện thiếu/lệch phiên, dữ liệu cũ, coverage, quyền truy cập và mô hình không đạt.
- Workflow finquery-operations-watch.yml kiểm tra ~15 phút trong phiên, giảm ngoài phiên/cuối tuần; tạo 1 incident issue và cập nhật body; đóng issue chỉ khi toàn bộ check OK.
- Các artifact finquery-ops-health (JSON/Markdown) lưu 14 ngày. Giám sát/issue không đồng nghĩa tự sửa hệ thống.
- Workflow finquery-workspace-production-smoke.yml chạy 3 lần/ngày; có thể workflow_dispatch kiểm tra thủ công.
- Khi cần SLA 24/7 có cam kết, bổ sung external uptime monitor độc lập GitHub Actions và cơ chế escalation riêng.

## Các hạng mục đang mở
- #1500: forecast core chậm. Log các lần chạy 23/10 cho thấy thu thập EOD 403/403 thành công nhưng không horizon trung hạn nào qua đầy đủ independent walk-forward. Cấm tự nới gate.
- #1503: nghiên cứu challenger forecast để khôi phục publishability đã chứng nhận.
- #1504: PIT corporate events, NHNN/VBMA interbank vs repo/FX swap, HNX futures/OI; kiểm tra licensing và chạy shadow trước dùng production.
- #1505: data serving có version/snapshot, API authorization, private dữ liệu hạn chế quyền, backup và browser owner/user UAT.

## Giới hạn minh bạch
Nguồn raw JSON/HTML trên GitHub Pages/raw GitHub vẫn có thể truy cập trực tiếp ngoài lớp đăng nhập finquery.info.vn. Muốn bảo mật dữ liệu nguồn phải thay đổi upstream và quyền phân phối; chưa có cơ sở tuyên bố mọi dữ liệu là riêng tư. Model stale sẽ được giám sát CRITICAL đến khi thực sự có mô hình mới vượt kiểm định, dù website và giá vẫn hoạt động.
