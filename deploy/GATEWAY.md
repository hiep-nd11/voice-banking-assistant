# Deploy qua MCP Gateway + Policy Group

```
Agent (Runtime, LangGraph) ──IAM bearer──▶ MCP Gateway "voice-banking-gw"
                                              │ 1. Inbound auth: IAM
                                              │ 2. Policy Group: allow agent, chặn số tiền lớn
                                              │ 3. Outbound auth: gắn X-Api-Key (lấy từ AgentBase Identity)
                                              ▼
                                   MCP server (Runtime "voice-banking-mcp") ──▶ vDB PostgreSQL
```

Agent không giữ `MCP_API_KEY`. Gateway lấy key từ Identity khi gọi tới MCP server, và mọi lời gọi tool đều phải qua Policy.

## 0. Chuẩn bị

```bash
export GREENNODE_CLIENT_ID="..." GREENNODE_CLIENT_SECRET="..."      # IAM service account, KHÔNG commit
SK=../greennode-agentbase-skills/skills/agentbase/scripts              # hoặc .claude/skills/agentbase/scripts nếu đã cài plugin
bash $SK/check_credentials.sh iam
TOKEN=$(bash $SK/get_token.sh)
```

Đã có từ các bước trước:
- MCP server chạy trên Runtime và `/health` trả `db: ok`. Xem README mục "Deploy lên GreenNode".
- **File env của runtime MCP server có `VB_CUSTOMER_ID=KH0001`.** Gateway có thể không chuyển tiếp header `X-Customer-Id`. Biến này gắn cố định server với khách duy nhất của app, và server sẽ từ chối mọi `X-Customer-Id` khác.

Ghi lại URL endpoint DEFAULT của runtime MCP server:

```bash
bash $SK/runtime.sh endpoints list <MCP_RUNTIME_ID>      # lấy "url", vd https://xxxx.agentbase...
MCP_URL=<url ở trên>
```

## 1. Lưu API key của MCP server vào AgentBase Identity

Không dán key vào chat hay commit vào repo. Đưa key qua biến môi trường:

```bash
export VB_MCP_KEY='<đúng giá trị MCP_API_KEY trong env của runtime MCP>'
bash $SK/auth.sh apikey create --name voice-banking-mcp-key --apikey-env VB_MCP_KEY
bash $SK/auth.sh apikey get --name voice-banking-mcp-key      # xác nhận đã có provider
```

## 2. Tạo Policy Group và các policy

```bash
PBASE=https://agentbase.api.vngcloud.vn/policy/api/v1
curl -s -X POST "$PBASE/policy-groups" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"voice-banking-gw","description":"Policies cho gateway voice-banking"}'
GROUP_ID=<id trong response>
```

Ba policy nằm trong `deploy/policies/`:

| File | Tác dụng |
|---|---|
| `01-allow-agent.json` | **allow** mọi tool cho principal của agent. Policy mặc định từ chối nếu không có rule allow nào khớp, nên bắt buộc phải có rule này |
| `02-deny-large-transfer.json` | **deny** `bank__open_transfer_screen` khi `amount > 100.000.000` |
| `03-deny-large-loan.json` | **deny** `bank__open_loan_screen` khi `amount > 500.000.000` |

Trong file 01, thay `<PRINCIPAL>` bằng:
- `iam:<id service account của runtime agent>`: chặt nhất, chỉ đúng agent đó được gọi.
- hoặc `iam:*`: mọi IAM caller trong tenant. Dùng tạm khi chưa biết id.

```bash
for f in deploy/policies/*.json; do
  curl -s -X POST "$PBASE/policy-groups/$GROUP_ID/policies" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" -d @"$f"; echo
done
```

Các rule deny chỉ đọc trường `amount`. Ba tool `open_*_screen` luôn có trường này, vì `amount` là bắt buộc. Đừng viết điều kiện dựa trên trường tùy chọn như `risk_acknowledged`: request thiếu trường đó sẽ bị **deny** (TYPE_MISMATCH).

## 3. Tạo Gateway

