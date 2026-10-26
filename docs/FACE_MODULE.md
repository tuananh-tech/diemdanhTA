# Module nhận diện khuôn mặt (tùy chọn, mặc định tắt)

## Vì sao mặc định tắt

Ảnh và đặc trưng khuôn mặt là **dữ liệu sinh trắc học**, thuộc nhóm **dữ liệu cá nhân nhạy cảm**. Ở đây lại là dữ liệu **của trẻ em**. Pháp luật Việt Nam về bảo vệ dữ liệu cá nhân (Luật Bảo vệ dữ liệu cá nhân và các văn bản hướng dẫn, trước đó là Nghị định 13/2023/NĐ-CP) đặt yêu cầu cao về sự đồng ý, mục đích, thời hạn lưu giữ, bảo mật và quyền xóa đối với loại dữ liệu này.

Tài liệu này **không phải tư vấn pháp lý**. Trước khi bật module, Xứ đoàn nên hỏi ý kiến Cha xứ và người có chuyên môn pháp lý. QR và điểm danh thủ công đã đáp ứng đầy đủ nhu cầu điểm danh.

## Các rào cản trước khi bật

Module chỉ hoạt động khi **cả ba** điều kiện đều thỏa:

1. Người triển khai đặt `FACE_MODULE_ALLOWED = true` trong Secrets. Đây là quyết định ở cấp hệ thống, người dùng web không tự bật được.
2. Quản trị viên vào *Cấu hình Xứ đoàn → Khuôn mặt*, **tích xác nhận đủ 5 điều kiện**:
   - Có văn bản đồng ý của cha mẹ/người giám hộ cho từng em, và ý kiến của chính em nếu đủ tuổi theo luật.
   - Đã đánh giá tác động xử lý dữ liệu cá nhân nhạy cảm và có người chịu trách nhiệm bảo vệ dữ liệu.
   - Đã thông báo mục đích, thời hạn lưu giữ, quyền rút lại đồng ý và quyền yêu cầu xóa.
   - Có quy trình xử lý khi nhận diện sai, và QR/thủ công luôn sẵn sàng thay thế.
   - Hệ thống chạy HTTPS, CSDL không công khai, chỉ người được phân quyền truy cập.

   Sau đó mới bật công tắc.
3. **Từng em** phải có bản ghi đồng ý **còn hạn** (tối đa 1 năm, phải có số/mã văn bản lưu trữ) thì mới được đăng ký khuôn mặt.

## Thiết kế an toàn

| Yêu cầu | Cách thực hiện |
|---|---|
| Không lưu ảnh | Ảnh chụp chỉ xử lý trong bộ nhớ. CSDL chỉ lưu **vector 128 số** (embedding) |
| Chỉ gợi ý | Hệ thống chỉ hiện "Gợi ý: …". Huynh trưởng phải bấm **"Đúng em này – ghi nhận"** thì mới lưu (method = `face`) |
| Từ chối khi không chắc | Gợi ý chỉ hiện khi điểm tương đồng ≥ ngưỡng **và** cách người giống thứ hai một khoảng tối thiểu. Ngược lại hệ thống báo "Không chắc chắn" và không gợi ý ai |
| Phạm vi hẹp | Chỉ so với các em thuộc **danh sách buổi đang điểm danh** |
| Chống trùng | Ghi nhận qua cùng cơ chế UPDATE có điều kiện như QR. Em đã điểm danh thì không ghi lần hai |
| Rút đồng ý / hết hạn | Rút đồng ý thì **xóa ngay** mọi vector của em. Vector có đồng ý hết hạn tự bị xóa mỗi lần dùng module |
| Quyền xóa | Có nút xóa mẫu của từng em và **xóa toàn bộ** dữ liệu sinh trắc học. Mọi thao tác đều ghi nhật ký |
| Cô lập | Module nạp lười, mọi lỗi được bắt lại. QR và điểm danh thủ công không phụ thuộc module này |

## Cài mô hình nhận diện

Module dùng **OpenCV YuNet** (phát hiện khuôn mặt) và **SFace** (trích đặc trưng), giấy phép Apache-2.0, thuộc dự án [opencv_zoo](https://github.com/opencv/opencv_zoo). Mô hình **không đi kèm** repository. Quản trị viên tự tải về và đặt vào thư mục `models/`:

- `models/face_detection_yunet_2023mar.onnx`
- `models/face_recognition_sface_2021dec.onnx`

Trên Streamlit Cloud, cần commit hai file này vào repository riêng tư của bạn (file `.onnx` đang bị `.gitignore` loại trừ, hãy bỏ dòng đó nếu chọn cách này). Trang cấu hình hiển thị trạng thái "Sẵn sàng" khi đã tìm thấy mô hình.

## Đánh giá mã nguồn tham khảo

Repository [Face_recognition_based_attendance_system](https://github.com/shubhamkumar27/Face_recognition_based_attendance_system) (giấy phép MIT) là ứng dụng **desktop Tkinter** dùng Haar Cascade và LBPH (`opencv-contrib`):

- Camera của **máy chạy chương trình** (`cv2.VideoCapture(0)`), không dùng được cho website.
- **Lưu ảnh khuôn mặt thô** ra thư mục `TrainingImage/` và lưu mật khẩu dạng chữ thường trong file văn bản. Cả hai điều này không phù hợp với dữ liệu trẻ em.
- Không có ngưỡng từ chối hay bước xác nhận của con người. Kết quả nhận diện được ghi thẳng vào CSV.

Vì vậy module ở đây **chỉ tham khảo ý tưởng**, không tái sử dụng mã. Thay vào đó dùng mô hình hiện đại hơn (YuNet/SFace), có trong OpenCV chính thức, không cần `opencv-contrib`.

## Trạng thái kiểm thử

- **Đã kiểm thử tự động:** logic so khớp, ngưỡng và khoảng cách với vector **giả lập**; điều kiện bật; đồng ý, rút đồng ý, tự xóa khi hết hạn; báo thiếu mô hình.
- **Chưa kiểm thử:** độ chính xác nhận diện trên khuôn mặt thật. Theo yêu cầu, **không dùng dữ liệu khuôn mặt thật** để chạy demo. Việc đánh giá độ chính xác cần làm có kiểm soát, với dữ liệu có đồng ý, trước khi dùng thật.
