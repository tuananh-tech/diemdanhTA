# Báo cáo kiểm thử

Môi trường: Windows 11, Python 3.12.3, Streamlit 1.66.1, pandas 3.1, SQLAlchemy 2.1.6, OpenCV 5.0. CSDL: SQLite 3 và **PostgreSQL 16.2** (nhúng qua `pgserver`). Trình duyệt: Chromium headless (Playwright 1.64).

## Tóm tắt

| Bộ kiểm thử | Lệnh | Kết quả |
|---|---|---|
| Unit/integration trên SQLite | `pytest` | **77 đạt**, 1 bỏ qua (test chỉ dành cho PostgreSQL) |
| Môi trường sạch giống Streamlit Cloud (venv mới chỉ từ `requirements.txt`, **không có ZBar**) | `pip install -r requirements.txt pytest && pytest` | **76 đạt**, 2 bỏ qua (PostgreSQL, pypdfium2) – chạy 3 lần liên tiếp đều đạt |
| Unit/integration trên PostgreSQL | `TEST_DB=postgres pytest` | **78/78 đạt** |
| Đầu-cuối trên trình duyệt thật, SQLite | `python tests/e2e/run_e2e.py` | **28/28 đạt** |
| Đầu-cuối trên trình duyệt thật, PostgreSQL | `E2E_DB=postgres python tests/e2e/run_e2e.py` | **28/28 đạt** |
| Hiệu năng 1.200 thiếu nhi | `python scripts/benchmark.py` | Xem bên dưới |
| File SQL migration | Chạy `migrations/001_initial_schema.sql` trên PostgreSQL trống, rồi khởi động ứng dụng | Đạt (ứng dụng nhận lược đồ phiên bản 1) |

Kết quả chi tiết nằm trong `test-artifacts/` (thư mục bị `.gitignore` loại trừ): `pytest_sqlite.txt`, `pytest_postgres.txt`, `e2e_results_*.txt` và ảnh chụp màn hình.

## Đối chiếu với 17 hạng mục yêu cầu

✅ = đã chạy tự động và đạt · 🟡 = đã kiểm thử bằng mô phỏng, cần xác nhận trên thiết bị thật · ⬜ = cần thiết bị/môi trường thật

| # | Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | Nhập Excel mẫu | ✅ | `test_import_*`: file ID+Tên (tách Tên Thánh), file đầy đủ 120 em tạo 6 lớp, CSV, cột Họ/Tên tách riêng, file `Book1.xlsx` gốc trên máy (24 dòng, 0 lỗi). E2E: tải file qua giao diện, xem trước, nhập 120 em |
| 2 | Nhập và cập nhật dữ liệu | ✅ | Cập nhật chỉ ghi đè ô có dữ liệu, giữ lớp cũ; chế độ chỉ thêm mới; trùng mã trong file; ngày sai; tự sinh mã; **giữ số 0 ở đầu** và tùy chọn bù số 0 |
| 3 | Tạo QR có logo | ✅ | 9 tổ hợp (logo 18/24/30% × đen/navy/vàng); 120 mã ngẫu nhiên chỉ dùng OpenCV; đổi mặt nạ → giảm logo → bỏ logo; ép tương phản màu nhạt |
| 4 | Đọc lại QR được tạo | ✅ | Giải mã bằng OpenCV + ZBar; **PDF thẻ rasterize 300 dpi → cắt từng thẻ → giải mã đúng** (cả PDF tạo từ giao diện); ZIP ảnh |
| 5 | Ghi nhận điểm danh thủ công | ✅ | Đổi trạng thái, ghi chú, lịch sử, hàng loạt chỉ áp cho em chưa điểm danh. E2E: chạm "Có mặt" → lưu |
| 6 | Quét QR | ✅ 🟡 | **E2E: camera giả lập của Chromium phát video chứa thẻ QR có logo → component JS giải mã → Streamlit → CSDL** (method=`qr`). Đã kiểm tra mã ngoài phiên, mã đã thu hồi, mã lạ, nhập mã thủ công, đi trễ theo giờ. 🟡 Chưa quét bằng camera điện thoại thật |
| 7 | Chống ghi nhận trùng | ✅ | Quét lại báo "đã điểm danh"; QR không ghi đè trạng thái thủ công; mỗi (buổi, em) đúng 1 bản ghi; ràng buộc UNIQUE |
| 8 | Quét cho các phiên khác nhau | ✅ | Cùng em, 2 buổi cùng ngày (Thánh lễ, Sinh hoạt): ghi nhận độc lập |
| 9 | Ghi nhận đồng thời | ✅ | **8 luồng quét cùng 1 thẻ cùng lúc → đúng 1 thành công, 1 dòng log**; 4 luồng × 30 lượt quét cho 10 em → đúng 10 bản ghi. Đạt trên SQLite và PostgreSQL. Xung đột phiên bản khi sửa thủ công được phát hiện |
| 10 | Đổi trạng thái điểm danh | ✅ | Khóa lạc quan theo `version`; bỏ chọn về "Chưa điểm danh"; đóng buổi có/không chốt vắng; mở lại buổi |
| 11 | Phân quyền | ✅ | Huynh trưởng chỉ thấy lớp mình; không sửa được lớp khác hay buổi đã đóng; không tạo được buổi toàn Xứ đoàn; trang quản trị bị ẩn, mở bằng URL bị chặn; chỉ Quản trị quản lý tài khoản; bảo vệ quản trị viên cuối cùng; khóa tài khoản sau 5 lần sai; token ghi nhớ bị thu hồi khi đổi mật khẩu |
| 12 | Xuất báo cáo | ✅ | Excel (đọc lại được), CSV (UTF-8 BOM, chống chèn công thức), PDF có logo; tải về qua giao diện |
| 13 | Lưu trữ bền vững | ✅ | Cấu hình, logo và dữ liệu vẫn còn sau khi khởi tạo lại kết nối; sao lưu/khôi phục toàn bộ (kể cả đặt lại sequence của PostgreSQL) |
| 14 | Thay đổi logo | ✅ | Tải logo qua giao diện, xem trước trong QR, hiện ở header; khôi phục mặc định; từ chối file không phải ảnh hoặc sai định dạng |
| 15 | Khởi động lại ứng dụng | ✅ | E2E: dừng server, chạy lại → đăng nhập → cấu hình và 120 em còn nguyên |
| 16 | Giao diện trên các kích thước màn hình | ✅ 🟡 | Ảnh chụp 1366×900, 1280×900, tablet 768×1024, **mobile 390×844 không cuộn ngang**, 4 nút trạng thái vừa 1 hàng. 🟡 Chưa thử trên điện thoại thật (Safari iOS, Chrome Android) |
| 17 | Lỗi thư viện và môi trường triển khai | ✅ ⬜ | Cài sạch từ `requirements.txt` (phiên bản ghim) trong venv mới; không có cảnh báo cấu hình Streamlit; không có lỗi console JS; mọi trang mở không lỗi. ⬜ **Chưa deploy thật lên Streamlit Community Cloud + Supabase** (cần tài khoản của Xứ đoàn) |

## Hiệu năng (dữ liệu giả lập 1.200 em, 40 buổi, 48.000 bản ghi)

| Thao tác | SQLite | PostgreSQL (cùng máy) |
|---|---:|---:|
| Đọc + kiểm tra file Excel 1.200 dòng | 330 ms | 323 ms |
| Ghi 1.200 em vào CSDL (1 giao dịch) | 1,1 s | 2,1 s |
| Mở buổi toàn Xứ đoàn (lập danh sách 1.200 em) | 67 ms | 125 ms |
| Tải danh sách điểm danh 1 buổi (1.200 em) | 22 ms | 22 ms |
| **Một lượt quét QR** (trung bình / p95, 300 lượt) | **2,7 / 3,4 ms** | **3,5 / 4,3 ms** |
| Tìm kiếm không dấu | 8 ms | 10 ms |
| Tải dữ liệu báo cáo cả năm | 640 ms | 576 ms |
| Thống kê theo lớp / tháng / từng em / sổ điểm danh | 16–47 ms | 15–45 ms |

