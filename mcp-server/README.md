# Voice Banking MCP: dữ liệu và tool cho trợ lý giọng nói ngân hàng

Phần **database + tool + MCP server** của bài dự thi Smart Banking 2026 AI Hackathon (Track A: Trải nghiệm khách hàng).
Đây là trợ lý giọng nói giúp **người lớn tuổi, người mắt kém** dùng app ngân hàng:
- Hỏi số dư và thống kê chi tiêu bằng giọng nói.
- Nói để mở màn hình **chuyển tiền / gửi tiết kiệm / vay** với số tiền đã điền sẵn.

> **Toàn bộ dữ liệu là MOCK / tổng hợp.** Không có dữ liệu khách hàng thật. Lãi suất và sản phẩm là giả lập.

## Điểm thiết kế chính

| Nguyên tắc | Cách làm |
|---|---|
| **Agent không thực hiện giao dịch** | `open_*_screen` chỉ tạo bản ghi `pending_actions` (mở màn hình + điền sẵn). Khách tự nhập phần còn lại và tự xác nhận OTP. Test `test_transfer_never_executes_*` kiểm chứng điều này. |
| **LLM không tự tính số** | Mọi con số do SQL tính. Mỗi kết quả có `speech` đã đọc số thành chữ ("một triệu năm trăm nghìn đồng") để TTS đọc đúng. |
| **Số tiền nói ra được hiểu bằng luật, không đoán** | `parse_vnd_amount` hiểu "một triệu rưỡi", "hai củ", "500k", "1tr2", "hai trăm năm nghìn". Luôn đọc lại để khách xác nhận. Eval 77/77 ca (có ca tên người trùng chữ số: "anh Nam hai triệu"), cộng 3.000 ca kiểm tra vòng chữ ↔ số. |
| **Chống lừa đảo** | Trước khi mở màn hình chuyển tiền, server kiểm tra: số dư, số tiền lớn bất thường, người nhận lạ, giờ khuya, nội dung kiểu "xác minh tài khoản", "công an". Rủi ro cao thì **không mở màn hình**, bắt agent hỏi lại khách. |
| **Không lộ dữ liệu người khác** | `customer_id` lấy từ phiên (header do backend gắn), không phải tham số của tool. |
| **Che dữ liệu nhạy cảm với LLM** | LLM chỉ thấy 4 số cuối tài khoản. Số đầy đủ đi qua REST tới giao diện. |
| **Audit** | Mọi lần gọi tool ghi `vb.tool_audit_log` (khách, phiên, model, tham số, kết quả, độ trễ, lỗi). |

## Cấu trúc

```
app/
  vn_money.py     số ↔ chữ tiếng Việt, hiểu số tiền trong câu nói
  tools.py        20 tool nghiệp vụ (SQL), audit, kiểm tra rủi ro, pending_actions
  server.py       MCP server (streamable HTTP /mcp) + REST /api/* + /health
db/
  schema.sql          schema Postgres "vb" (8 bảng + 1 view)
  generate_seed.py    sinh dữ liệu mock (seed cố định, chạy lại ra y hệt)
  seed.sql            dữ liệu đã sinh: 1 khách, 1 tài khoản thanh toán, 1.859 giao dịch
  load_db.py          nạp schema + seed (không cần psql)
evals/
  amount_cases.jsonl        67 câu nói số tiền + đáp án
  run_amount_eval.py        chấm bộ hiểu số tiền
  run_anomaly_eval.py       chấm bộ phát hiện giao dịch bất thường
  agent_intent_cases.jsonl  30 câu nói → tool mong đợi (cho người làm agent)
tests/                pytest (108 test)
scripts/smoke_test.py gọi MCP server thật qua HTTP như agent
Dockerfile            image chạy trên AgentBase Runtime (cổng 8080, /health)
CONTRACT.md           hợp đồng tích hợp cho người làm agent và giao diện
```

## Chạy local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest

# Postgres local (hoặc vDB GreenNode)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
python db/load_db.py                     # tạo schema vb + nạp dữ liệu (XÓA schema vb cũ)

export MCP_API_KEY=dev-key DEMO_NOW=2026-10-21T09:30
python -m app.server                     # http://localhost:8080/mcp , /health

# kiểm tra
python scripts/smoke_test.py --url http://localhost:8080 --key dev-key --customer KH0001
pytest -q
python -m evals.run_amount_eval
python -m evals.run_anomaly_eval

