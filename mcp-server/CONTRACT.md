# Hợp đồng tích hợp: MCP server ↔ Agent ↔ Giao diện app

Tài liệu cho người làm **agent** (LangGraph) và người làm **giao diện app + giọng nói**.

## 1. Luồng tổng thể

```
 Người dùng bấm icon micro
        │  (giọng nói → STT → text)
        ▼
 Giao diện app ──POST /invocations──▶ Agent (AgentBase Runtime)
   (frontend)     header: X-GreenNode-AgentBase-User-Id = KH0001    │
        ▲                                                          │ MCP streamable HTTP
        │                                                          ▼
        │  {response, speech, ui_actions[]}            MCP server (repo này) ──▶ Postgres (vDB)
        │                                               header: X-Api-Key, X-Customer-Id
        │
        └── ui_action.type == "navigate" → mở màn hình, gọi GET /api/actions/{id} lấy dữ liệu điền sẵn
```

## 2. Agent gọi MCP server

| Mục | Giá trị |
|---|---|
| URL | `https://<endpoint>/mcp` (streamable HTTP, stateless, trả JSON) |
| `X-Api-Key` | `MCP_API_KEY` (bí mật, lưu ở env của agent, không đưa vào prompt) |
| `X-Customer-Id` | Mã khách **đã đăng nhập**, agent lấy từ `context.user_id` của AgentBase SDK, **không lấy từ LLM** |
| `X-Session-Id` | `context.session_id`, ghi vào audit log |
| `X-Model-Name` | Tên model đang dùng, ghi vào audit log |

Không có tool nào nhận tham số `customer_id`, nên prompt injection kiểu "xem tài khoản KH0002" không có tác dụng.

**Khi đi qua MCP Gateway** (xem [deploy/GATEWAY.md](deploy/GATEWAY.md)):
- Agent gọi URL của Gateway với `Authorization: Bearer <IAM token>`, **không** gửi `X-Api-Key`. Gateway lấy key từ AgentBase Identity rồi gắn vào request.
- Runtime MCP đặt `VB_CUSTOMER_ID=KH0001` để không phụ thuộc việc Gateway có chuyển tiếp `X-Customer-Id` hay không. Nếu header này vẫn tới server và khác `KH0001`, request bị từ chối.
- Policy chặn `open_transfer_screen` trên 100 triệu và `open_loan_screen` trên 500 triệu. Khi bị chặn, tool trả lỗi; agent hướng dẫn khách thao tác trực tiếp trên app hoặc ra quầy.

### Ví dụ LangGraph (langchain-mcp-adapters)

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

async def build_agent(customer_id: str, session_id: str):
    client = MultiServerMCPClient({
        "bank": {
            "transport": "streamable_http",
            "url": os.environ["BANK_MCP_URL"],            # https://.../mcp
            "headers": {
                "X-Api-Key": os.environ["BANK_MCP_API_KEY"],
                "X-Customer-Id": customer_id,             # từ context.user_id, KHÔNG từ LLM
                "X-Session-Id": session_id,
                "X-Model-Name": os.environ["LLM_MODEL"],
            },
        }
    })
    tools = await client.get_tools()
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)

# Sau khi chạy agent, gom ui_action từ ToolMessage để trả cho giao diện:
ui_actions = []
for m in result["messages"]:
    if m.type == "tool" and m.name in ("open_transfer_screen", "open_savings_screen", "open_loan_screen",
                                       "cancel_pending_action"):
        data = json.loads(m.content if isinstance(m.content, str) else m.content[0]["text"])
        if data.get("ui_action"):
            ui_actions.append(data["ui_action"])
return {"response": final_text, "ui_actions": ui_actions}
```

Gợi ý system prompt: dùng chuỗi `INSTRUCTIONS` trong `app/server.py`. Server cũng gửi chuỗi này qua MCP `instructions`.

## 3. Danh sách tool

Mọi kết quả đều là JSON và có trường **`speech`**: câu tiếng Việt đã viết sẵn, số tiền đã đọc thành chữ. Agent nên đọc gần như nguyên văn cho TTS.

| Tool | Khi nào dùng |
|---|---|
| `get_current_date` | Trước khi tính "tháng này", "tuần trước" |
| `parse_vnd_amount(text)` | **Luôn dùng** để đổi số tiền khách nói ra số. Đọc lại `words` và chờ khách nói "đúng" |
| `get_customer_profile` | Lấy cách xưng hô (`salutation`) |
| `get_account_balances` | Số dư tài khoản thanh toán, các sổ tiết kiệm trong tài khoản (ngày đến hạn), khoản vay |
| `get_recent_transactions(limit, direction)` | "Mấy giao dịch gần đây" |
| `search_transactions(date_from, date_to, category, keyword, ...)` | "Tiền điện tháng này", "đóng học phí khi nào" |
| `get_month_overview(month)` | "Tháng này tôi tiêu thế nào" (thu, chi, top 3 khoản, so với tháng trước) |
| `get_spending_summary` / `get_income_summary` | Tổng chi / thu theo khoảng ngày |
| `compare_periods` | So sánh 2 kỳ |
| `get_category_trend(category, months)` | "Tiền điện mấy tháng nay" |
| `detect_unusual_transactions` | "Có giao dịch nào lạ không" |
| `find_beneficiary(name)` / `list_beneficiaries` | "Chuyển cho con trai" → tìm người nhận đã lưu |
| `search_products` | Lãi suất tiết kiệm, các loại vay (MOCK) |
| `check_transfer_risk` | Tự gọi bên trong `open_transfer_screen`, agent có thể gọi riêng |
| `open_transfer_screen(amount, beneficiary_id?, note?, risk_acknowledged?)` | Mở màn hình chuyển tiền + điền sẵn |
| `open_savings_screen(amount, term_months?)` | Mở màn hình gửi tiết kiệm online + điền sẵn |
| `open_loan_screen(amount, loan_type?, term_months?)` | Mở màn hình đăng ký vay + điền sẵn |
| `cancel_pending_action(action_id)` | Khách đổi ý |

`category` nhận cả mã (`electricity`) lẫn cách nói (`"tiền điện"`, `"đi chợ"`, `"học phí"`). Danh sách đầy đủ ở resource `vb://categories`.

