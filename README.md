# Hệ thống Điểm danh Thiếu Nhi Thánh Thể

Website điểm danh cho Xứ đoàn TNTT, viết bằng Python + Streamlit, chạy trên điện thoại, máy tính bảng và máy tính.

**Quy trình:** Nhập Excel → Quản lý thiếu nhi → Tạo buổi sinh hoạt → Điểm danh (danh sách một chạm / quét QR / nhập mã) → Lưu vào cơ sở dữ liệu → Thống kê → Xuất báo cáo.

Huynh trưởng chỉ cần mở website, đăng nhập, chọn buổi rồi điểm danh. Không phải mở terminal, sửa CSV hay đụng vào cơ sở dữ liệu.

## Tính năng chính

| Nhóm | Có gì |
|---|---|
| Điểm danh | 3 cách trong cùng một trang: **danh sách một chạm** (Có mặt / Trễ / Phép / Vắng, kèm ghi chú và lịch sử), **quét QR liên tục** bằng camera của chính điện thoại (có màu, âm thanh, rung), **nhập mã** khi camera hỏng. Có thao tác hàng loạt và tự làm mới khi nhiều Huynh trưởng cùng điểm danh. |
| Chống trùng | Mỗi em chỉ có **một trạng thái chính thức** trong mỗi buổi, có ràng buộc UNIQUE ngay trong CSDL. Mọi thay đổi là câu lệnh UPDATE có điều kiện (an toàn khi nhiều người thao tác cùng lúc). Mọi thay đổi đều được ghi nhật ký. |
| Buổi sinh hoạt | Gắn với buổi cụ thể (Thánh lễ, Giáo lý, Sinh hoạt… cùng một ngày vẫn là các buổi khác nhau). Tạo đơn lẻ hoặc **tạo theo lịch** (ví dụ mọi Chủ nhật). Danh sách tham dự được lập theo lớp/ngành. Em chưa được quét **không** tự bị coi là vắng; chỉ khi đóng buổi người phụ trách mới chọn chốt. |
| Thiếu nhi | Nhập Excel/CSV (tự nhận diện cột, **giữ số 0 ở đầu mã**, tách Tên Thánh, xem trước và kiểm lỗi), tìm kiếm không dấu, thêm/sửa, chuyển lớp, **chuyển năm học**, xuất Excel. Hồ sơ tách riêng khỏi ghi danh theo năm nên lịch sử được giữ nguyên. |
| QR & thẻ | QR chỉ chứa **mã ngẫu nhiên**, không chứa họ tên hay ngày sinh. Có logo ở giữa (mức sửa lỗi H, **tự kiểm tra giải mã**, tự thu nhỏ hoặc bỏ logo nếu khó quét). Có bản trắng đen hoặc theo màu Xứ đoàn. In **thẻ PDF 9 thẻ/trang A4** hoặc tải ZIP ảnh. Thu hồi và cấp lại mã khi mất thẻ. |
| Nhận diện Xứ đoàn | Tên giáo xứ, Xứ đoàn, giáo phận, khẩu hiệu, màu sắc, **logo** (tải lên, cắt, xoay, xóa nền, xem trước trong QR, khôi phục mặc định). Logo hiện trên header, sidebar, trang đăng nhập, thẻ, báo cáo và giữa QR. |
| Báo cáo | Dashboard có biểu đồ. Thống kê theo ngày, tuần, tháng, học kỳ, năm, ngành, lớp, cá nhân, loại sinh hoạt. Có sổ điểm danh (em × buổi). Xuất **Excel, CSV, PDF** kèm logo. |
| Phân quyền | 4 vai trò: Quản trị, Ban Điều hành, Huynh trưởng, Chỉ xem. Huynh trưởng chỉ thấy lớp/ngành được phân công. Có ghi nhớ đăng nhập an toàn (tải lại trang không bị đăng xuất), khóa tạm khi đăng nhập sai nhiều lần, bắt đổi mật khẩu lần đầu. |
| Vận hành | Nhật ký hoạt động, sao lưu/khôi phục toàn bộ dữ liệu, hỗ trợ PostgreSQL/Supabase (bật RLS chặn API công khai) và SQLite cho máy cá nhân. |
| Khuôn mặt (tùy chọn) | Module riêng, **mặc định tắt**, có rào cản pháp lý và đồng ý của phụ huynh. Chỉ gợi ý, Huynh trưởng phải xác nhận. Chỉ lưu vector đặc trưng, không lưu ảnh. Xem [docs/FACE_MODULE.md](docs/FACE_MODULE.md). |

## Chạy thử trên máy (5 phút)

Cần Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