# MCP Inspector (stdio)
VB_CUSTOMER_ID=KH0001 npx @modelcontextprotocol/inspector -e DATABASE_URL=$DATABASE_URL -e VB_CUSTOMER_ID=KH0001 python -m app.server --stdio
```

## Deploy lên GreenNode

### 1. Database: vDB PostgreSQL
1. Tạo PostgreSQL trên vDB (dùng Cloud Credit). Ghi lại host, port, user, password, db.
2. Mở quyền kết nối từ máy mình để nạp dữ liệu, rồi chạy:
   ```bash
   export DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB?sslmode=require"
   python db/load_db.py && python db/load_db.py --check
   ```
3. MCP server trên AgentBase phải kết nối được tới vDB:
   - **vDB có IP public:** runtime ở chế độ PUBLIC dùng được ngay.
   - **vDB chỉ có IP private:** tạo runtime ở **VPC mode**, cùng VPC/subnet với vDB (xem skill `/agentbase-deploy`).

### 2. Build và đẩy image lên Container Registry (vCR)
```bash
# Mac chip M: bắt buộc --platform linux/amd64
docker build --platform linux/amd64 -t vcr.vngcloud.vn/<repo>/voice-banking-mcp:v1 .
docker login vcr.vngcloud.vn          # hoặc: bash .claude/skills/agentbase/scripts/docker_login.sh
docker push vcr.vngcloud.vn/<repo>/voice-banking-mcp:v1
```

### 3. Tạo runtime trên AgentBase (Custom Agent)
Dùng console **Agent Runtime → Create**, hoặc skill `/agentbase-deploy` trong Claude Code/Codex.
- Image: `vcr.vngcloud.vn/<repo>/voice-banking-mcp:v1`, flavor gợi ý `1x1-general`.
- Cổng 8080, health check `GET /health` (image đã đáp ứng hợp đồng Runtime).
- Biến môi trường (xem `.env.example`):

  | Biến | Bắt buộc | Ghi chú |
  |---|---|---|
  | `DATABASE_URL` | ✔ | chuỗi kết nối vDB |
  | `MCP_API_KEY` | ✔ | sinh bằng `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
  | `DEMO_NOW` | nên có | ví dụ `2026-10-22T09:00`, giữ số liệu cố định khi giám khảo thử |
  | `CORS_ORIGINS` | nếu giao diện gọi REST từ trình duyệt | domain của giao diện |

### 4. Kiểm tra sau deploy
```bash
curl https://<runtime-endpoint>/health
python scripts/smoke_test.py --url https://<runtime-endpoint> --key $MCP_API_KEY --customer KH0001
```
Nếu endpoint runtime đòi IAM token (401 khi chưa có `Authorization`), có hai cách:
- Gọi qua **MCP Gateway**, xem bước 5.
- Agent gắn IAM bearer vào header `Authorization`. Server này đọc key ở `X-Api-Key` nên không xung đột.

### 5. Nên có: MCP Gateway + Policy Group (điểm cộng phần bảo mật)
Hướng dẫn chạy từng bước và file cấu hình sẵn: [deploy/GATEWAY.md](deploy/GATEWAY.md) (`deploy/gateway.json`, `deploy/policies/*.json`). Khi đi qua Gateway, đặt `VB_CUSTOMER_ID=KH0001` trong env của runtime MCP.

- Tạo **MCP Gateway** (skill `/agentbase-gateway`), target = `https://<runtime-endpoint>/mcp`.
- Outbound auth `APIKEY` với `headerName: X-Api-Key`, giá trị lưu trong AgentBase Identity.
- Gắn **Policy Group** (skill `/agentbase-policy`) để giới hạn agent chỉ gọi các tool cần thiết. Có thể thêm điều kiện trên tham số, ví dụ chặn `bank__open_transfer_screen` khi `context.input.amount > 100000000`.
- Agent chỉ biết URL gateway, không giữ key của MCP server.

## Dữ liệu mock

Sinh bởi `db/generate_seed.py`, dùng seed cố định. Giai đoạn **01/05/2025 → 25/10/2026**. Tool tự ẩn giao dịch sau "hôm nay"; muốn đổi ngày thì chạy `python db/generate_seed.py --end 2026-10-31`.

**KH0001: anh Trần Quốc Hưng, 51 tuổi**, trưởng phòng kỹ thuật ở Hà Nội. Bị lão thị, ngại thao tác app. Có **1.859 giao dịch / 18 tháng** (~103 giao dịch/tháng), tất cả nằm trên **một tài khoản thanh toán VietinBank**, gồm:
- **Thu:** lương (tăng lương 01/2026), thưởng Tết/KPI/lễ, tiền cho thuê ki-ốt (đổi người thuê 07/2026, có trả cọc và nhận cọc), lãi tiết kiệm, hoàn thuế TNCN, bán xe máy cũ, em trai trả nợ.
- **Chi cố định:** gửi vợ, gửi con sinh hoạt phí, gửi mẹ ở quê, phí chung cư và gửi xe, trả góp ô tô (auto-debit), học thêm của con gái, điện (theo mùa), nước, internet, điện thoại, nạp VETC, gas.
- **Chi phát sinh:**
  - Học phí đại học và THPT, bảo hiểm nhân thọ và bảo hiểm xe.
  - Bảo dưỡng xe, đăng kiểm, phạt nguội, thuế đất.
  - Khám sức khỏe, nha khoa, cắt kính.
  - Điều hòa, điện thoại cho con, quà sinh nhật vợ.
  - Du lịch Sầm Sơn và Đà Nẵng, Tết Bính Ngọ (rút tiền lì xì, biếu mẹ, mua sắm).
  - Mừng cưới, phúng viếng, từ thiện, sửa nhà, cho em trai mượn tiền.
