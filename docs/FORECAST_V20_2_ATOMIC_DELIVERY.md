# VMEWS Forecast V20.2 — phát hành nguyên tử

## Mục tiêu

V20.2 hoàn thiện lớp phân phối của V20.1. Một URL CDN theo commit phải tải HTML, JavaScript và dữ liệu JSON từ cùng commit. URL theo `main` vẫn theo dữ liệu mới nhất, nhưng toàn bộ tài nguyên cùng dùng ref `main`. Bản Vercel tiếp tục dùng dữ liệu nằm trong chính deployment.

## Lỗi đã khắc phục

Trước V20.2, HTML và JavaScript có thể được khóa theo commit trong URL CDN, nhưng `forecast-final-v12.js` vẫn đọc JSON từ `main`. Khi schema dữ liệu thay đổi, giao diện cũ có thể ghép với dữ liệu mới và tạo lỗi không tái lập được.

V20.2 lấy ref trực tiếp từ đường dẫn CDN và dùng ref đó cho dữ liệu. Không còn đường dẫn `/main/data` được mã hóa cứng trong frontend.

## Hàng rào

- Kiểm thử Node xác nhận URL commit `hash` chỉ đọc `hash/data`.
- CDN smoke chặn mã có `/main/data` cố định.
- Release audit chặn phát hành nếu chính sách `SAME_REF` bị phá vỡ.
- Pull request chạy smoke trước khi được đưa vào `main`.
- Dữ liệu live chưa kiểm định vẫn chỉ là kịch bản tham khảo và không thay đổi giá trung tâm.

## Cách dùng

- Bản đóng băng, tái lập: URL CDN chứa commit SHA.
- Bản theo dữ liệu mới nhất: URL CDN chứa ref `main`.
- Production Vercel: dùng dữ liệu tương đối `./data` nằm trong cùng deployment.
