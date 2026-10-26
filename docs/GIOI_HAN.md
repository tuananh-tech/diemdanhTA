# Giới hạn và công việc còn lại

## Cần chủ sở hữu thực hiện (cần tài khoản, quyền hoặc quyết định)

| Việc | Vì sao tôi không tự làm | Hướng dẫn |
|---|---|---|
| Tạo dự án Supabase, lấy chuỗi kết nối | Cần tài khoản và mật khẩu của Xứ đoàn | [SUPABASE.md](SUPABASE.md) |
| Tạo repository GitHub (nên để Private) và push | Cần tài khoản; quyết định công khai hay không thuộc về chủ sở hữu | [TRIEN_KHAI.md](TRIEN_KHAI.md) |
| Deploy lên Streamlit Community Cloud, nhập Secrets | Cần tài khoản | [TRIEN_KHAI.md](TRIEN_KHAI.md) |
| Nhập danh sách thiếu nhi **thật** | Dữ liệu trẻ em: chỉ chủ sở hữu được đưa lên hệ thống. Repo chỉ chứa dữ liệu **giả lập** | Trang *Thiếu nhi → Nhập Excel* |
| Logo chính thức của Xứ đoàn | Cần file logo được phép sử dụng | [LOGO_VA_QR.md](LOGO_VA_QR.md) |
| Chọn giấy phép mã nguồn (nếu công khai) | Quyết định của chủ sở hữu | — |
| Thủ tục pháp lý trước khi bật module khuôn mặt | Quyết định và trách nhiệm của Xứ đoàn/Giáo xứ | [FACE_MODULE.md](FACE_MODULE.md) |

## Danh sách kiểm tra tại giáo xứ trước khi dùng chính thức

1. Deploy xong, đăng nhập được trên **ít nhất 2 điện thoại** (1 iPhone, 1 Android) và 1 laptop.
2. In thử 1 trang thẻ (khổ 100%), quét bằng các điện thoại đó trong điều kiện ánh sáng ở nơi sinh hoạt.
3. Thử 2 Huynh trưởng quét cùng một buổi ở hai cửa và kiểm tra con số khớp nhau.
4. Quét 10 thẻ liên tục để cảm nhận tốc độ thực tế. Nếu chậm, xem lại region Supabase.
5. Tạo bản sao lưu đầu tiên và cất giữ cẩn thận.
6. Hướng dẫn Huynh trưởng theo [HUONG_DAN_HUYNH_TRUONG.md](HUONG_DAN_HUYNH_TRUONG.md).

## Giới hạn kỹ thuật đã biết

| Giới hạn | Ảnh hưởng | Cách xử lý |
|---|---|---|
| **Không có chế độ offline** | Mất mạng thì không quét được. Trường hợp này hệ thống báo lỗi và **không ghi** gì, không có dữ liệu "ảo" | Dùng 4G dự phòng; hoặc ghi giấy rồi nhập lại bằng danh sách. Tôi cố ý không làm offline giả: đồng bộ có giải quyết xung đột đúng nghĩa là một hạng mục lớn riêng |
| Camera chỉ chạy trên **HTTPS** (hoặc localhost) | Chạy trong mạng LAN bằng `http://ip` sẽ không có camera | Dùng Streamlit Cloud (có HTTPS), cấu hình chứng chỉ, hoặc dùng ô nhập mã / máy quét USB |
| Streamlit Community Cloud **ngủ** khi lâu không dùng | Lần mở đầu tiên chờ ~30–60 giây | Mở website sẵn trước giờ sinh hoạt |
| Độ trễ mạng tới Supabase | Có thể chậm nếu khác region | Chọn region gần; đo sau khi deploy |
| Mỗi lượt quét làm mới một mảnh giao diện qua WebSocket | Kết nối yếu thì phản hồi chậm hơn; quá 6 giây không có phản hồi thì component báo "Mất kết nối – quét lại" | — |
| Âm thanh trên iPhone | Safari chỉ phát âm thanh sau khi người dùng chạm vào trang (đã xử lý khi bấm "Bật camera"); chế độ im lặng của máy có thể tắt tiếng | Vẫn có màu và chữ phản hồi |
| Đèn flash (torch) | Chỉ một số trình duyệt Android hỗ trợ; nút chỉ hiện khi thiết bị hỗ trợ | — |
| Ghi nhớ đăng nhập dùng cookie đặt bằng JavaScript (không HttpOnly) | Streamlit không cho đặt cookie phía server. Token chỉ có giá trị khi khớp bản băm trong CSDL, thu hồi được, có hạn | Bỏ chọn "Ghi nhớ" trên máy chung |
| Phân quyền thực thi ở tầng ứng dụng | RLS của Supabase chỉ dùng để chặn API công khai, không phân quyền từng Huynh trưởng | Đây là kiến trúc chuẩn khi máy chủ giữ kết nối CSDL; không đưa key CSDL xuống trình duyệt |
| Phân công theo **lớp** gắn với từng năm học | Sang năm mới phải phân công lại | Dùng phân công theo **ngành** nếu muốn tự chuyển năm |
| Danh sách tham dự chụp lại khi mở buổi | Em mới thêm vào lớp sau khi mở buổi chưa có trong buổi | Bấm *Đồng bộ danh sách* ở trang Buổi sinh hoạt |
| Chưa có thông báo (SMS/Zalo) cho phụ huynh | — | Có thể bổ sung sau; cần dịch vụ trả phí và sự đồng ý của phụ huynh |
| Module khuôn mặt chưa đánh giá độ chính xác thực tế | — | Xem [FACE_MODULE.md](FACE_MODULE.md) |

## Đề xuất phát triển tiếp

- Thông báo cho phụ huynh khi em vắng nhiều buổi liên tiếp (cần kênh gửi và sự đồng ý).
- Trang cho phụ huynh tự xem chuyên cần của con (cần tài khoản phụ huynh và đánh giá quyền riêng tư).
- Chế độ offline có hàng đợi đồng bộ và quy tắc giải quyết xung đột rõ ràng.
- Thống kê so sánh giữa các năm học.
