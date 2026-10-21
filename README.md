# VTB Voice Banking

Ứng dụng demo ngân hàng với React/Vite và FastAPI: trợ lý chat/voice, tài sản,
giao dịch, phân tích thu chi và chuyển tiền mô phỏng.

## Thành phần

| Thư mục | Thành phần | Tài liệu |
| --- | --- | --- |
| `FE/` | Giao diện React/Vite (nginx, cổng 8080) | [FE/README.md](FE/README.md) |
| `BE/` | Agent backend FastAPI: ReAct + function calling, workflow, ASR/TTS | [BE/README.md](BE/README.md) |
| `mcp-server/` | MCP server 20 tool + REST, schema PostgreSQL, dữ liệu mock, cấu hình MCP Gateway/Policy | [mcp-server/README.md](mcp-server/README.md), [mcp-server/CONTRACT.md](mcp-server/CONTRACT.md) |
| `asr-system/` | Dịch vụ nhận dạng giọng nói (ONNX) | `asr-system/run.sh`, `asr-system/deploy.sh` |

```
FE ──/api──▶ BE (agent, LLM GreenNode MaaS) ──MCP──▶ mcp-server ──▶ PostgreSQL (vDB)
                 └──▶ asr-system (speech-to-text)
```

Trên GreenNode AgentBase, `BE/backend` và `mcp-server` chạy thành hai Custom Agent
runtime riêng (cổng 8080, `GET /health`). Biến môi trường nạp lúc tạo/cập nhật
runtime, không nằm trong image hay repo.

`compose.yaml` ở thư mục này chạy FE + BE; MCP server và DB chạy riêng theo
`mcp-server/README.md`.

## Chạy bằng Docker

1. Copy `BE/.env.example` thành `BE/.env` và điền cấu hình LLM, MCP, ASR; TTS tùy chọn.
2. Chạy `docker compose up -d --build` tại thư mục này.
3. Mở FE tại http://localhost:8080 và Swagger tại http://localhost:8000/docs.

Yêu cầu Docker Desktop/Engine với Linux containers và Compose hỗ trợ
`env_file.required`. Dịch vụ chạy trên máy host cần dùng `host.docker.internal`
trong URL của container.

```sh
docker compose logs -f backend frontend
docker compose down
```

## Phát triển local

- Python 3.12+: tạo virtualenv trong `BE/backend/.venv`, cài
  `python -m pip install -r requirements-dev.txt` tại `BE/backend`.
- Khởi động BE: `python -m uvicorn app.main:app --reload --port 8000`.
- Node.js 22.12+: tại `FE`, chạy `npm ci`, rồi `npm run dev`.
- Vite proxy `/api` sang BE cổng 8000. Giữ `api.baseUrl` rỗng trong
  `FE/public/app-config.json` khi dùng proxy.

## Cấu hình và dữ liệu

| File | Mục đích |
| --- | --- |
| `BE/.env` | Endpoint và khóa dịch vụ, không commit |
| `BE/backend/app/config/workflows.json` | Intent, rule, thứ tự hỏi, điều hướng và lời thoại |
| `BE/backend/app/config/system_prompt.yaml` | Prompt LangChain: tên, phiên bản, biến và template |
| `FE/public/app-config.json` | Cấu hình công khai của FE và dữ liệu demo |

Compose mount cấu hình BE và FE ở chế độ chỉ đọc. Sửa workflow/prompt xong
chạy `docker compose restart backend`; sửa app-config rồi tải lại trang.
Không đặt bí mật trong app-config vì trình duyệt đọc được file này.

FE mặc định lấy hồ sơ, tài sản và giao dịch từ BE/MCP. MCP hiện gắn khách hàng
ở phía server; `customer_id` không thay đổi khách hàng của MCP.
Chuyển tiền thường/nhanh/QR được xác nhận mô phỏng trên FE, cập nhật số dư
hiển thị và lịch sử trong phiên; không ghi vào MCP. Tải lại trang sẽ tải lại
dữ liệu nguồn và mất giao dịch mô phỏng trong phiên.

Người nhận qua trợ lý chỉ khớp tên đầy đủ hoặc tên gợi nhớ trong danh sách
Chuyển tiền nhanh. Không tìm thấy thì mở chuyển thường và giữ số tiền;
trùng tên thì yêu cầu chọn. Danh bạ MCP trong Dịch vụ là nguồn tra cứu riêng.

Hội thoại và workflow lưu trong RAM BE; restart sẽ mất phiên. Camera/micro
cần HTTPS hoặc localhost. Nếu TTS lỗi, câu trả lời chữ vẫn sử dụng được.

## Kiểm tra chất lượng

Tại `FE`:

```sh
npm run check
```

Tại `BE/backend`, sau khi kích hoạt virtualenv:

```sh
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m pip check
```

Mỗi repository có CI riêng cho lint, format và test. Các bài kiểm thử BE
mock dịch vụ ngoài, không cần API key thật.

## Tài liệu

- [Backend và API](BE/README.md)
- [Frontend](FE/README.md)
- [Hợp đồng workflow/SSE](BE/docs/workflow-client.md)
- [Chỉnh kịch bản và prompt](BE/docs/workflow-configuration.md)
- [Voice hiện tại và phương án streaming](BE/docs/voice-streaming-client.md)
- [MCP server, dữ liệu mock và deploy](mcp-server/README.md)
- [Hợp đồng tích hợp MCP ↔ agent ↔ giao diện](mcp-server/CONTRACT.md)
- [MCP Gateway + Policy Group](mcp-server/deploy/GATEWAY.md)

## Khai báo xuất xứ và dữ liệu

- **Dữ liệu:** toàn bộ là dữ liệu mô phỏng (mock/synthetic) sinh bởi
  `mcp-server/db/generate_seed.py`. Không dùng dữ liệu khách hàng thật.
  Lãi suất và sản phẩm là giả lập.
- **Code:** viết trong thời gian cuộc thi, có sử dụng trợ lý lập trình AI
  (Claude, Claude Code). Thư viện mã nguồn mở theo `requirements.txt` /
  `package.json` của từng thành phần.
- **Model:** LLM trên GreenNode MaaS; mô hình ASR ONNX trong `asr-system/models`.
- **Bí mật:** không commit key/mật khẩu; cấu hình qua biến môi trường
  (`.env` local, env của AgentBase Runtime). Xem `.env.example` của từng thành phần.
