# Kiến trúc và quyết định kỹ thuật

## Tổng quan

```
Trình duyệt (điện thoại / laptop)
 ├─ Giao diện Streamlit (WebSocket)
 └─ Component quét QR (iframe HTML/JS): camera → BarcodeDetector/jsQR → {text, nonce}
            │
Streamlit server (Python)        ← Secrets: DATABASE_URL, SETUP_TOKEN
 ├─ tntt/ui        Trang, điều hướng theo quyền, CSS
 ├─ tntt/services  Nghiệp vụ (không phụ thuộc Streamlit, kiểm thử độc lập)
 ├─ tntt/qrimage, cards   Sinh QR + logo + tự kiểm tra; thẻ PDF
 └─ SQLAlchemy 2 ──► PostgreSQL / Supabase (production) hoặc SQLite (máy cá nhân)
```

## Các quyết định chính

| Vấn đề | Lựa chọn | Lý do |
|---|---|---|
| Camera | Camera **của trình duyệt** qua `getUserMedia`, giải mã ngay trên thiết bị (BarcodeDetector, dự phòng bằng jsQR) | Mã cũ dùng `cv2.VideoCapture(0)` mở camera **của máy chủ**, nên vô dụng khi deploy. Giải mã ở trình duyệt chỉ gửi chuỗi ngắn về server: nhanh, không gửi ảnh |
| Quét liên tục | Custom component Streamlit (giao thức v1, HTML thuần, không cần Node build) đặt trong `st.fragment` | Mỗi lần quét chỉ chạy lại một mảnh giao diện. `nonce` chống xử lý lặp; component nhận lại kết quả để phát màu/âm thanh |
| CSDL | PostgreSQL (Supabase) + SQLAlchemy; SQLite cho chạy thử | Ổ đĩa Streamlit Cloud là tạm thời. Cùng một mã chạy được cả hai CSDL; bộ test chạy trên cả hai |
| Chống trùng | `UNIQUE(session_id, student_id)` + danh sách lập sẵn khi mở buổi + `UPDATE … WHERE status='unmarked'` / `WHERE version=?` | Nguyên tử ở cả PostgreSQL và SQLite. Không phụ thuộc khóa trong bộ nhớ (như `set()` của mã cũ, mất khi khởi động lại) |
| Danh sách tham dự | Chụp lại (snapshot) khi mở buổi, lưu cả `class_id` tại thời điểm đó | Tỷ lệ chuyên cần tính đúng trên buổi em thực sự thuộc đối tượng; chuyển lớp không làm sai lịch sử |
| Hồ sơ và ghi danh | `students` tách khỏi `enrollments` (mỗi năm một dòng) | Dùng lại dữ liệu nhiều năm, chuyển năm học không mất lịch sử |
| Nội dung QR | `TNTT:` + 12 ký tự ngẫu nhiên (bảng chữ không dễ nhầm), lưu ở `qr_credentials`, có thu hồi | Không lộ thông tin cá nhân, không đoán được, cấp lại được. Ký tự thuộc bảng *alphanumeric* của QR nên mã gọn (version 3) |
| Logo trong QR | Tự vẽ ma trận bằng Pillow; mức H; logo ≤ 30% trên nền trắng; tự giải mã bằng OpenCV; tự giảm hoặc bỏ logo | Kiểm soát hoàn toàn hình học và màu; bảo đảm quét được bằng phép thử, không bằng phỏng đoán |
| Thẻ PDF | fpdf2 (vẽ vector, font TTF Unicode) + ảnh QR đã kiểm tra | Chữ tiếng Việt sắc nét, file nhỏ (~140 KB/10 thẻ), đúng kích thước in |
| Mật khẩu | PBKDF2-SHA256 của thư viện chuẩn | Không thêm dependency biên dịch, vẫn đủ an toàn |
| Ghi nhớ đăng nhập | Cookie token ngẫu nhiên; CSDL lưu SHA-256; hết hạn tuyệt đối 14 ngày và theo thời gian không hoạt động | Streamlit mất phiên khi tải lại trang; trên điện thoại điều này xảy ra thường xuyên |
| Logo/cấu hình | Lưu trong CSDL (`assets`, `app_settings`) | Bền vững trên Cloud, sao lưu cùng dữ liệu |
| Supabase API | Bật RLS không policy trên mọi bảng | Chặn truy cập qua anon key; ứng dụng là chủ sở hữu bảng nên không bị ảnh hưởng |
| Font | Be Vietnam Pro (OFL), tự host qua `static/` | Thiết kế cho tiếng Việt; dùng chung cho web và PDF; không phụ thuộc Google Fonts lúc chạy |