- **Hằng ngày:** ăn sáng, ăn trưa, cà phê, chợ, siêu thị, cửa hàng tiện lợi, hoa quả, quán ăn, xăng, gửi xe, Grab/Be, rút ATM, Shopee/Lazada, cắt tóc, nhà sách, xem phim, Netflix, Google One.
- **Chuyển khoản nhỏ:** tiền tiêu vặt cho con gái, đưa thêm vợ, gửi thêm con trai, nạp điện thoại cho mẹ, góp tiền / được trả lại tiền liên hoan với đồng nghiệp.
- **Tài khoản:** đúng 1 tài khoản thanh toán `TK000101`. Mọi giao dịch (chuyển khoản, QR, quẹt thẻ ghi nợ, hóa đơn, ATM) đều nằm trên tài khoản này. Bên trong tài khoản (`parent_account_id = TK000101`, không có giao dịch riêng): 2 sổ tiết kiệm đang gửi (sổ 180 triệu **đến hạn 28/10/2026**, sổ 50 triệu), 2 sổ đã tất toán, khoản vay ô tô trả góp bằng trích nợ tự động ngày 15. Gửi/tất toán sổ, nhận lãi, trả góp đều hiện là giao dịch trên tài khoản thanh toán. Không có thẻ tín dụng.
- **7 giao dịch bất thường cài sẵn** (cột `is_anomaly_seed`, chỉ script eval đọc):
  - Bị lừa chuyển 45 triệu lúc 22:47, rồi thêm 30 triệu sáng hôm sau, giả danh cơ quan điều tra.
  - "Đầu tư ứng dụng" 15 triệu.
  - Rút ATM 20 triệu.
  - Quẹt thẻ quốc tế lúc 3 giờ sáng.
  - Tiền điện bị trừ trùng.
  - Tiền điện tháng 10 tăng vọt.

Dữ liệu chỉ có một khách hàng (KH0001) để demo cho một cá nhân.

## Kết quả eval (chạy trên dữ liệu mock)

| Bộ | Kết quả |
|---|---|
| Hiểu số tiền nói (`evals/amount_cases.jsonl`) | **77/77** đúng; 3.000/3.000 ca kiểm tra vòng chữ ↔ số |
| Phát hiện giao dịch bất thường (01/11/2025 → 25/10/2026, 1.246 giao dịch) | **TP 7, FP 1, FN 0**: precision 87,5%, recall 100%. Ca báo nhầm là 25 triệu trả thợ sửa nhà mới, cài sẵn làm ca khó. |
| Test tự động | 108 test pass |

**Giới hạn cần nói rõ:**
- Dữ liệu và luật do cùng một nhóm viết, nên các con số trên **chưa chứng minh độ chính xác trên dữ liệu thật**.
- Bộ hiểu số tiền mới được kiểm trên văn bản. Cần thử thêm với đầu ra STT thật, có giọng vùng miền và người lớn tuổi.

## Khai báo xuất xứ (theo thể lệ)

- **Code:** viết trong thời gian cuộc thi, có sử dụng trợ lý lập trình AI (Claude). Ý tưởng schema và tool kế thừa và viết lại từ bản nháp "Trợ lý tài chính cá nhân" của nhóm (thư mục `db/` cũ).
- **Thư viện mã nguồn mở:**

  | Thư viện | Giấy phép |
  |---|---|
  | `mcp` (Model Context Protocol Python SDK) | MIT |
  | `psycopg`, `psycopg-pool` | LGPL-3.0 |
  | `uvicorn` | BSD-3 |
  | `starlette` | BSD-3 |
  | `pydantic` | MIT |
  | `tzdata` | Apache-2.0 |
- **Dữ liệu:** 100% tổng hợp bởi `db/generate_seed.py`. Tên người, số tài khoản, công ty, trường học đều hư cấu; tên ngân hàng, chuỗi cửa hàng chỉ để sao kê giống thật. Lãi suất là MOCK.
- **Không có** khóa, mật khẩu hay credential trong repo. Cấu hình qua biến môi trường (`.env.example`).
