# Cấu hình Supabase (PostgreSQL)

## 1. Tạo dự án

1. Đăng ký tại https://supabase.com và chọn **New project**.
2. Đặt tên (ví dụ `tntt-diemdanh`), đặt **Database password** mạnh và lưu lại cẩn thận.
3. **Region:** chọn gần máy chủ chạy Streamlit (xem phần "Tốc độ" trong [TRIEN_KHAI.md](TRIEN_KHAI.md)).
4. Chờ dự án khởi tạo xong.

## 2. Lấy chuỗi kết nối

Vào nút **Connect** ở đầu trang dự án (hoặc *Project Settings → Database*). Chọn **Connection string → URI** và mục **Session pooler**.

```
postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres
```

- Thay `[YOUR-PASSWORD]` bằng mật khẩu ở bước 1. Nếu mật khẩu có ký tự đặc biệt như `@ : / ? #`, hãy mã hóa URL (ví dụ `@` → `%40`).
- Thêm `?sslmode=require` vào cuối chuỗi.
- **Dùng Session pooler** (cổng 5432). Kết nối *Direct* của Supabase chỉ hỗ trợ IPv6, có thể không truy cập được từ Streamlit Cloud.

Dán chuỗi này vào `DATABASE_URL` trong Secrets.

## 3. Tạo bảng

**Không cần làm gì thêm.** Lần đầu khởi động, ứng dụng tự tạo toàn bộ bảng, chỉ mục, ràng buộc và bật Row Level Security.

Nếu muốn tự tạo bằng tay hoặc rà soát cấu trúc, mở **SQL Editor** trong Supabase, dán nội dung file [`migrations/001_initial_schema.sql`](../migrations/001_initial_schema.sql) rồi chạy. File này được sinh tự động từ `tntt/models.py` và đã được kiểm thử trên PostgreSQL 16.

## 4. Mô hình bảo mật – đọc kỹ

| Thành phần | Cách bảo vệ |
|---|---|
| Chuỗi kết nối CSDL | Chỉ nằm trong **Secrets** phía máy chủ Streamlit. Không bao giờ gửi xuống trình duyệt, không có trong repository. |
| API REST công khai của Supabase | Supabase tự mở API cho schema `public` bằng *anon key*. Ứng dụng **bật RLS trên mọi bảng nhưng không tạo policy nào**, nên anon/authenticated key **không đọc hay ghi được** dữ liệu. Ứng dụng kết nối bằng vai trò `postgres` (chủ sở hữu bảng), là vai trò bỏ qua RLS. |
| anon key / service_role key | Ứng dụng **không dùng** hai key này. Đừng dán chúng vào Secrets hay mã nguồn. |
| Phân quyền theo lớp/ngành | Thực thi ở tầng nghiệp vụ (`tntt/services`). Mọi truy vấn của Huynh trưởng đều lọc theo phạm vi được phân công. |
| Mật khẩu người dùng | Băm PBKDF2-SHA256 (310.000 vòng, có salt). Không lưu mật khẩu gốc. |
| Phiên ghi nhớ đăng nhập | Cookie chứa token ngẫu nhiên. CSDL chỉ lưu bản băm SHA-256. Token bị thu hồi khi đăng xuất, đổi mật khẩu hoặc tài khoản bị khóa. |

**Kiểm tra RLS:** trong Supabase vào *Table Editor*, mỗi bảng phải có nhãn "RLS enabled". Hoặc chạy SQL:

```sql
SELECT relname, relrowsecurity FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind = 'r';
```

Mọi dòng phải là `true`.

> Nếu bạn tạo một vai trò PostgreSQL riêng (không phải `postgres`) cho ứng dụng, vai trò đó phải là **chủ sở hữu** các bảng, hoặc có thuộc tính `BYPASSRLS`. Nếu không, RLS sẽ chặn cả ứng dụng.

## 5. Sao lưu và khôi phục

Nên dùng **cả hai** cách sau.

1. **Trong ứng dụng** (*Cấu hình Xứ đoàn → Sao lưu*): tải về một file ZIP chứa toàn bộ dữ liệu, gồm thiếu nhi, điểm danh, tài khoản (mật khẩu đã băm), cấu hình và logo. Dùng file này để khôi phục, hoặc chuyển từ SQLite sang Supabase và ngược lại. Nên tải **mỗi tháng** và sau mỗi đợt nhập dữ liệu lớn. Lưu file ở nơi an toàn vì có thông tin cá nhân của trẻ em.
2. **pg_dump** (dành cho người có kỹ thuật):

   ```bash
   pg_dump "postgresql://postgres.<ref>:<mk>@aws-0-<region>.pooler.supabase.com:5432/postgres" -Fc -f tntt_$(date +%F).dump
   pg_restore --clean --no-owner -d "<chuoi-ket-noi>" tntt_YYYY-MM-DD.dump
   ```

Các gói trả phí của Supabase có sao lưu tự động hằng ngày. Gói miễn phí thì không có bản sao lưu tải về được (kiểm tra lại chính sách hiện hành của Supabase), vì vậy cách 1 rất quan trọng.

## 6. Chuyển dữ liệu từ máy cá nhân (SQLite) lên Supabase

1. Trên máy cá nhân, vào *Cấu hình Xứ đoàn → Sao lưu* và tải file ZIP.
2. Mở website trên Supabase, tạo quản trị viên tạm qua màn hình khởi tạo.
3. Vào *Cấu hình Xứ đoàn → Sao lưu → Khôi phục*, chọn file ZIP rồi gõ `KHÔI PHỤC`.
4. Đăng nhập lại bằng tài khoản cũ. Tài khoản tạm sẽ bị thay bằng dữ liệu trong bản sao lưu.
