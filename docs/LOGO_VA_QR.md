# Logo Xứ đoàn, tạo và in thẻ QR

## A. Thêm logo Xứ đoàn

1. Đăng nhập bằng tài khoản **Quản trị**, vào **Cấu hình Xứ đoàn → Logo**.
2. Chọn loại logo: **Logo Xứ đoàn** (dùng ở mọi nơi và giữa QR) hoặc **Logo Giáo xứ** (tùy chọn).
3. Bấm tải ảnh lên (PNG, JPG hoặc WebP, tối đa 5 MB). Nên dùng **PNG nền trong suốt**, hình vuông, từ 500×500 px trở lên.
4. Chỉnh trực tiếp trên web:
   - **Cắt trái/phải/trên/dưới** để bỏ phần thừa.
   - **Xoay** 90°, 180° hoặc 270°.
   - **Căn giữa thành hình vuông** và chỉnh **lề quanh logo**.
   - **Xóa nền trắng** khi ảnh gốc có nền trắng.
5. Xem trước ở ba chỗ: cỡ lớn, trên header, và **trong QR**. Dòng thông báo bên dưới cho biết QR có logo **đã được giải mã thử thành công** hay chưa.
6. Bấm **Lưu logo này**. Logo lưu trong cơ sở dữ liệu nên không mất khi khởi động lại hay cập nhật phiên bản.
7. Muốn quay lại logo mặc định thì bấm **Khôi phục logo mặc định**.

Logo xuất hiện ở header, sidebar, trang đăng nhập, biểu tượng tab trình duyệt, thẻ thiếu nhi, báo cáo PDF và giữa mã QR.

Logo mặc định của hệ thống là biểu tượng thánh giá trung tính, **không** phải huy hiệu chính thức của Phong trào TNTT. Hãy thay bằng logo được phép sử dụng của Xứ đoàn.

Tên Xứ đoàn, Giáo xứ, Giáo phận, khẩu hiệu và màu sắc chỉnh ở tab **Thông tin**. Kích thước logo trên header cũng chỉnh ở đây.

## B. Cấu hình QR mặc định

Vào **Cấu hình Xứ đoàn → QR mặc định**:

- **Chèn logo giữa QR**: bật hoặc tắt.
- **Logo trong QR**: chọn logo Xứ đoàn hoặc logo Giáo xứ.
- **Màu QR**: *Trắng đen* (dễ quét nhất, in máy đen trắng) hoặc *Màu nhận diện* (dùng màu chính của Xứ đoàn).
- **Kích thước logo**: từ 12% đến 30% cạnh QR.

### Cơ chế bảo đảm quét được

| Biện pháp | Chi tiết |
|---|---|
| Mức sửa lỗi **H** | Khi có logo, QR phục hồi được khoảng 30% dữ liệu bị che |
| Giới hạn kích thước | Logo tối đa 30% cạnh QR (≈9% diện tích), không chạm 3 ô định vị ở góc |
| Nền trắng quanh logo | Logo nằm trên ô nền trắng bo góc, căn theo lưới ô của mã |
| Tương phản màu | Màu quá nhạt (ví dụ vàng) được **tự làm tối** đến khi đủ tương phản 7:1 |
| **Tự kiểm tra** | Sau khi tạo, hệ thống giải mã thử ảnh gốc, ảnh thu nhỏ có làm mờ (mô phỏng chụp) và ảnh đặt trên nền xám, bằng 2 bộ dò của OpenCV (và ZBar nếu có) |
| Tự điều chỉnh | Giải mã không được thì thử **mẫu mặt nạ QR khác** (cùng nội dung, khác hình ô), rồi **giảm logo** dần đến 12%, cuối cùng mới **bỏ logo** và báo cho bạn |

Nội dung QR chỉ có dạng `TNTT:K7P2MXQ9ABCD`, là mã ngẫu nhiên. Nó **không chứa họ tên, ngày sinh hay mã thiếu nhi**. Người nhặt được thẻ cũng không đọc ra thông tin gì, và không có trang công khai nào tra cứu theo mã này.

## C. Tạo và in thẻ

Vào **Thẻ QR**:

1. Chọn kiểu QR ở đầu trang (logo, màu, kích thước), mặc định lấy theo cấu hình.
2. Chọn **lớp**, hoặc chọn từng em. Để trống thì in tất cả em đang sinh hoạt trong lựa chọn.
3. Có ba tab:
   - **Xem trước & tải 1 mã**: xem QR kèm tên, tải PNG có tên hoặc chỉ mã.
   - **In thẻ PDF / tải hàng loạt**:
     - **Tạo PDF thẻ thiếu nhi**: thẻ cỡ **54 × 85,6 mm** (bằng thẻ ATM, dọc), **9 thẻ/trang A4**, có vạch cắt. Mỗi thẻ có logo, tên Xứ đoàn, QR ở giữa, Tên Thánh, họ tên, lớp, mã và năm học.
     - **Tạo ZIP ảnh QR**: mỗi em một file PNG, tên file là mã kèm họ tên không dấu.
     - Sau khi tạo, hệ thống báo số mã phải bỏ logo (nếu có) và xác nhận **mọi mã đã được giải mã thử**.
   - **Thu hồi / cấp lại**: khi em **mất thẻ** hoặc thẻ bị người khác dùng, bấm *Thu hồi & cấp mã mới*. Mã cũ vô hiệu ngay, quét mã cũ sẽ báo "đã bị thu hồi". Sau đó in lại thẻ cho em.

### Mẹo in

- In ở chế độ **Actual size / 100%**, **không** chọn *Fit to page* để thẻ đúng kích thước.
- Giấy bìa 200–250 gsm hoặc ép plastic để thẻ bền. Nên dùng màng mờ: màng bóng dễ lóa khi quét.
- In thử 1 trang và quét bằng 2–3 điện thoại khác nhau trước khi in cả Xứ đoàn.
- QR in ra nên có cạnh tối thiểu **2,5 cm**. Thẻ mặc định có QR rộng 4,1 cm.

### Thẻ cũ (QR chỉ chứa số ID)

Nếu Xứ đoàn đã in thẻ cũ chứa trực tiếp mã số (ví dụ `12`), vào *Cấu hình Xứ đoàn → Quy tắc điểm danh* và bật **"Chấp nhận QR cũ chỉ chứa mã thiếu nhi"** trong giai đoạn chuyển đổi. Cách này kém an toàn hơn vì ai biết mã số cũng tự tạo được QR. Hãy in thẻ mới rồi tắt tùy chọn này.

## D. Kiểm thử đã thực hiện

- Tạo QR có logo ở các tỷ lệ 18%, 24%, 30% với màu đen, navy và vàng: **cả 9 tổ hợp đều giải mã được** bằng OpenCV và ZBar.
- Tạo PDF thẻ, rasterize lại ở 300 dpi (mô phỏng bản in) rồi cắt từng thẻ: **9/9 thẻ giải mã đúng nội dung**.
- Quét QR có logo qua **camera giả lập của Chromium** (phát video chứa thẻ): ghi nhận thành công vào CSDL.
- **Chưa thực hiện:** in ra giấy thật và quét bằng điện thoại thật. Việc này cần thiết bị tại giáo xứ. Hãy làm theo mục "Mẹo in" ở trên.
