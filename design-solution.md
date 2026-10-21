# Thiết kế Backend — VietinBot Voice Agent

> Tài liệu thiết kế ban đầu, giữ lại để tham khảo. Cấu trúc và lệnh chạy hiện tại nằm trong [README](README.md); hợp đồng đang triển khai nằm trong [workflow-client.md](docs/workflow-client.md). Một số phương án bên dưới chưa được tích hợp.

## 1. Tổng quan

Backend là một **Voice Agent** tài chính cá nhân của VietinBank: nhận **audio** từ người dùng (giọng nói tiếng Việt), hiểu ý định, thực hiện yêu cầu bằng cách gọi các banking tool, và trả về **câu trả lời dạng text + audio (TTS)** kèm trace các bước thực thi.

Trọng tâm use case: **trợ lý tài chính cá nhân** — báo cáo chi tiêu, thống kê giao dịch, phát hiện giao dịch bất thường, lập kế hoạch chi tiêu 50/30/20, tư vấn sản phẩm tiết kiệm/vay.

### Nguyên tắc thiết kế

- **Audio-in / audio-out**: request là file audio (voice), response stream về cả transcript, text token và audio TTS để UI hiển thị và phát song song.
- **Agent không bịa số liệu**: mọi số liệu tài chính phải đến từ tool (MCP server); LLM chỉ tổng hợp và diễn đạt.
- **Streaming end-to-end**: SSE cho text/tool-trace; audio trả qua URL hoặc base64 chunk để client phát ngay.
- **Demo-friendly**: dữ liệu khách hàng mock qua MCP server `voice-banking-assistant`; đăng nhập demo bằng `customer_id`.

## 2. Kiến trúc tổng thể

```
┌──────────┐   audio (multipart)   ┌───────────────────────────────────────────────┐
│  Client   │ ───────────────────► │                 Backend (FastAPI)              │
│ (Web/App) │ ◄─────────────────── │                                               │
└──────────┘   SSE stream          │  /api/voice                                   │
                                     │    │                                          │
                                     │    ▼                                          │
                                     │  STT (Speech-to-Text)                         │
                                     │    "tháng này tôi tiêu thế nào?"              │
                                     │    ▼                                          │
                                     │  Agent Orchestrator (ReAct + function calling) │
                                     │    │  GLM (OpenAI-compatible API)              │
                                     │    ▼                                          │
                                     │  Tool Dispatcher ──► MCP server               │
                                     │    (local tools)      (voice-banking-assistant │
                                     │                        localhost:8080/mcp)     │
                                     │    ▼                                          │
                                     │  Session Memory (in-memory → Postgres)        │
                                     │    ▼                                          │
                                     │  TTS (Text-to-Speech)                          │
                                     │    ▼                                          │
                                     │  SSE: transcript / token / tool_call /         │
                                     │       tool_result / audio / done               │
                                     └───────────────────────────────────────────────┘
```

**Pipeline xử lý 1 lượt voice:**

1. Client upload audio (multipart/form-data) + `session_id` (nếu có) + `customer_id`.
2. **STT** chuyển audio → text tiếng Việt. Transcript được stream về client ngay (`transcript` event) để người dùng xác nhận đúng ý.
3. **Agent Orchestrator** chạy ReAct loop: build messages (system prompt + history + transcript) → gọi LLM stream → nếu LLM đòi tool thì thực thi và feed kết quả lại → lặp tới khi có câu trả lời cuối (tối đa `MAX_AGENT_STEPS` bước).
4. **TTS** chuyển câu trả lời cuối thành audio; trả về client cùng text.
5. Toàn bộ diễn ra qua **SSE** để client render token/trace theo thời gian thực.

## 3. Các thành phần

### 3.1. API Layer — `app/api/`

| Endpoint | Method | Mô tả |
|---|---|---|
| `/api/voice` | POST | Nhận audio (multipart, field `audio`; WAV PCM16 mono 16kHz), gọi STT `/transcribe`, chạy agent, trả SSE stream. Form kèm `session_id?`, `customer_id?` (mặc định demo KH2). Event đầu tiên là `transcript` để UI xác nhận đúng ý. |
| `/api/chat` | POST | Endpoint text (giữ lại cho debug/demo không mic), cùng SSE event format. |
| `/api/sessions/{id}/messages` | GET | Lấy lại lịch sử hội thoại. |
| `/api/health` | GET | Trạng thái service + LLM/STT/TTS config. |

**SSE events** (JSON, một event per dòng):

```jsonc
{"type": "transcript",  "text": "tháng này tôi tiêu thế nào?"}
{"type": "token",       "content": "..."}           // text trả lời, stream theo chunk
{"type": "tool_call",   "name": "get_month_overview", "args": {...}}
{"type": "tool_result", "name": "get_month_overview", "result": {...}}
{"type": "audio",       "format": "mp3", "data": "<base64>"}  // hoặc "url"
{"type": "done",        "session_id": "..."}
{"type": "error",       "message": "..."}
```

