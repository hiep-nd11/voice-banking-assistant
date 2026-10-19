# QR mock cho FE

Vào **Quét QR → Tải ảnh QR** và chọn một ảnh PNG trong thư mục này, hoặc mở ảnh trên thiết bị khác để quét bằng camera.

| Ảnh | Người nhận | Số tiền |
| --- | --- | --- |
| `01-vietinbank-200k.png` | NGUYEN VAN MINH · VietinBank | 200.000 ₫ |
| `02-vietcombank-350k.png` | TRAN THI LAN · Vietcombank | 350.000 ₫ |
| `03-mb-custom-amount.png` | LE QUANG HUY · MB Bank | Để trống, nhập sau khi quét |
| `04-missing-recipient.png` | Chưa có tên · VietinBank | 100.000 ₫ |

Mẫu 04 dùng để kiểm tra thông báo yêu cầu nhập và kiểm tra tên người nhận. Các file JSON đi kèm có thể sao chép vào ô **Dán nội dung QR** nếu trình duyệt không hỗ trợ đọc QR từ camera/ảnh.

Các mã chứa JSON demo phù hợp với parser hiện tại của FE, không phải mã VietQR dùng để thanh toán trên ứng dụng ngân hàng. Tài khoản và giao dịch chỉ dùng cho mô phỏng.