Trên Supabase thật, mỗi truy vấn cộng thêm độ trễ mạng giữa máy chủ Streamlit và Supabase. Một lượt quét cần khoảng 8 truy vấn: nếu độ trễ 5 ms thì khoảng 40 ms/lượt, nếu 100 ms thì gần 1 giây/lượt. Vì vậy cần chọn region gần nhau (xem [TRIEN_KHAI.md](TRIEN_KHAI.md)).

## Lỗi phát hiện và đã sửa trong quá trình kiểm thử

| Lỗi | Cách phát hiện | Sửa |
|---|---|---|
| iframe quét QR tự tăng chiều cao vô hạn (đo `documentElement.scrollHeight` + 4px mỗi lần) | E2E: nút "Điểm danh" ở ô nhập mã "không ổn định" | Đo chiều cao nội dung thực, chỉ gửi khi thay đổi |
| Tải lại trang (F5, mở lại tab trên điện thoại) bị đăng xuất | Thăm dò E2E | Thêm cơ chế ghi nhớ đăng nhập bằng token (băm trong CSDL, thu hồi được) |
| Trang Nhật ký lỗi: dùng `df.at` (bộ chỉ mục của pandas) thay cho cột `at` | E2E duyệt mọi trang | `df["at"]` |
| `db.configure("postgresql://…")` dùng driver psycopg v3 (không có trong requirements) | E2E trên PostgreSQL | Chuẩn hóa URL ngay trong `configure()`, kèm test |
| Tab bị đặt lại về tab đầu sau khi bấm Lưu | E2E | Đặt `key` cho `st.tabs` |
| Mobile: header bị thanh công cụ che; số liệu xếp 1 cột dài; nút "Vắng" bị cắt | Ảnh chụp 390px | Lưới KPI 2–3 cột, dải chip trạng thái, bố cục hàng mới, CSS riêng cho màn hình hẹp |
| Rủi ro chèn công thức khi mở CSV/Excel | Rà soát bảo mật | Thêm tiền tố `'` cho ô bắt đầu bằng `= + @ -` |
| Trên môi trường chỉ có OpenCV (như Streamlit Cloud), khoảng 1/150 mã bị kiểm tra "không giải được" dù thực ra không liên quan logo, nên hệ thống bỏ logo oan | Chạy test trong venv sạch từ `requirements.txt` | Dùng cả `QRCodeDetector` và `QRCodeDetectorAruco`; khi kiểm tra thất bại thì thử **mẫu mặt nạ QR khác** trước khi giảm logo. Thêm test 120 mã ngẫu nhiên khi không có ZBar: 120/120 giữ logo 30% |

## Những gì chưa thể kiểm thử trong môi trường này

- Deploy thật lên **Streamlit Community Cloud** với **Supabase** thật (độ trễ mạng, HTTPS, ngủ/thức ứng dụng).
- Quét bằng **camera điện thoại thật** (Safari iOS, Chrome Android), đèn flash, chuyển camera trước/sau, ánh sáng yếu.
- **In thẻ ra giấy** và quét bản in (đã mô phỏng bằng cách rasterize PDF ở 300 dpi).
- Âm thanh và rung trên thiết bị thật (trình duyệt headless không phát âm thanh).
- Module khuôn mặt với **mô hình thật và khuôn mặt thật** (cố ý không làm, xem [FACE_MODULE.md](FACE_MODULE.md)).
- Kiểm thử trợ năng bằng trình đọc màn hình.

Danh sách kiểm tra tại giáo xứ có trong [GIOI_HAN.md](GIOI_HAN.md#danh-sách-kiểm-tra-tại-giáo-xứ-trước-khi-dùng-chính-thức).
