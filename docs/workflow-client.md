# Kịch bản trợ lý và giao diện

Chat và voice dùng chung engine `app/agent/workflows.py`, đọc định nghĩa từ `app/config/workflows.json`. Các câu lệnh rõ ràng đi qua bộ nhận intent trước; các cách diễn đạt khác có thể được LLM chuyển tới tool `start_banking_workflow`. BE kiểm tra intent và khớp người nhận với danh sách Chuyển tiền nhanh do FE gửi. Câu hướng dẫn, giả định và phủ định không được kích hoạt điều hướng bằng tool này.

## Các luồng hiện có

- **Chuyển thường:** nói số tài khoản/ngân hàng/số tiền sẽ điền trực tiếp vào form chuyển tiền gốc. Ví dụ “chuyển cho tài khoản 22212132 Vietcombank 5 triệu” -> account=22212132, bank=Vietcombank, amount=5000000. Thiếu trường nào hỏi trường đó; không bắt chọn người đã lưu. Số tài khoản được tách khỏi câu trước khi đọc số tiền.
- **Chuyển nhanh:** mở đúng mục Chuyển tiền nhanh hiện có để chọn người đã lưu. Ba lựa chọn chuyển thường / chuyển nhanh / QR giữ nguyên; đổi phương thức thủ công sẽ hủy kịch bản trợ lý trước để không ghi đè form mới.

- **Chuyển bằng QR:** mở màn QR, chờ người dùng bấm camera/chọn ảnh/dán nội dung; kiểm tra dữ liệu QR; hỏi số tiền còn thiếu; đối chiếu tên người nhận; kiểm tra rủi ro; chuẩn bị thông tin.
- **Chuyển theo tên:** khớp chính xác tên hoặc tên gợi nhớ trong Chuyển tiền nhanh do FE gửi; trùng tên thì yêu cầu chọn; không tìm thấy thì báo không có trong danh bạ và mở chuyển thường, giữ số tiền. Không dùng kết quả tìm tên gần giống từ MCP. Nút xác nhận trên FE tạo giao dịch demo cục bộ.
- **Tiết kiệm:** thu thập số tiền và kỳ hạn; kiểm tra tối thiểu 1 triệu và kỳ hạn 1/3/6/9/12/24 tháng; chuẩn bị qua MCP.
- **Vay:** thu thập số tiền (tối thiểu 5 triệu) và kỳ hạn nếu có; chuẩn bị đăng ký qua MCP.
- **Tra cứu:** mở Tài sản, Tiết kiệm, Khoản vay, Giao dịch, Phân tích hoặc Kế hoạch. Một lượt tra cứu không hủy giao dịch đang chuẩn bị.
- **Chỉnh sửa:** “đổi thành một triệu”, “đổi người nhận sang…”, “nội dung là…”, “quay lại”, “đổi QR”, “hủy đi”. Chỉnh sửa yêu cầu đã chuẩn bị sẽ hủy mã chuẩn bị cũ trước khi tạo mã khác.

Ví dụ thử: “Chuyển tiền bằng QR”; “Chuyển cho con trai 500k”; “Gửi tiết kiệm 10 triệu” rồi “sáu tháng”; “Tôi muốn vay 10 triệu 12 tháng”; “Cho tôi xem số dư”; “Lập kế hoạch chi tiêu”. Bộ đọc tiền được gọi qua MCP, kỳ hạn và nội dung được tách trước để không bị gộp vào số tiền.

## SSE

Ngoài các event chat cũ, `/api/chat` và `/api/voice` trả thêm:

- `session`: định danh phiên, gửi sớm để FE lưu trước khi điều hướng/TTS.
- `flow_state`: `{session_id, flow}`. `flow` gồm `id`, `intent`, `step`, `version`, `slots`, `candidates`, `risk?`, `action_id?`, `prepared?`, `expires_at`. `flow: null` nghĩa là đã hủy/kết thúc.
- `ui_action`: `{action: "navigate", screen, feature?, flow_id?, session_id}`. FE chỉ chấp nhận màn hình và tính năng trong danh sách cho phép.

