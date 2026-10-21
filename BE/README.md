# VTB Banking Backend

FastAPI phục vụ trợ lý tài chính, workflow và adapter dữ liệu MCP.
Python 3.12+; cấu hình mẫu tại [`.env.example`](.env.example).

## Chạy local

Tại `backend`, tạo/kích hoạt `.venv`, sau đó:

```sh
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Hoặc tại `BE`: `docker compose up -d --build`. Swagger: http://localhost:8000/docs.
Compose tích hợp FE/BE ở thư mục cha được ưu tiên khi chạy toàn ứng dụng.
Image mặc định nghe cổng 8080 theo hợp đồng runtime; Compose local ghi đè thành 8000.

BE đọc `.env` ở thư mục `BE` và `BE/backend` theo đường dẫn source;
file thứ hai ưu tiên hơn, biến môi trường hệ thống ưu tiên cao nhất.
Không có fallback LLM khi thiếu cấu hình nhà cung cấp.

## Cấu trúc

```text
backend/
  app/
    agent/     # Điều phối LLM, engine workflow, session và loader prompt
    api/       # FastAPI routes và request schemas
    config/    # Workflow JSON và prompt YAML được chỉnh độc lập
    core/      # Settings, STT, TTS
    tools/     # Registry, MCP adapter và snapshot schema upstream
  tests/       # unittest, mock các dịch vụ ngoài
```

Không có DB local. Dữ liệu ngân hàng do MCP cung cấp; hội thoại/workflow lưu RAM.
FE thực hiện chuyển tiền mô phỏng. Các API chuẩn bị yêu cầu không thực thi giao dịch.

## API

| Method | Path | Nội dung |
| --- | --- | --- |
| GET | `/health`, `/api/health` | Health/runtime configuration status |
| GET | `/api/banking/overview` | Hồ sơ, tài khoản, giao dịch gần nhất |
| GET | `/api/banking/features` | Danh mục chức năng và schema |
| POST | `/api/banking/features/{feature}` | Tra cứu hoặc chuẩn bị yêu cầu theo schema |
| POST | `/api/chat` | Chat JSON → SSE |
| POST | `/api/voice` | WAV multipart, tối đa 10 MB → STT → SSE |
| GET | `/api/sessions/{session_id}/messages` | Lịch sử hội thoại |
| GET | `/api/workflows/{session_id}` | Trạng thái workflow |
| POST | `/api/workflows/{session_id}/events` | Thao tác với workflow |

Chi tiết: [workflow/SSE](docs/workflow-client.md),
[cấu hình workflow/prompt](docs/workflow-configuration.md),
[voice](docs/voice-streaming-client.md).
`banking_tools.json` là snapshot hợp đồng MCP, không phải nơi chỉnh kịch bản.

## Kiểm tra

Tại `backend`:

```sh
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m pip check
```

Tự sửa định dạng/import: `python -m ruff check . --fix` và `python -m ruff format .`.
Dependency runtime nằm trong `requirements.txt`; công cụ phát triển ở `requirements-dev.txt`.