Mở http://localhost:8501. Lần đầu hệ thống yêu cầu **mã khởi tạo**. Mã này nằm trong file `data/SETUP_TOKEN.txt` và được in ra cửa sổ terminal. Bạn cũng có thể tự đặt `SETUP_TOKEN` trong `.streamlit/secrets.toml`. Nhập mã rồi tạo tài khoản quản trị.

Không cấu hình gì thêm thì dữ liệu được lưu ở `data/tntt.db` (SQLite). Cách này chỉ phù hợp chạy trên một máy. Khi đưa lên mạng hãy dùng Supabase, xem [docs/SUPABASE.md](docs/SUPABASE.md).

Có sẵn dữ liệu mẫu **giả lập** trong `sample_data/` để thử chức năng nhập Excel.

> Điện thoại chỉ cho dùng camera khi trang được mở qua **HTTPS** (hoặc `localhost`). Khi deploy lên Streamlit Cloud thì đã có sẵn HTTPS.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [docs/TRIEN_KHAI.md](docs/TRIEN_KHAI.md) | Đưa lên GitHub và Streamlit Community Cloud |
| [docs/SUPABASE.md](docs/SUPABASE.md) | Tạo CSDL Supabase, chuỗi kết nối, bảo mật, sao lưu |
| [docs/LOGO_VA_QR.md](docs/LOGO_VA_QR.md) | Thêm logo Xứ đoàn, tạo và in thẻ QR |
| [docs/HUONG_DAN_HUYNH_TRUONG.md](docs/HUONG_DAN_HUYNH_TRUONG.md) | Hướng dẫn sử dụng cho Huynh trưởng |
| [docs/QUAN_TRI.md](docs/QUAN_TRI.md) | Dành cho quản trị: phân quyền, năm học mới, sao lưu |
| [docs/FACE_MODULE.md](docs/FACE_MODULE.md) | Module nhận diện khuôn mặt (tùy chọn) |
| [docs/KIEN_TRUC.md](docs/KIEN_TRUC.md) | Kiến trúc, mô hình dữ liệu, đánh giá mã nguồn tham khảo |
| [docs/KIEM_THU.md](docs/KIEM_THU.md) | Kết quả kiểm thử đã chạy |
| [docs/GIOI_HAN.md](docs/GIOI_HAN.md) | Giới hạn và việc còn lại |

## Cấu trúc thư mục

```
app.py                      Điểm vào Streamlit
requirements.txt            Thư viện cho môi trường chạy (đã ghim phiên bản đã kiểm thử)
requirements-dev.txt        Thêm thư viện kiểm thử
.streamlit/config.toml      Giao diện (navy / kem / vàng), font, bảo mật
.streamlit/secrets.toml.example   Mẫu cấu hình bí mật (KHÔNG commit file thật)
tntt/
  config.py  constants.py  models.py  db.py  security.py  textutil.py
  qrimage.py                Sinh QR + logo + tự kiểm tra giải mã
  cards.py                  Thẻ thiếu nhi PDF, ZIP ảnh QR
  services/                 Nghiệp vụ, không phụ thuộc giao diện:
    users.py org.py students.py importer.py sessions.py attendance.py
    qrcodes.py reports.py branding.py backup.py audit.py face.py
  components/qr_scanner/    Thành phần quét QR bằng camera trình duyệt (HTML/JS + jsQR)
  ui/                       Giao diện: main.py (điều hướng), theme.py, charts.py, pages/*
migrations/001_initial_schema.sql   Lược đồ PostgreSQL (sinh tự động từ models)
scripts/                    Sinh dữ liệu mẫu, sinh SQL, đo hiệu năng
static/fonts/               Font Be Vietnam Pro (OFL) dùng cho web và PDF
sample_data/                File Excel/CSV mẫu với tên giả lập
tests/                      Kiểm thử tự động (pytest) + tests/e2e (trình duyệt thật)
docs/                       Tài liệu
```

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest                                  # 78 test (77 chạy trên SQLite, 1 chỉ dành cho PostgreSQL)
TEST_DB=postgres pytest                 # chạy lại toàn bộ trên PostgreSQL thật (cần pgserver)
python -m playwright install chromium
python tests/e2e/run_e2e.py             # 28 kiểm tra trên trình duyệt thật, có camera giả lập quét QR
python scripts/benchmark.py             # đo hiệu năng với 1.200 thiếu nhi
```

Kết quả chi tiết xem [docs/KIEM_THU.md](docs/KIEM_THU.md).

## Giấy phép bên thứ ba

Xem [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Mã nguồn dự án chưa chọn giấy phép. Chủ sở hữu tự quyết định trước khi công khai repository.
