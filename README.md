# Personal-Finance-Assistant — FE Service

Prototype ứng dụng ngân hàng dùng **React 19 + Vite**, phục vụ VTB Hackathon 2026.

## Chạy trên máy local

Yêu cầu Node.js 22.12 trở lên và npm.

```bash
npm ci
npm run dev
```

Mở địa chỉ Vite hiển thị trong terminal (mặc định http://localhost:5173).

```bash
npm test          # Kiểm thử các luồng chính và logic nghiệp vụ
npm run build    # Build production vào dist/
npm run preview  # Xem thử bản build
```

Triển khai thư mục `dist/` lên static hosting sau khi build. Không chạy trực tiếp mã nguồn bằng `python -m http.server` như phiên bản cũ. Hướng dẫn về Vite: https://vite.dev/guide/.

## Chạy bằng Docker

Yêu cầu Docker Engine/Docker Desktop đang chạy với Linux containers và Docker Compose.

```bash
docker compose up -d --build
```

Mở http://localhost:8080. Docker tự cài dependencies và build React bằng Node.js; image chạy production dùng Nginx. Cấu trúc này sử dụng [multi-stage build](https://docs.docker.com/build/building/multi-stage/).

```bash
docker compose logs -f fe
docker compose down
```

Compose ánh xạ `8080:8080`: cổng `8080` trên máy host tới Nginx cổng `8080` trong container. Muốn đổi cổng truy cập thành `8081`, sửa mapping thành `8081:8080` rồi chạy lại `docker compose up -d`.

Hoặc build và chạy trực tiếp:

```bash
docker build -t vtb-fe:local .
docker run -d --name vtb-fe -p 8080:8080 vtb-fe:local
```

Nginx hỗ trợ fallback về `index.html` cho SPA, cache assets có hash, và endpoint `/healthz` dùng cho healthcheck. Camera hoạt động trên localhost; khi triển khai lên domain cần cấu hình HTTPS tại reverse proxy.

## Cấu trúc mã nguồn

**Dữ liệu/cấu hình tập trung tại [`public/app-config.json`](public/app-config.json)**. Ứng dụng tải file trước khi khởi tạo React, không nhúng dữ liệu mock vào bundle:

- `user`: ID user, tên hiển thị, ngân hàng, tài khoản nguồn và số dư.
- `banks`, `transfer`: danh sách ngân hàng/BIN, ngân hàng mặc định, hạn mức tối thiểu, quy tắc STK, phí và nội dung mặc định.
- `recipients`: danh sách người nhận ban đầu; `transactions`: lịch sử. Ảnh QR được giải mã trực tiếp, không lấy thông tin từ danh sách mẫu trong config.
- `mockServices`: giá trị mặc định, lựa chọn và kết quả cho từng dịch vụ mock.
- `services`, `navigation`, `transferMethods`, `screenTitles`: danh mục, điều hướng và tiêu đề màn hình.
- `app`, `storage`: tên ứng dụng, định dạng tiền, mã tham chiếu và tiền tố lưu trữ danh bạ.

Với **Docker Compose**, file được mount read-only vào Nginx: sửa `public/app-config.json` rồi reload trang, **không cần rebuild**. Nếu thay file bằng cách xóa/tạo lại và không thấy cập nhật, chạy `docker compose up -d --force-recreate`. Với `docker run` không mount file, cấu hình được đóng gói trong image khi build.

Danh bạ người dùng lưu được ưu tiên hơn `recipients` trong config. Đổi `user.id` để dùng một danh bạ riêng cho user khác. File config là dữ liệu công khai trong trình duyệt, không đặt password, token hoặc API key vào đây. Các nội dung giao diện và logic xử lý vẫn nằm trong component; dữ liệu nghiệp vụ demo không còn nằm rải rác trong code.

```text
src/
  main.jsx            # Khởi tạo React, import CSS
  App.jsx             # Điều hướng màn hình, state form và giao dịch
  pages/              # Home, Transfer, Qr, Confirm/Success, History, More
  components/         # Icon, Header/Navbar, Services, Transactions, VoicePanel
  hooks/              # Vòng đời camera và đọc ảnh QR
  lib/                # Dữ liệu mẫu, đọc QR, kiểm tra chuyển tiền
  test/               # Vitest + React Testing Library
```

Để thêm màn hình, tạo component trong `pages/`, khai báo điều hướng trong `App.jsx` và tiêu đề/danh mục trong `public/app-config.json`. Xử lý dịch vụ ở hàm `service` trong `App.jsx`. Tách logic nghiệp vụ mới vào `lib/` hoặc hook, và dùng React state để cập nhật giao diện.

Form và danh sách giao dịch lưu trong bộ nhớ, mất khi tải lại trang. Camera được dừng khi rời trang QR. `VoicePanel` có nút bật/tắt micro bằng `getUserMedia`, tự giải phóng micro khi đóng panel hoặc điều hướng. Chưa có logic voice-to-text, lưu/gửi âm thanh hoặc xử lý câu lệnh; có thể tích hợp từ audio stream trong `VoicePanel` sau.

## Chức năng

- Mục Chuyển tiền có ba lựa chọn: Chuyển tiền thường, Quét QR và Chuyển tiền nhanh. Chuyển tiền nhanh chỉ điền ngân hàng, tài khoản và tên chủ tài khoản; số tiền và nội dung để trống cho mỗi lần chuyển, vẫn cần xác nhận giao dịch.
- Lưu/cập nhật người nhận từ form chuyển tiền mà không cần nhập số tiền; đặt tên gợi nhớ như Mẹ, Cha; quản lý/xóa trong danh sách người nhận. Dữ liệu lưu trong localStorage của trình duyệt. Danh bạ mặc định trống, không tự lấy người nhận từ QR mẫu. Danh bạ cũ vẫn đọc được, bỏ qua số tiền và nội dung từng lưu.

### Thêm người nhận

Vào **Chuyển tiền → Chuyển tiền nhanh → Thêm người nhận**. Form riêng chỉ có ngân hàng, số tài khoản, tên chủ tài khoản và tên gợi nhớ; không có số tiền hoặc nội dung chuyển khoản. Chọn Lưu để trở về danh bạ, hoặc Hủy để bỏ thông tin đang nhập.

Để cấu hình danh bạ ban đầu, sửa trường `recipients` trong `public/app-config.json`. Mỗi người nhận gồm `bank`, `account` (STK dạng chuỗi để giữ số 0 đầu), `recipient` và `nickname` tùy chọn. Giao diện không có nút nhập JSON.

### Các dịch vụ khác

- Các dịch vụ nạp điện thoại, tiết kiệm, vé máy bay, vay, chứng chỉ quỹ, thẻ, hóa đơn và ưu đãi đều có form cùng kết quả mô phỏng. Không gọi API hoặc thay đổi số dư thực tế.

- Trang chủ với các dịch vụ ngân hàng và lịch sử giao dịch.
- Form chuyển khoản trống và chuyển khoản từ mã QR.
- Quét QR bằng camera hoặc tải ảnh, giải mã trực tiếp bằng JavaScript kể cả khi không có BarcodeDetector. Thông tin đọc được sẽ điền vào form; không còn danh sách QR mẫu để bấm điền sẵn.
- Xác nhận và kết quả chuyển tiền giả lập.
- Nút bật/tắt micro và trạng thái đang nghe; xử lý giọng nói sẽ được tích hợp sau.

**Cảnh báo:** Mọi tài khoản và giao dịch đều là mock. Không kết nối Core Banking, không xác thực thụ hưởng thực tế, không chuyển tiền thật. Camera cần quyền trình duyệt; thường yêu cầu HTTPS hoặc localhost.