## Mô hình dữ liệu

```
users ─┬─ user_scopes (branch_id | class_id)          login_sessions (token_hash)
       │
school_years ─ classes ─ branches
       │          │
students ─ enrollments (student, year, class, team)    qr_credentials (token, active/revoked)
   │
attendance_sessions ─ session_classes
   │
attendance_records  UNIQUE(session, student) · status · method · marked_by · marked_at · version · class_id
   │
attendance_logs (old → new, ai, lúc nào)

app_settings · assets (logo) · audit_logs · schema_meta
face_consents · face_templates (chỉ vector)       ← module tùy chọn
```

Trạng thái: `unmarked` (chưa điểm danh), `present`, `late`, `excused`, `absent`. Phương thức: `manual`, `qr`, `code`, `bulk`, `face`, `system`.

**Migration:** `db.init_db()` tạo bảng (idempotent), ghi `schema_meta`, chạy các migration mới trong `db.MIGRATIONS` theo thứ tự và bật RLS trên PostgreSQL. Khi đổi cấu trúc, hãy thêm một hàm migration mới (không sửa migration cũ) rồi chạy `python scripts/export_schema_sql.py`.

## Đánh giá các nguồn được cung cấp

| Nguồn | Chức năng | Giấy phép | Điểm yếu | Tái sử dụng |
|---|---|---|---|---|
| `attendance_app.py`, `New/1.py`, `2.py`, `3.py`, `attendance_app.py` (Flask) | Điểm danh bằng nhập ID hoặc quét ảnh QR, ghi CSV theo ngày | Mã của Xứ đoàn | Camera là của **máy chủ**; danh sách ID hardcode hoặc đọc Excel mỗi lần chạy; chống trùng bằng `set()` trong RAM (mất khi tắt); CSV không có buổi sinh hoạt, không phân quyền; endpoint `/shutdown` không bảo vệ | Giữ ý tưởng quy trình và định dạng `Book1.xlsx` (ID, Tên) |
| `QRcode.py`, `diemdanh.py` | Sinh QR từ Excel | — | Mức sửa lỗi L; `diemdanh.py` đưa **họ tên vào QR**; không có logo, không kiểm tra | Thay bằng `qrimage.py` |
| `camera.py`, `docQR.py` | Quét QR bằng OpenCV + pyzbar | — | Chạy desktop | Dùng pyzbar/OpenCV làm **bộ giải mã kiểm tra** |
| `Book1.xlsx`, `Untitled spreadsheet.xlsx` | Danh sách thật (ID, Tên) | Dữ liệu trẻ em | — | Importer đọc được (có test cục bộ, **không** đưa vào repo) |
| student-attendance-system (Streamlit) | Dashboard, CSV | **Không có file LICENSE** | Lưu CSV, không đăng nhập, chỉ có/vắng | Chỉ tham khảo bố cục; **không sao chép mã** |
| Face_recognition_based_attendance_system | Nhận diện LBPH, desktop | MIT | Xem [FACE_MODULE.md](FACE_MODULE.md) | Chỉ tham khảo ý tưởng |
| `diemdanh.rar` | Bản nén | — | Không giải nén (trùng nội dung thư mục `New/`) | — |
