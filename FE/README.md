# VTB Voice Banking Frontend

React 19 + Vite. Yêu cầu Node.js 22.12+ và npm.

```sh
npm ci
npm run dev
```

Vite mặc định mở http://localhost:5173, proxy `/api` sang http://127.0.0.1:8000.
Chạy Docker tích hợp từ thư mục cha bằng `docker compose up -d --build`.
Compose riêng trong `FE` dùng tên dịch vụ frontend là `fe`.

## Cấu trúc

```text
src/
  App.jsx       # State điều hướng, chuyển tiền demo và sự kiện trợ lý
  pages/        # Trang chủ, tài sản, giao dịch, phân tích, dịch vụ và workflow
  components/   # UI dùng chung
  hooks/        # Camera và quét QR
  lib/          # API/SSE, config, tiền/ngày, QR, danh bạ và validation
  test/         # Vitest + React Testing Library
public/
  app-config.json
```

## Cấu hình và dữ liệu

`public/app-config.json` được tải trước khi khởi tạo React:

- `api.dataSource`: `backend` (mặc định) hoặc `demo`.
- `api.baseUrl`: để rỗng khi dùng Vite/Nginx proxy.
- `api.customerId`: định danh phiên trợ lý; không thay đổi khách hàng cố định của MCP.
- `user`, `transactions`, `recipients`: dữ liệu khởi tạo/demo.
- `banks`, `transfer`: ngân hàng, hạn mức, phí và nội dung mặc định.
- `services`, `navigation`, `transferMethods`, `screenTitles`: cấu hình hiển thị.
- `mockServices`, `app`, `storage`: dịch vụ demo, định dạng và khóa lưu cục bộ.

Ở chế độ backend, hồ sơ/số dư/tài khoản/giao dịch được nạp từ BE.
Lỗi tải dữ liệu được hiển thị, không âm thầm thay bằng dữ liệu demo.
Không đặt API key, mật khẩu hoặc token trong file công khai này.

Chuyển thường/nhanh/QR đều xác nhận mô phỏng trên FE. Số dư hiển thị và giao dịch
demo chỉ tồn tại trong phiên, không ghi vào MCP. Người nhận đã lưu và dịch vụ
yêu thích được lưu trên trình duyệt. Trợ lý gửi danh sách Chuyển tiền nhanh
hiện tại kèm yêu cầu chat/voice để khớp tên chính xác.

## Voice

Nhấn nút mic để mở panel, nhập tin nhắn hoặc thu âm tối đa 30 giây rồi bấm dừng.
Audio được mã hóa WAV PCM16 mono trước khi gửi BE. Đóng panel giữ hội thoại
nhưng dừng thu âm. Camera/micro cần HTTPS hoặc localhost; lỗi TTS không chặn text.
Hợp đồng SSE và workflow: [tài liệu BE](../BE/docs/workflow-client.md) trong workspace tích hợp.

## Chất lượng và build

```sh
npm run lint
npm run format:check
npm test
npm run build
npm run check
```

`check` chạy cả bốn bước trên. Sửa định dạng bằng `npm run format`;
sửa lỗi lint tự động bằng `npm run lint:fix`.
ESLint kiểm tra JavaScript/JSX; Prettier chuẩn hóa code, JSON, CSS và tài liệu.

Production dùng Nginx, proxy `/api`, hỗ trợ SSE và SPA fallback, có `/healthz`.
Image cũng có `/health` cho AgentBase Runtime, nghe cổng 8080. Nginx đọc
`BACKEND_URL` khi container khởi động; mặc định `http://backend:8000` cho Compose.
Khi deploy FE riêng, đặt `BACKEND_URL=https://<endpoint-BE>` (URL gốc, không có
`/api`, `/docs` hoặc dấu `/` cuối). HTTPS upstream bật SNI để gọi endpoint BE.
Giữ `api.baseUrl` rỗng trong app-config để trình duyệt gọi qua proxy cùng origin.
Command và Args trên AgentBase để trống, sử dụng CMD mặc định của image.
Image tự bỏ dấu `/` cuối `BACKEND_URL` để giữ nguyên đường dẫn `/api/`.
Giá trị chứa `/api`, `/docs` hoặc query sẽ bị từ chối lúc khởi động.
Compose mount app-config chỉ đọc: sửa xong tải lại trang. Source code thay đổi cần build lại image.
