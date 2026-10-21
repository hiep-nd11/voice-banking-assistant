# Cấu hình kịch bản trợ lý

Sửa `backend/app/config/workflows.json` để thay đổi kịch bản; sửa
`backend/app/config/system_prompt.yaml` để thay đổi hướng dẫn LLM.
Không cần chỉnh `workflows.py` khi sửa lời thoại, quy tắc nhận diện,
thứ tự hỏi thông tin, màn hình, số tiền tối thiểu hoặc kỳ hạn.

## Các phần trong workflows.json

- `version`: phiên bản cấu trúc, hiện là `1`.
- `ttl_seconds`: thời gian hết hạn workflow.
- `banks`: tên ngân hàng và cách gọi/viết tắt.
- `non_action_pattern`: loại câu hướng dẫn, giả định hoặc phủ định khỏi nhánh hành động.
- `rules`: duyệt theo thứ tự; quy tắc đầu tiên khớp sẽ chọn intent.
  Dùng `pattern` (regex trên chữ thường, không dấu), `all`, `any`, hoặc
  predicate có sẵn `has_destination` / `has_recipient`. Mỗi điều kiện chỉ có một toán tử.
- `scenarios`: định nghĩa từng intent, loại `flow` hoặc `navigation`.
- `messages`: lời thoại và thông báo lỗi, có thể dùng placeholder được engine cung cấp.

Ví dụ thêm cách nói để mở lịch sử: chèn quy tắc trước những quy tắc tổng quát:

```json
{"intent": "transactions", "when": {"pattern": "\\b(xem sao ke|kiem tra giao dich)\\b"}}
```

Một flow có `requirements` là danh sách thông tin cần hỏi theo thứ tự:

```json
{
  "slot": "amount",
  "step": "awaiting_amount",
  "message": "ask_amount",
  "screen": "workflow"
}
```

`message` trỏ tới khóa trong `messages`. Prompt hỏi slot không có placeholder.
`screen` là màn hình gợi ý; với màn `workflow`, engine áp dụng `step_screens`
của scenario, rồi mới dùng màn mặc định `screen`.
`minimum`, `terms` và `max_term` kiểm soát giới hạn của flow.

Placeholder của các lời thoại tổng hợp phải giữ nguyên: `{name}`,
`{minimum}`, `{term_months}`, `{amount_text}`, `{detail}` tại đúng message tương ứng.
Có thể đổi phần chữ xung quanh placeholder.

## Áp dụng thay đổi

Cấu hình được đọc một lần khi BE khởi động. Các Compose trong dự án đã mount
thư mục cấu hình từ máy vào container. Sau khi sửa, chạy từ thư mục Compose:

```sh
docker compose restart backend
```

Nếu chạy bằng image không mount thư mục cấu hình, cần build lại image.
Cấu hình sai sẽ khiến BE báo lỗi khi khởi động; khôi phục file đúng rồi restart.
Đổi lời thoại hoặc rule không làm đổi schema API/SSE.

## Phần vẫn nằm trong code

Engine Python giữ thuật toán đọc số tiền/QR, khớp chính xác danh bạ Chuyển tiền nhanh,
kiểm tra dữ liệu, phiên bản workflow, chống lặp request, xử lý event và gọi tool.
Thêm một nghiệp vụ mới có handler hoặc màn hình mới vẫn cần viết code;
JSON không thực thi Python hay tự tạo API/màn hình.
`system_prompt.yaml` điều khiển nhánh LLM, không thay thế các rule phía trên.

Kiểm tra trước khi áp dụng, từ `BE/backend`:

```sh
python -m unittest discover -s tests -v
```

## PromptTemplate (LangChain)

`system_prompt.yaml` uses a versioned definition (`name`, `version`, `input_variables`,
`template_format`, `template`). LangChain PromptTemplate validates and renders
`max_steps`. Update `version` when editing the template. YAML is read with
`safe_load`; only the f-string template format is supported. No remote prompt
service or tracing is configured. Restart the backend to load changes.
