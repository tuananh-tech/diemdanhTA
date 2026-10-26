# Hướng dẫn quản trị

## Vai trò

| Vai trò | Phạm vi dữ liệu | Quyền chính |
|---|---|---|
| **Quản trị hệ thống** | Toàn bộ | Mọi quyền, gồm tài khoản, cấu hình Xứ đoàn, sao lưu/khôi phục |
| **Ban Điều hành Xứ đoàn** | Toàn bộ | Thiếu nhi, nhập Excel, ngành/lớp/năm học, buổi sinh hoạt, sửa buổi đã đóng, báo cáo, thẻ QR, nhật ký |
| **Huynh trưởng / Dự trưởng** | Lớp/ngành được phân công | Xem và sửa thiếu nhi của lớp, tạo buổi cho lớp mình, điểm danh, báo cáo, in thẻ QR |
| **Chỉ xem** | Lớp/ngành được phân công | Xem thiếu nhi và báo cáo |

Bảng quyền chi tiết có trong trang **Phân quyền → Bảng quyền theo vai trò**.

**Phân công theo ngành** tự áp dụng sang năm học mới. **Phân công theo lớp** gắn với lớp của từng năm học, nên khi sang năm mới cần phân công lại.

Khi quét QR trong một buổi, mọi Huynh trưởng được phân công cho buổi đó đều quét được **tất cả** các em thuộc buổi (ví dụ đứng cửa nhà thờ trong Thánh lễ toàn Xứ đoàn). Đổi trạng thái thủ công thì chỉ làm được với em thuộc lớp mình phụ trách.

## Tài khoản

- **Tạo tài khoản**: hệ thống gợi ý mật khẩu tạm ngẫu nhiên. Hãy gửi riêng cho người dùng (tin nhắn trực tiếp, không đăng nhóm chung). Người dùng phải đổi mật khẩu khi đăng nhập lần đầu.
- **Đăng nhập sai 5 lần** thì tài khoản bị khóa 15 phút. Quản trị có thể bấm *Mở khóa đăng nhập*.
- **Huynh trưởng nghỉ**: bỏ chọn *Đang hoạt động*. Phiên ghi nhớ đăng nhập của người đó bị thu hồi ngay.
- **Quên mật khẩu**: dùng *Đặt lại mật khẩu*. Mọi phiên đăng nhập cũ của người đó bị thu hồi.
- Hệ thống luôn giữ ít nhất **một quản trị viên đang hoạt động**, và bạn không thể tự hạ quyền chính mình.

## Đầu năm học mới

1. **Ngành / Lớp → Năm học**: tạo năm học mới, đặt ngày bắt đầu học kỳ II, đánh dấu *năm học hiện tại*.
2. **Ngành / Lớp → Lớp**: chọn năm mới ở thanh bên trái rồi tạo các lớp.
3. **Thiếu nhi → Chuyển năm học**: chọn năm cũ → năm mới, ghép mỗi lớp cũ với lớp mới (hệ thống tự gợi ý nếu trùng tên), rồi bấm thực hiện. Ghi danh năm cũ **được giữ nguyên**.
4. Nhập thêm em mới bằng Excel.
5. **Phân quyền**: phân công lại lớp cho Huynh trưởng.
6. Không cần in lại thẻ QR. Mã QR gắn với em, không gắn với năm học.

## Nhập Excel

- Cột được nhận diện tự động theo tên, ví dụ: *Mã thiếu nhi / ID / Mã*, *Tên Thánh*, *Họ và tên / Tên*, *Ngày sinh*, *Giới tính*, *Ngành*, *Lớp*, *Đội*, *Năm học*, *Tình trạng*, *Phụ huynh*, *SĐT phụ huynh*, *Ghi chú*. Hỗ trợ cả hai cột tách riêng *Họ* + *Tên*. Có thể đổi lại cách hiểu từng cột trước khi nhập.
- File chỉ có **ID và Tên** (như `Book1.xlsx` của Xứ đoàn) cũng nhập được. Bật **Tách Tên Thánh** thì "Maria Nguyễn Thị A" thành Tên Thánh "Maria", họ tên "Nguyễn Thị A".
- **Số 0 ở đầu mã** được giữ nếu ô Excel ở dạng Text. Nếu Excel đã lưu thành số (0007 thành 7), dùng tùy chọn **Bù số 0** để khôi phục.
- **Mã đã tồn tại**: *Cập nhật* chỉ ghi đè những ô có dữ liệu (ô trống trong file không xóa dữ liệu cũ), hoặc *Bỏ qua* để chỉ thêm em mới.
- Dòng lỗi (thiếu tên, ngày sai, trùng mã trong file) được báo rõ và **không** được nhập. Các dòng hợp lệ được nhập trong **một giao dịch**: lỗi giữa chừng thì không ghi gì.
- Ngày sinh nhận dạng `dd/mm/yyyy`, `yyyy-mm-dd` hoặc ô ngày của Excel.

## Sao lưu

**Cấu hình Xứ đoàn → Sao lưu → Tạo bản sao lưu.** Nên làm hằng tháng. Xem thêm [SUPABASE.md](SUPABASE.md#5-sao-lưu-và-khôi-phục).

Khôi phục sẽ **thay toàn bộ** dữ liệu hiện tại. Phải gõ `KHÔI PHỤC` để xác nhận, và mọi người phải đăng nhập lại.

## Nhật ký

**Nhật ký hoạt động** ghi lại đăng nhập (kể cả thất bại), tạo/sửa thiếu nhi, nhập Excel, tạo/mở/đóng buổi, cấp/thu hồi QR, xuất báo cáo, thay cấu hình, sao lưu/khôi phục. Tab **Thay đổi điểm danh** cho từng buổi ghi ai đổi trạng thái của em nào, từ gì sang gì, lúc nào.
