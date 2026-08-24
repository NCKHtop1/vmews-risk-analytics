# VMEWS Forecast V20.1 — phạm vi sử dụng và hàng rào phát hành

## Kết luận

V20.1 ưu tiên tính toàn vẹn của giá dự báo hơn số lượng tín hiệu. Giá trung tâm T+1 đến T+5 chỉ đến từ mô hình đã đi qua kiểm định ngoài thời gian. Dữ liệu mới tại thời điểm ra quyết định — danh mục quỹ, dòng tiền, báo cáo tài chính, tin sau phiên và tín hiệu cộng đồng — được lưu thành bối cảnh/kịch bản tham khảo, không được cộng trực tiếp vào giá trung tâm khi chưa có lịch sử điểm-thời-gian đủ dài và chưa chứng minh được lợi thế độc lập.

Bản phát hành này không được coi là hệ thống giao dịch tự động hoặc bảo đảm sinh lời. T+4 và T+5 vẫn ở chế độ theo dõi nếu kiểm định sau chi phí không đạt.

## Vì sao phải sửa

V20.0 đã có mô hình trực tiếp cho từng kỳ, kiểm định giữ lại theo thời gian, bước giá HOSE và vùng Q20–Q80. Tuy nhiên, giá hiển thị sau cùng còn có thể bị thay đổi bởi hai lớp chưa được kiểm định độc lập:

1. Bộ điều chỉnh trực tiếp từ quỹ, dòng tiền, tài chính, tin mới và thông tin lan truyền.
2. Tệp cộng đồng tải sau khi mở trang có thể ghi đè các trường giá đã niêm phong.

Hai điểm này làm giá người dùng nhìn thấy không còn chắc chắn trùng với giá đã vượt kiểm định phát hành. V20.1 loại bỏ cả hai đường ghi đè.

## Chính sách dữ liệu

| Nhóm dữ liệu | Vai trò trong V20.1 | Điều kiện trước khi được nâng cấp vai trò |
|---|---|---|
| OHLCV lịch sử | Đầu vào mô hình | Nguồn đóng băng đã kiểm toán, điều chỉnh doanh nghiệp và đối chiếu nguồn |
| Giá phiên hiện tại | Neo giá T0 | Cùng ngày, đủ độ phủ, đối chiếu VNDIRECT với TradingView theo sai số gắn với bước giá |
| Tin/sự kiện lịch sử | Đầu vào mô hình | Có thời điểm công bố, đúng doanh nghiệp, không dùng kết quả tương lai |
| Dòng tiền tổ chức lịch sử | Đầu vào khi còn mới | Giá trị quan sát thật; dữ liệu quá hạn bị che khỏi quyết định |
| Quỹ, tài chính, tin sau phiên, cộng đồng mới | Kịch bản tham khảo | Cần kho lưu trữ điểm-thời-gian, kiểm định riêng và lợi thế ổn định qua nhiều khối thời gian |

Nguồn lịch sử đóng băng hiện có ghi nhận 404/404 mã HOSE tại thời điểm chụp, `vnstock` được thử làm nguồn chính cho 404 mã, tỷ lệ xác minh hành động doanh nghiệp là 100% và sai khác MAD giữa các nguồn ở phân vị 95 khoảng 0,00000834. Đây là bằng chứng chất lượng nguồn, không phải bằng chứng mô hình sẽ dự báo đúng trong tương lai.

## Hàng rào phát hành V20.1

- Dừng phát hành nếu giá T0 cũ, độ phủ HOSE giảm hoặc biểu đồ không khớp báo giá.
- Dừng phát hành nếu đối chiếu không bao phủ ít nhất 98% số mã có mặt đồng thời ở hai nguồn, nếu phần giao nhau thấp hơn 55% toàn bộ HOSE, hoặc nếu có mã sai khác quá dung sai.
- Dừng phát hành nếu bất kỳ giá trung tâm, vùng giá hoặc kịch bản nào nằm ngoài biên phiên hay sai bước giá.
- Dừng phát hành nếu tổng đóng góp của mô hình không khớp lợi suất trung tâm.
- Dừng phát hành nếu dữ liệu trực tiếp chưa kiểm định làm thay đổi giá trung tâm.
- Giao diện chỉ nhận lớp kịch bản trực tiếp; `expectedPrice`, `expectedReturn`, Q20 và Q80 đã niêm phong là bất biến.
- Pull request phải chạy toàn bộ quy trình mô hình và kiểm toán; nhánh kiểm thử không được tự ghi dữ liệu vào `main`.

## Những hạn chế còn lại

1. Bằng chứng sau phí hiện là chẩn đoán mua đơn với mức phí cố định, chưa phải backtest danh mục có trượt giá, khớp lệnh, giới hạn thanh khoản và quy mô vị thế.
2. T+4 và T+5 chưa chứng minh lợi thế sau phí ổn định như T+1 đến T+3; không nên dùng làm tín hiệu vào lệnh độc lập.
3. Quỹ, báo cáo tài chính và thông tin sau phiên chưa có kho lịch sử điểm-thời-gian đủ sâu để huấn luyện/kiểm định riêng.
4. Vùng dự báo phụ thuộc vào chế độ thị trường đã thấy trong dữ liệu; cú sốc chính sách, thanh khoản hoặc sự kiện bất thường có thể nằm ngoài phân phối lịch sử.
5. Dữ liệu công khai có thể chậm, thiếu hoặc được nhà cung cấp sửa lại. Hai nguồn cùng khớp nhau giúp phát hiện lỗi báo giá, nhưng không chứng minh dữ liệu hoàn hảo.

## Lộ trình cải thiện tiếp theo

1. Lưu hàng ngày các snapshot quỹ, tài chính, tin sau phiên và cộng đồng với thời điểm quan sát bất biến.
2. Chạy nghiên cứu gia tăng ngoài mẫu cho từng nhóm dữ liệu; chỉ thăng cấp nhóm nào cải thiện sai số hoặc lợi suất sau phí trên nhiều khối thời gian.
3. Xây dựng backtest danh mục có spread, trượt giá theo thanh khoản, giới hạn tỷ trọng, turnover và kiểm tra khả năng khớp lệnh.
4. Hiệu chỉnh vùng dự báo theo trạng thái biến động và kiểm tra độ phủ có điều kiện theo ngành, thanh khoản, vốn hóa và xu hướng thị trường.
5. Theo dõi sai số thực tế theo ngày; tự hạ cấp hoặc khóa kỳ dự báo khi độ ổn định suy giảm.

## Quy tắc sử dụng tiền thật

Chỉ xem V20.1 là một lớp hỗ trợ quyết định. Trước mỗi lệnh cần kiểm tra lại giá/khối lượng hiện hành tại công ty chứng khoán, sự kiện doanh nghiệp, thanh khoản, mức lỗ tối đa chấp nhận và điều kiện thoát lệnh. Không dùng xác suất/độ đúng lịch sử như cam kết cho một mã cụ thể và không dùng T+4/T+5 làm căn cứ duy nhất khi trạng thái sau phí là `REVIEW`.