```bash
GBASE=https://agentbase.api.vngcloud.vn/gateway/api/v1
curl -sS "$GBASE/flavors?resourceType=GATEWAY" -H "Authorization: Bearer $TOKEN" \
  | jq '.items[] | select(.availability=="YES") | {id, cpu, memoryGi}'
FLAVOR_ID=<chọn 1 id>

sed -e "s#<FLAVOR_ID>#$FLAVOR_ID#" -e "s#<POLICY_GROUP_ID>#$GROUP_ID#" -e "s#<MCP_RUNTIME_ENDPOINT>#$MCP_URL#" \
  deploy/gateway.json > /tmp/gateway.json
curl -sS -i -X POST "$GBASE/gateways" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @/tmp/gateway.json

until [ "$(curl -sS "$GBASE/gateways/voice-banking-gw" -H "Authorization: Bearer $TOKEN" | jq -r .state)" = "ACTIVE" ]; do sleep 5; done
curl -sS "$GBASE/gateways/voice-banking-gw" -H "Authorization: Bearer $TOKEN" | jq '{state, endpoint, lastError}'
GW_URL=<endpoint ở trên>
```

Các trường `name`, `networkMode`, `flavorId`, `replicas` **không sửa được** sau khi tạo; muốn đổi thì phải xóa và tạo lại. Còn `targets`, `inboundAuth`, `policyGroupId` sửa được bằng PATCH kèm header `If-Match`.

## 4. Kiểm tra qua Gateway

Slide training ghi agent gọi `POST {GW_URL}/<connector>`, nên URL MCP thường là `$GW_URL/bank`. Hãy thử `tools/list` để xác nhận:

```bash
H=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
for U in "$GW_URL/bank" "$GW_URL" "$GW_URL/mcp"; do echo "== $U"; curl -s "${H[@]}" -d "$INIT" "$U" | head -c 200; echo; done
```

Dùng URL trả về `serverInfo` để chạy 3 ca kiểm tra:

```bash
MCP=<URL đúng ở trên>
call() { curl -s "${H[@]}" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" "$MCP"; echo; }
call get_account_balances '{}'                         # mong đợi: có speech "Thưa anh Hưng..."
call open_transfer_screen '{"amount":2000000}'         # mong đợi: ui_action navigate
call open_transfer_screen '{"amount":150000000}'       # mong đợi: BỊ POLICY CHẶN (deny > 100 triệu)
```

Nếu ca đầu báo "Phiên chưa gắn khách hàng hợp lệ", runtime MCP **chưa có `VB_CUSTOMER_ID`**. Thêm biến này vào file env rồi `runtime.sh update`.

## 5. Agent kết nối Gateway

Trên Runtime, agent đã được nền tảng gắn sẵn `GREENNODE_CLIENT_ID` và `GREENNODE_CLIENT_SECRET`. Agent dùng hai biến này để lấy IAM token. Token có hạn, nên lấy lại mỗi lần chạy agent hoặc khi gặp lỗi 401.

```python
import os, httpx
from langchain_mcp_adapters.client import MultiServerMCPClient

def iam_token() -> str:
    r = httpx.post("https://iam.api.vngcloud.vn/accounts-api/v2/auth/token",
                   auth=(os.environ["GREENNODE_CLIENT_ID"], os.environ["GREENNODE_CLIENT_SECRET"]),
                   data={"grant_type": "client_credentials"}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

async def build_tools(customer_id: str, session_id: str):
    client = MultiServerMCPClient({"bank": {
        "transport": "streamable_http",
        "url": os.environ["BANK_MCP_GATEWAY_URL"],          # URL đúng ở bước 4
        "headers": {
            "Authorization": f"Bearer {iam_token()}",       # xác thực với Gateway (inbound IAM)
            "X-Customer-Id": customer_id,                   # nếu Gateway chuyển tiếp thì server đối chiếu với VB_CUSTOMER_ID
            "X-Session-Id": session_id,
        },
    }})
    return await client.get_tools()
```

Agent **không** cần `MCP_API_KEY` nữa, vì Gateway gắn key khi gọi tới MCP server. Nếu Policy chặn một lời gọi, tool trả lỗi. Agent nên nói với khách: "Số tiền này lớn, anh vui lòng thao tác trực tiếp trên app hoặc ra quầy."

## Ghi chú bảo mật (để trình bày)

- **Ba lớp chặn số tiền lớn:**
  - Policy Gateway: 100 triệu.
  - Server: không điền sẵn trên `MAX_PREFILL_TRANSFER` (500 triệu).
  - Rủi ro cao thì không mở màn hình nếu khách chưa xác nhận lại.
- **Agent chỉ giữ IAM token có hạn.** API key của MCP server nằm trong AgentBase Identity.
- **Runtime MCP vẫn có endpoint public**, nhưng mọi tool đều cần `X-Api-Key`.
- **Một bản deploy chỉ phục vụ một khách** (`VB_CUSTOMER_ID`). Khi lên production, danh tính khách phải lấy từ token đăng nhập của app (ví dụ inbound JWT của Gateway, dùng claim `sub`), không gắn cố định bằng biến môi trường.