FE thu gọn trợ lý khi chuyển màn hình, giữ component và kết nối SSE; không tự mở camera/micro. Người dùng có thể tiếp tục nói hoặc nhập. `beneficiary_id` trong workflow chuyển theo tên chỉ định danh ứng viên trong danh sách demo hiện tại, không phải ID khách hàng hay tài khoản xác thực của MCP. Biểu mẫu không suy diễn số tài khoản đầy đủ từ số đã che. Tên lấy từ QR chưa được ngân hàng xác minh.

## Callback từ màn hình

`GET /api/workflows/{session_id}` lấy trạng thái hiện tại để khôi phục sau khi tải lại trang.

`POST /api/workflows/{session_id}/events`:

```json
{
  "flow_id": "uuid",
  "version": 2,
  "request_id": "uuid-moi-cho-moi-thao-tac",
  "event": "form_updated",
  "payload": {"amount": 500000, "note": "Hoc phi"}
}
```

Các event: `qr_scanned`, `rescan`, `recipient_search`, `recipient_selected`, `change_recipient`, `form_updated`, `prepare`, `cancel`, `resume`. Kết quả là `{events: [...]}` sử dụng cùng cấu trúc state/action/token/done như SSE.

- `qr_scanned`: bank, account, recipient?, amount?, memo?. Số tiền QR khác lời nói sẽ yêu cầu lưu/kiểm tra lại trước khi chuẩn bị.
- `recipient_search`: name; `recipient_selected`: beneficiary_id thuộc danh sách BE đã trả.
- `form_updated`: amount?, term_months?, note?, recipient?, bank?, account?. Bank/account chỉ sửa cho chuyển thường hoặc QR; người nhận định danh bằng beneficiary_id không được sửa tài khoản tùy ý. API vẫn hỗ trợ kiểm tra/chuẩn bị yêu cầu; form chuyển tiền FE hiện xác nhận mô phỏng cục bộ, không gọi `form_updated` hoặc `prepare`.
- `prepare`: risk_acknowledged?; chỉ hợp lệ khi đã ở bước review. Rủi ro được kiểm tra lại ngay trước khi chuẩn bị.
- `cancel`, `resume`, `rescan`, `change_recipient`: payload rỗng.

BE khóa thao tác theo phiên, kiểm tra version và giữ 32 request gần nhất. FE gửi lại cùng request_id nếu mất mạng khi chưa nhận được kết quả. Gửi lặp hợp lệ không tạo thêm yêu cầu MCP; dữ liệu cũ trả 409, hết hạn trả 410, dữ liệu sai trả 422.

## Giới hạn thực tế

Trạng thái và lịch sử đang lưu trong bộ nhớ, hết hạn sau 30 phút hoặc mất khi BE khởi động lại. Mô hình phiên hiện tại phục vụ demo, chưa thay thế xác thực khách hàng thật. MCP gắn khách hàng theo cấu hình server.

Không có API thực thi chuyển tiền/OTP. FE cho phép xác nhận giao dịch mô phỏng cục bộ, cập nhật số dư hiển thị và ghi giao dịch demo trong phiên; không ghi vào MCP. Lời nói “đồng ý” không thực thi giao dịch. Các API `prepare` vẫn chỉ chuẩn bị yêu cầu; tiết kiệm/vay chưa có bước thực thi.

## Danh sách chuyển tiền nhanh

Chat JSON gửi thêm `quick_recipients`, voice multipart gửi trường cùng tên dưới dạng JSON string. Mỗi người nhận có `bank`, `account` (6–20 chữ số), `recipient` và `nickname` tùy chọn. Danh sách tối đa 200 người; mặc định rỗng khi không gửi.

BE chỉ khớp tên đầy đủ hoặc tên gợi nhớ, hỗ trợ không dấu. Không tìm thấy thì báo không có tên đó trong danh bạ, mở chuyển thường, giữ số tiền và để trống người nhận. Trùng tên phải chọn. Danh sách này là dữ liệu demo từ FE, không phải bằng chứng xác thực khách hàng; không dùng ID trong danh sách để thực hiện giao dịch thật.