### Kịch bản chuyển tiền chuẩn

```
Khách: "Chuyển cho con trai một triệu rưỡi"
 1. parse_vnd_amount("chuyển cho con trai một triệu rưỡi") → amount=1500000, words="một triệu năm trăm nghìn đồng"
 2. find_beneficiary("con trai") → 1 kết quả, beneficiary_id=2
 3. Agent: "Em chuyển cho con trai Trần Minh Khoa một triệu năm trăm nghìn đồng, đúng không ạ?"
 4. Khách: "Đúng rồi"
 5. open_transfer_screen(amount=1500000, beneficiary_id=2) → ui_action navigate + speech
 6. Agent đọc speech, trả ui_action cho giao diện
```

Nếu `open_transfer_screen` trả về `blocked: true` (rủi ro cao, ví dụ nội dung có "xác minh", "công an"): agent đọc cảnh báo và hỏi lại. Chỉ gọi lại với `risk_acknowledged=true` khi khách nói rõ vẫn muốn tiếp tục.

## 4. `ui_action` (giao diện nhận từ agent)

```json
{
  "type": "navigate",                      // hoặc "close" (khi hủy)
  "screen": "transfer",                    // transfer | savings_open | loan_apply
  "action_id": "act_m-HVZmJPyMSc",
  "expires_at": "2026-10-21T09:45:00",     // mặc định 15 phút
  "prefill": {
    "amount": 1500000,
    "amount_text": "1.500.000đ",
    "amount_words": "một triệu năm trăm nghìn đồng",
    "beneficiary": {"beneficiary_id": 2, "name": "Trần Minh Khoa", "relationship": "con trai",
                    "bank": "Vietcombank", "account_number": "****7890"}
  },
  "required_user_inputs": ["Kiểm tra lại tên người nhận...", "Nội dung chuyển khoản", "Xác nhận ... OTP"]
}
```

- `prefill` trong ui_action đã **che số tài khoản**, vì nó đi qua LLM. Muốn điền số tài khoản đầy đủ, giao diện gọi `GET /api/actions/{action_id}`.
- `savings_open.prefill`: `amount`, `term_months?`, `product_code?`, `interest_rate_mock?`, `estimated_interest?`, `source_account`.
- `loan_apply.prefill`: `amount`, `product_code?`, `product_name?`, `interest_rate_mock?`, `term_months?`, `estimated_monthly_payment?`. Khách chưa nói loại vay thì không có `product_code`, `required_user_inputs` có "Chọn loại vay".
- `required_user_inputs`: danh sách để giao diện **tô sáng các ô khách phải tự điền**. Nên đọc to cho người mắt kém.

## 5. REST cho giao diện app

Header: `X-Api-Key: <UI_API_KEY>` (mặc định bằng `MCP_API_KEY`), `X-Customer-Id: KH0001`.

| Method | Path | Mô tả |
|---|---|---|
| GET | `/health` | Không cần key. `{"status":"ok","db":"ok"}` |
| GET | `/api/me/accounts` | Số dư (dùng cho trang chủ app giả lập) |
| GET | `/api/me/transactions?limit=30` | Lịch sử giao dịch |
| GET | `/api/me/beneficiaries` | Danh bạ người nhận (đã che số) |
| GET | `/api/actions/{action_id}` | Dữ liệu điền sẵn **đầy đủ** của màn hình. Hết hạn thì `status="expired"` |
| POST | `/api/actions/{action_id}/status` | Body `{"status": "opened" \| "submitted" \| "cancelled"}` |

Vòng đời `pending_actions`: `created → opened → submitted | cancelled`, tự `expired` sau `ACTION_TTL_MINUTES`.
`submitted` nghĩa là khách đã tự bấm xác nhận trên màn hình giả lập. Server này **không bao giờ** tạo giao dịch.

> Demo: giao diện gọi thẳng REST bằng key là chấp nhận được. Production: giao diện gọi qua backend của app;
> `X-Customer-Id` phải lấy từ token đăng nhập (OAuth/JWT), không phải header thô.

## 6. Khách hàng mock để demo

| Mã | Persona | Ghi chú |
|---|---|---|
| **KH0001** | Anh Trần Quốc Hưng, 51 tuổi, lão thị | Khách hàng duy nhất, 1 tài khoản thanh toán (sổ tiết kiệm và khoản vay nằm trong tài khoản), 18 tháng, 1.859 giao dịch, 7 người nhận đã lưu |

Người nhận đã lưu của KH0001: `1` vợ Lê Thị Mai · `2` con trai Trần Minh Khoa · `3` con gái Trần Ngọc Anh · `4` mẹ Phạm Thị Lụa · `5` em trai Trần Quốc Tuấn · `6` cô giáo dạy thêm Nguyễn Thị Hoa · `7` BQL chung cư.