### 3.2. STT — Speech-to-Text

- Đầu vào: audio tiếng Việt (WAV PCM16 mono 16kHz hoặc raw PCM16).
- Triển khai: **ASR Voice API** (VNG Cloud agentbase-runtime, Zipformer + openWakeWord + Silero VAD). Có 2 chế độ:
  - **File mode** (đã tích hợp trong `/api/voice`): backend gọi `POST /transcribe` của ASR service với nội dung file audio → `{"text": "..."}`. Bỏ qua wake word/VAD, STT thẳng cả file.
  - **Streaming mode** (từ browser/app client): client mở WebSocket trực tiếp tới `wss://.../ws/voice`, stream mic PCM16 16kHz; service tự phát hiện wake word ("Hey Jarvis") + VAD cắt câu, trả event `text`; client gọi `/api/chat` với transcript đó.
- Output: text → trở thành `user_message` cho orchestrator. Phát transcript về client qua event `transcript`.
- Lưu ý: transcript thường CHỮ HOA, không dấu câu; agent vẫn xử lý bình thường.
- Tài liệu đầy đủ: `docs/asr-voice-websocket-api.md`.

### 3.3. Agent Orchestrator — `app/agent/orchestrator.py`

ReAct loop + function calling, streaming:

1. `user_message` (từ STT) + `session_id` → build messages: `system prompt` + history (tối đa ~10 lượt) + user message.
2. Gọi LLM stream (OpenAI-compatible SSE). Gom `content` và `tool_calls` từ các delta chunk.
3. Không có tool call → đây là câu trả lời cuối: stream token về client (chunk ~40 ký tự), rồi TTS.
4. Có tool call → thực thi từng call (yield event `tool_call`/`tool_result`), append kết quả vào messages với role `tool`, quay lại bước 2.
5. Vượt `MAX_AGENT_STEPS` (mặc định 5) → chèn message ép LLM trả lời bằng dữ liệu đã có, không gọi tool thêm.
6. Lưu assistant message vào session, yield `done`.

Bảo vệ: tool result bị clip ở 4000 ký tự trước khi đưa vào context; lỗi tool trả về dạng `{"error": ...}` để LLM tự diễn đạt lại với người dùng.

### 3.4. System Prompt — `app/agent/prompts.py`

VietinBot với quy tắc bắt buộc:

- LUÔN dựa trên số liệu thật từ tool, không bịa số liệu tài chính.
- Không biết hôm nay là ngày nào → gọi `get_current_date` trước khi tính "tháng này/tuần trước".
- Tư vấn sản phẩm → `search_products`, trích nguyên văn lãi suất, luôn nói rõ "lại suất tham khảo" (dữ liệu MOCK).
- Lập kế hoạch chi tiêu → `create_budget_plan` (50/30/20 từ dữ liệu thật 3 tháng).
- Phong cách: tiếng Việt, thân thiện, cấu trúc rõ, format VNĐ (VD: 12.500.000đ), ngắn gọn, kèm gợi ý hành động.

### 3.5. Tool Registry — `app/tools/registry.py`

Schema tool (OpenAI function-calling format) khớp tool thật trên MCP server + 1 local tool. Bộ tool hiện tại:

| Tool | Mô tả ngắn |
|---|---|
| `get_current_date` | Hôm nay + các mốc thời gian. Gọi trước khi tính khoảng ngày. |
| `get_customer_profile` | Tên, cách xưng hô, nghề nghiệp, nhu cầu của khách đang đăng nhập. |
| `get_account_balances` | Số dư, sổ tiết kiệm, khoản vay, kỳ trả tiếp theo. |
| `get_recent_transactions` | Giao dịch gần nhất ("dạo này tôi tiêu gì"). |
| `get_month_overview` | Tổng quan 1 tháng: thu, chi, dư, top chi, so tháng trước. |
| `get_spending_summary` | Tổng chi theo khoảng ngày, group by danh mục/tháng/nơi chi/nhóm. |
| `get_income_summary` | Tổng thu trong khoảng ngày. |
| `search_transactions` | Tìm giao dịch theo điều kiện + tổng tiền. |
| `compare_periods` | So sánh chi tiêu 2 kỳ, toàn bộ hoặc 1 danh mục. |
| `get_category_trend` | Khoản chi theo từng tháng + trung bình các tháng trước. |
| `detect_unusual_transactions` | Giao dịch bất thường (người nhận lạ, giờ khuya, trùng lặp, lừa đảo). |
| `search_products` | Sản phẩm tiết kiệm/vay, lãi suất tham khảo (MOCK). |
| `create_budget_plan` | **Local tool**: kế hoạch 50/30/20 từ thu nhập + chi tiêu 3 tháng gần nhất. |

### 3.6. MCP Client — `app/tools/mcp_client.py`

