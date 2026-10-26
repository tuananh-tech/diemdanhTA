# Triển khai lên GitHub và Streamlit Community Cloud

Bạn sẽ có một địa chỉ dạng `https://ten-xu-doan.streamlit.app`, chạy HTTPS (bắt buộc để điện thoại dùng được camera).

Tổng thời gian khoảng 30 phút. Cần chuẩn bị: tài khoản GitHub, tài khoản Streamlit Community Cloud (đăng nhập bằng GitHub), và tài khoản Supabase.

---

## Bước 1. Tạo cơ sở dữ liệu Supabase

Làm theo [SUPABASE.md](SUPABASE.md). Kết quả cần có là **chuỗi kết nối Session pooler**, ví dụ:

```
postgresql://postgres.abcdefghijkl:MAT_KHAU@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require
```

> **Không dùng SQLite trên Streamlit Cloud.** Ổ đĩa ở đó là tạm thời, dữ liệu sẽ **mất** mỗi khi ứng dụng khởi động lại hoặc cập nhật.

## Bước 2. Đưa mã nguồn lên GitHub

1. Tạo repository mới trên GitHub. Nên để **Private** vì đây là hệ thống quản lý trẻ em.
2. Trong thư mục `tntt_diemdanh`:

   ```bash
   git init
   git add .
   git commit -m "Hệ thống điểm danh TNTT"
   git branch -M main
   git remote add origin https://github.com/<tai-khoan>/<ten-repo>.git
   git push -u origin main
   ```

3. **Kiểm tra trước khi push.** File `.gitignore` đã loại trừ những thứ sau. Hãy xác nhận chúng không có trên GitHub:
   - `.streamlit/secrets.toml` (mật khẩu CSDL)
   - `data/` (CSDL SQLite, setup token)
   - `.venv/`, `test-artifacts/`
   - Các file Excel có **dữ liệu thật** của các em. Chỉ `sample_data/` (tên giả lập) được đưa lên.

## Bước 3. Tạo ứng dụng trên Streamlit Community Cloud

1. Vào https://share.streamlit.io → **Create app** → **Deploy a public app from GitHub**.
2. Chọn repository, nhánh `main`, *Main file path* là `app.py`.
3. Đặt *App URL* theo ý muốn, ví dụ `diemdanh-tntt-<giao-xu>`.
4. Mở **Advanced settings**:
   - **Python version: 3.12** (phiên bản đã kiểm thử).
   - **Secrets**: dán nội dung sau, thay bằng giá trị của bạn:

     ```toml
     DATABASE_URL = "postgresql://postgres.<ref>:<mat-khau>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
     SETUP_TOKEN = "mot-chuoi-ngau-nhien-dai-chi-ban-biet"
     SESSION_IDLE_MINUTES = 480
     FACE_MODULE_ALLOWED = false
     ```

5. Bấm **Deploy**. Lần đầu mất vài phút để cài thư viện.

## Bước 4. Khởi tạo hệ thống

1. Mở địa chỉ website. Hệ thống tự tạo bảng trong Supabase và bật RLS.
2. Màn hình **Khởi tạo hệ thống** hiện ra. Nhập `SETUP_TOKEN` đã đặt ở bước 3, họ tên và mật khẩu quản trị.
3. Vào **Cấu hình Xứ đoàn** để nhập tên giáo xứ, Xứ đoàn và tải logo (xem [LOGO_VA_QR.md](LOGO_VA_QR.md)).
4. Vào **Ngành / Lớp** để kiểm tra năm học và tạo lớp, hoặc để file Excel tự tạo lớp.
5. Vào **Thiếu nhi → Nhập Excel**.
6. Vào **Phân quyền** để tạo tài khoản cho Huynh trưởng và gán lớp/ngành.
7. Khi đã có tài khoản quản trị, có thể xóa `SETUP_TOKEN` khỏi Secrets. Màn hình khởi tạo chỉ xuất hiện khi chưa có tài khoản nào.

## Bước 5. Thử camera trên điện thoại

Mở website bằng Chrome (Android) hoặc Safari (iPhone), vào **Quét QR**, bấm **Bật camera** và cho phép quyền camera. Hệ thống ưu tiên camera sau. Nếu máy có nhiều camera sẽ có danh sách để đổi.

---

## Lưu ý vận hành trên Streamlit Community Cloud

- **Ứng dụng "ngủ"** khi lâu không có người dùng. Người đầu tiên mở lại phải chờ khoảng 30 giây đến 1 phút. Trước giờ sinh hoạt nên mở website sẵn.
- **Tốc độ** phụ thuộc khoảng cách giữa máy chủ Streamlit và Supabase. Mỗi lần quét cần vài truy vấn CSDL. Nên chọn region Supabase gần máy chủ Streamlit; Community Cloud hiện chủ yếu đặt tại Mỹ, hãy kiểm tra lại trong tài liệu của Streamlit. Sau khi deploy, hãy quét thử 10 thẻ để cảm nhận độ trễ thực tế.
- **Quyền riêng tư của app:** trong *Settings → Sharing* có thể giới hạn người xem bằng email. Ngoài ra hệ thống luôn yêu cầu đăng nhập.
- **Cập nhật phiên bản:** push mã mới lên `main`, Streamlit tự triển khai lại. Dữ liệu nằm ở Supabase nên không bị ảnh hưởng.
- **Gói miễn phí của Supabase** tạm dừng dự án sau một thời gian không hoạt động (xem điều khoản hiện hành của Supabase). Website sẽ báo "Không kết nối được cơ sở dữ liệu". Khi đó vào Supabase bấm *Restore project*.

## Chạy trong mạng nội bộ (không dùng Cloud)

Có thể chạy trên một máy tính tại giáo xứ: `streamlit run app.py --server.port 8501`. Điện thoại trong cùng mạng Wi-Fi truy cập qua `http://<ip-may>:8501`, nhưng **camera sẽ không hoạt động vì không có HTTPS**. Có hai cách xử lý:

- Dùng chứng chỉ: `streamlit run app.py --server.sslCertFile cert.pem --server.sslKeyFile key.pem` (chứng chỉ tự ký sẽ bị trình duyệt cảnh báo), hoặc
- Dùng ô **Nhập mã** / máy quét mã vạch cầm tay (cắm USB, hoạt động như bàn phím).

## Biến cấu hình

| Tên | Bắt buộc | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | Có (trên Cloud) | Chuỗi kết nối PostgreSQL. Bỏ trống thì dùng SQLite `data/tntt.db` |
| `SETUP_TOKEN` | Nên có | Mã dùng một lần để tạo quản trị viên đầu tiên. Không đặt thì hệ thống tự sinh và in ra log máy chủ |
| `SESSION_IDLE_MINUTES` | Không | Tự đăng xuất sau N phút không thao tác (mặc định 480) |
| `FACE_MODULE_ALLOWED` | Không | `true` mới cho phép bật module khuôn mặt (mặc định `false`) |

Các biến có thể đặt trong Secrets (`.streamlit/secrets.toml`) hoặc biến môi trường. Biến môi trường được ưu tiên.