- Nguồn dữ liệu khách hàng: **MCP server `voice-banking-assistant`** (`MCP_BASE_URL`, mặc định `http://localhost:8080/mcp`), giao thức JSON-RPC 2.0 qua HTTP POST (`tools/call`), auth header `X-Api-Key`. Server chạy stateless, gắn cố định 1 khách hàng theo `VB_CUSTOMER_ID`.
- `dispatch_tool(name, customer_id, args)`: tool local (`create_budget_plan`) tính tại chỗ từ dữ liệu MCP; còn lại forward qua MCP. Kết quả text content được parse JSON; lỗi MCP/ToolError chuẩn hóa thành `{"error": ...}`.
- Cần `docker compose up` MCP server **trước** khi chạy backend.

### 3.7. TTS — Text-to-Speech

- Đầu vào: câu trả lời cuối của agent (ưu tiên các con số/thông điệp chính, tránh đọc lại bảng biểu dài).
- Triển khai: API TTS (OpenAI-compatible `/audio/speech` hoặc vendor VN giọng northern/southern female tự nhiên). Config env `TTS_*`.
- Output: audio mp3/wav → event `audio` (base64 chunk hoặc URL có TTL) để client phát.

### 3.8. Session Memory — `app/agent/memory.py`

- In-memory `SessionStore`: mỗi session giữ messages OpenAI-format + `customer_id`; history giới hạn ~20 message (10 lượt), tự cắt các cặp tool_call/tool cũ nhất.
- Backend **không có DB riêng** — mọi số liệu tài chính đến từ MCP server. Session mất khi restart process (chấp nhận cho demo); nếu cần persist thì thêm bảng `chat_sessions`/`chat_messages` sau.

## 4. Luồng tuần tự (ví dụ: "Tháng này tôi tiêu thế nào?")

```
Client          Backend                     LLM                MCP server
  │  audio ────►│
  │             │ ── STT ──► "tháng này tôi tiêu thế nào?"
  │ ◄─transcript│
  │             │ ── messages ──────────────►│
  │             │ ◄── tool_call: get_current_date
  │ ◄─tool_call─│ ─────────────────────────────────────────►│ get_current_date
  │ ◄─tool_result (tool_result)
  │             │ ── messages(+tool) ───────►│
  │             │ ◄── tool_call: get_month_overview(month="2026-10")
  │ ◄─tool_call─│ ─────────────────────────────────────────►│ get_month_overview
  │ ◄─tool_result
  │             │ ── messages(+tool) ───────►│
  │ ◄─token ────│ ◄─── final content stream
  │ ◄─audio ────│ ── TTS(final content)
  │ ◄─done ─────│
```

## 5. Công nghệ

| Thành phần | Công nghệ |
|---|---|
| API framework | FastAPI + sse-starlette (SSE), uvicorn |
| LLM | GLM qua OpenAI-compatible endpoint (`LLM_BASE_URL`, `LLM_MODEL`) |
| STT | ASR Voice API (VNG Cloud agentbase-runtime) — `/transcribe` + WebSocket `/ws/voice` |
| TTS | (chưa tích hợp) API TTS vendor VN |
| Tools/data | MCP server `voice-banking-assistant` (JSON-RPC over HTTP) — DB riêng của MCP |
| Deploy | Docker Compose (backend; MCP server chạy compose riêng) |

## 6. Cấu hình (env)

```bash
# LLM (OpenAI-compatible)
LLM_API_KEY=...
LLM_BASE_URL=https://...
LLM_MODEL=glm-4.6

# STT (ASR Voice API — VNG Cloud agentbase-runtime)
ASR_BASE_URL=https://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24.agentbase-runtime.aiplatform.vngcloud.vn

# TTS
TTS_API_KEY=...
TTS_BASE_URL=...
TTS_MODEL=...
TTS_VOICE=...

# MCP server (nguồn dữ liệu khách)
MCP_BASE_URL=http://localhost:8080/mcp
MCP_API_KEY=dev-key

# Khác
ALLOW_ORIGINS=http://localhost:3000
MAX_AGENT_STEPS=5
```

## 7. Chạy hệ thống

```bash
# 1. MCP server voice-banking-assistant (nguồn dữ liệu khách)
cd voice-banking-assistant && docker compose up -d   # localhost:8080/mcp

# 2. Backend (không có DB riêng)
docker compose up --build    # backend: localhost:8000
```

## 8. Hướng phát triển tiếp theo

- [x] Đưa STT vào `/api/voice` (file mode qua `/transcribe` của ASR Voice API).
- [ ] TTS cho `/api/voice` (audio-out).
- [ ] Chuyển SessionStore sang Postgres (bảng đã sẵn trong schema).
- [ ] Streaming TTS theo câu (chia câu trả lời thành sentence, TTS từng đoạn để giảm độ trễ phát audio đầu tiên).
- [ ] Barge-in / VAD: cho phép người dùng ngắt lời khi agent đang nói.
- [ ] Xác thực khách hàng thật (thay `customer_id` mặc định demo) + RBAC cho tool nhạy cảm (chuyển tiền, mở sổ).
- [ ] Đánh giá chất lượng agent: bộ test Q&A chuẩn, đo accuracy số liệu so với dữ liệu gốc.
