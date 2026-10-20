"""
MCP server + REST API cho Voice Banking Assistant.

Chạy:
    # HTTP (deploy AgentBase Runtime / vServer): MCP ở /mcp, health ở /health, REST ở /api/*
    python -m app.server                      # đọc HOST (0.0.0.0), PORT (8080)

    # stdio (dev, MCP Inspector, Claude Desktop): 1 tiến trình = 1 khách hàng
    VB_CUSTOMER_ID=KH0001 python -m app.server --stdio

Xác thực (HTTP):
    X-Api-Key: <MCP_API_KEY>      (hoặc Authorization: Bearer <MCP_API_KEY>)
    X-Customer-Id: KH0001         khách đã đăng nhập, do BACKEND agent gắn, KHÔNG lấy từ LLM
    X-Session-Id, X-Model-Name    tùy chọn, ghi vào audit log
Ghi chú: dùng X-Api-Key thay vì Authorization khi đi qua AgentBase (header Authorization có thể
được nền tảng dùng cho IAM token).
"""
from __future__ import annotations

import argparse
import hmac
import logging
import os
import re
from typing import Annotated, Literal

import anyio.to_thread
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import tools as T

log = logging.getLogger("voice-banking-mcp")

API_KEY = os.getenv("MCP_API_KEY", "")
UI_API_KEY = os.getenv("UI_API_KEY", "") or API_KEY
ALLOW_NO_AUTH = os.getenv("ALLOW_NO_AUTH", "false").lower() == "true"
CUSTOMER_RE = re.compile(r"^KH\d{4}$")
# Gắn cố định server với 1 khách (app chỉ phục vụ tài khoản này). Bắt buộc với stdio; với HTTP thì dùng khi
# header X-Customer-Id không tới được server (vd đi qua MCP Gateway).
BOUND_CUSTOMER = os.getenv("VB_CUSTOMER_ID", "")
VERSION = "1.0.0"

INSTRUCTIONS = """Bạn là trợ lý giọng nói của ngân hàng, giúp người lớn tuổi và người mắt kém dùng app. Trả lời bằng tiếng Việt.
QUY TẮC
- Câu ngắn, rõ, mỗi lượt tối đa 2-3 câu. Xưng "em", gọi khách theo `salutation` (vd "anh Hưng").
- KHÔNG tự tính hay ước lượng số liệu. Mọi con số lấy từ tool. Khi tool có trường `speech`, đọc lại gần như nguyên văn.
- Khách đã đăng nhập theo phiên; không hỏi mã khách hàng, không xem được dữ liệu người khác.
- Không biết hôm nay là ngày nào thì gọi get_current_date trước khi tính khoảng ngày ("tháng này", "tuần trước").
CHUYỂN TIỀN / GỬI TIẾT KIỆM / VAY
- Em KHÔNG thực hiện giao dịch. Em chỉ mở đúng màn hình và điền sẵn số tiền; khách tự nhập phần còn lại và tự xác nhận OTP.
- Số tiền khách nói phải đưa qua parse_vnd_amount, đọc lại `words` cho khách và chờ khách nói "đúng" rồi mới mở màn hình.
- Khách nhắc tên người nhận ("con trai", "mẹ") thì gọi find_beneficiary; có đúng 1 kết quả mới truyền beneficiary_id.
- Nếu open_transfer_screen trả về blocked=true: đọc cảnh báo, hỏi khách có ai đang hướng dẫn qua điện thoại không.
  Chỉ gọi lại với risk_acknowledged=true khi khách nói rõ vẫn muốn tiếp tục.
- Không bao giờ nói "đã chuyển tiền thành công". Kết quả luôn là "đã mở màn hình, điền sẵn".
- Khách đổi ý thì gọi cancel_pending_action.
AN TOÀN
- Không đọc số tài khoản đầy đủ, chỉ 4 số cuối.
- Nếu khách nhắc tới công an, tòa án, "xác minh tài khoản", đầu tư lãi cao: nhắc khách đây có thể là lừa đảo."""

mcp = MCPServer("voice-banking", title="Trợ lý giọng nói ngân hàng", instructions=INSTRUCTIONS, version=VERSION)

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
PREPARE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

Date = Annotated[str, Field(description="Ngày dạng YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$")]
Amount = Annotated[int, Field(description="Số tiền VND (số nguyên), lấy từ parse_vnd_amount", ge=1000)]
Category = Annotated[str, Field(description="Danh mục: mã (electricity, groceries...) hoặc cách nói tiếng Việt "
                                            "('tiền điện', 'đi chợ', 'học phí')")]


# ================================================================= phiên & gọi tool
def _session(ctx: Context) -> tuple[str, dict]:
    h = ctx.headers
    if h is None:                                           # stdio
        cid = BOUND_CUSTOMER
        audit = {"session_id": "stdio"}
    else:
        _check_key(h, API_KEY)
        cid = _bound_customer(h.get("x-customer-id", ""))
        audit = {k: v for k, v in (("session_id", h.get("x-session-id") or h.get("mcp-session-id")),
                                   ("model_name", h.get("x-model-name"))) if v}
    if not CUSTOMER_RE.match(cid or ""):
        raise ToolError("Phiên chưa gắn khách hàng hợp lệ (header X-Customer-Id hoặc VB_CUSTOMER_ID)")
    return cid, audit


def _bound_customer(header_cid: str) -> str:
    """Khách của request. Nếu server được gắn cố định 1 khách (VB_CUSTOMER_ID, vd khi đứng sau MCP Gateway
    không chuyển tiếp header tùy chỉnh) thì dùng khách đó, và từ chối mọi X-Customer-Id khác."""
    if not BOUND_CUSTOMER:
        return header_cid
    if header_cid and header_cid != BOUND_CUSTOMER:
        raise ToolError("Phiên không được phép truy cập khách hàng này")
    return BOUND_CUSTOMER


def _check_key(h, key: str):
    if not key:
        if ALLOW_NO_AUTH:
            return
        raise ToolError("Server chưa cấu hình MCP_API_KEY")
    got = h.get("x-api-key") or (h.get("authorization", "")[7:] if h.get("authorization", "").lower()
                                 .startswith("bearer ") else "")
    if not hmac.compare_digest(got or "", key):
        raise ToolError("Không có quyền truy cập")


async def _run(_tool: str, ctx: Context | None, with_customer: bool = True, **args) -> dict:
    audit: dict = {}
    if with_customer:
        cid, audit = _session(ctx)
        args = {"customer_id": cid, **args}
    elif ctx is not None and ctx.headers is not None:
        _check_key(ctx.headers, API_KEY)
    args = {k: v for k, v in args.items() if v is not None}

    def call():
        T.AUDIT_CTX.set(audit)
        return T.call_tool(_tool, args)

    result = await anyio.to_thread.run_sync(call)
    if isinstance(result, dict) and "error" in result:
        raise ToolError(result["error"])
    return result


# ================================================================= TIỆN ÍCH
@mcp.tool(annotations=READ)
async def get_current_date(ctx: Context) -> dict:
    """Ngày hôm nay và các mốc (đầu tuần, tháng này, tháng trước). Gọi trước khi tính khoảng ngày."""
    return await _run("get_current_date", ctx, with_customer=False)


@mcp.tool(annotations=READ)
async def parse_vnd_amount(ctx: Context, text: Annotated[str, Field(description="Nguyên văn câu khách nói")]) -> dict:
    """Hiểu số tiền trong câu nói tiếng Việt ('một triệu rưỡi', '500k', 'hai củ', '1tr2') -> số VND chính xác
    và câu đọc lại để khách xác nhận. LUÔN dùng tool này thay vì tự đổi chữ ra số."""
    return await _run("parse_vnd_amount", ctx, with_customer=False, text=text)


# ================================================================= HỒ SƠ, SỐ DƯ
@mcp.tool(annotations=READ)
async def get_customer_profile(ctx: Context) -> dict:
    """Tên, cách xưng hô, tuổi, nhu cầu hỗ trợ (vd mắt kém) của khách đang đăng nhập."""
    return await _run("get_customer_profile", ctx)


@mcp.tool(annotations=READ)
async def get_account_balances(ctx: Context) -> dict:
    """Số dư tài khoản thanh toán, các sổ tiết kiệm mở từ tài khoản (ngày đến hạn), khoản vay (kỳ trả tiếp theo)."""
    return await _run("get_account_balances", ctx)


# ================================================================= GIAO DỊCH, THỐNG KÊ
@mcp.tool(annotations=READ)
async def get_recent_transactions(
    ctx: Context, limit: Annotated[int, Field(ge=1, le=20)] = 5,
    direction: Annotated[Literal["in", "out"] | None, Field(description="in = tiền vào, out = tiền ra")] = None,
) -> dict:
    """Mấy giao dịch gần nhất ('dạo này tôi tiêu gì', 'vừa rồi có ai chuyển tiền cho tôi không')."""
    return await _run("get_recent_transactions", ctx, limit=limit, direction=direction)


@mcp.tool(annotations=READ)
async def search_transactions(
    ctx: Context, date_from: Date, date_to: Date, category: Category | None = None,
    keyword: Annotated[str | None, Field(description="Từ khóa trong nội dung/người nhận, vd 'hoc phi', 'shopee'")] = None,
    direction: Literal["in", "out"] | None = None,
    min_amount: Annotated[int | None, Field(ge=0)] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> dict:
    """Tìm giao dịch cụ thể + tổng tiền khớp điều kiện ('tháng này tôi trả tiền điện bao nhiêu', 'đóng học phí khi nào')."""
    return await _run("search_transactions", ctx, date_from=date_from, date_to=date_to, category=category,
                      keyword=keyword, direction=direction, min_amount=min_amount, limit=limit)


@mcp.tool(annotations=READ)
async def get_month_overview(
    ctx: Context,
    month: Annotated[str | None, Field(description="Tháng dạng YYYY-MM; bỏ trống = tháng này",
                                       pattern=r"^\d{4}-\d{2}$")] = None,
) -> dict:
    """Tổng quan 1 tháng: thu, chi, còn dư, 3 khoản chi lớn nhất, so với tháng trước. Dùng cho câu hỏi chung
    'tháng này tôi tiêu thế nào'."""
    return await _run("get_month_overview", ctx, month=month)


@mcp.tool(annotations=READ)
async def get_spending_summary(
    ctx: Context, date_from: Date, date_to: Date,
    group_by: Literal["category", "month", "merchant", "group"] = "category",
    top: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict:
    """Tổng chi tiêu trong khoảng ngày, chia theo danh mục/tháng/nơi chi/nhóm (không tính gửi tiết kiệm, đầu tư, cho mượn)."""
    return await _run("get_spending_summary", ctx, date_from=date_from, date_to=date_to, group_by=group_by, top=top)


@mcp.tool(annotations=READ)
async def get_income_summary(ctx: Context, date_from: Date, date_to: Date) -> dict:
    """Tổng tiền nhận được (lương, thưởng, cho thuê, lãi...) trong khoảng ngày."""
    return await _run("get_income_summary", ctx, date_from=date_from, date_to=date_to)


@mcp.tool(annotations=READ)
async def compare_periods(ctx: Context, a_from: Date, a_to: Date, b_from: Date, b_to: Date,
                          category: Category | None = None) -> dict:
    """So sánh chi tiêu kỳ A (cũ) với kỳ B (mới), toàn bộ hoặc một danh mục."""
    return await _run("compare_periods", ctx, a_from=a_from, a_to=a_to, b_from=b_from, b_to=b_to, category=category)


@mcp.tool(annotations=READ)
async def get_category_trend(ctx: Context, category: Category,
                             months: Annotated[int, Field(ge=2, le=18)] = 6) -> dict:
    """Một khoản theo từng tháng ('tiền điện mấy tháng nay thế nào'), kèm trung bình và so sánh tháng này."""
    return await _run("get_category_trend", ctx, category=category, months=months)


@mcp.tool(annotations=READ)
async def detect_unusual_transactions(ctx: Context, date_from: Date | None = None, date_to: Date | None = None) -> dict:
    """Rà soát giao dịch bất thường (mặc định 30 ngày gần nhất): người nhận lạ số tiền lớn, giờ khuya, chuyển liên tiếp,
    bị trừ trùng, hóa đơn tăng vọt, nội dung giống lừa đảo. Mỗi giao dịch kèm lý do."""
    return await _run("detect_unusual_transactions", ctx, date_from=date_from, date_to=date_to)


# ================================================================= NGƯỜI NHẬN, SẢN PHẨM
@mcp.tool(annotations=READ)
async def find_beneficiary(ctx: Context, name: Annotated[str, Field(description="Tên/cách gọi: 'con trai', 'mẹ', 'cô Hoa'")]) -> dict:
    """Tìm người nhận trong danh bạ đã lưu của khách theo tên hoặc cách gọi thân mật."""
    return await _run("find_beneficiary", ctx, name=name)


@mcp.tool(annotations=READ)
async def list_beneficiaries(ctx: Context) -> dict:
    """Danh bạ người nhận đã lưu (số tài khoản đã che)."""
    return await _run("list_beneficiaries", ctx)


@mcp.tool(annotations=READ)
async def search_products(ctx: Context, product_type: Literal["savings", "loan"] | None = None,
                          term_months: Annotated[int | None, Field(ge=1, le=36)] = None) -> dict:
    """Sản phẩm tiết kiệm/vay và lãi suất tham khảo (dữ liệu MOCK)."""
    return await _run("search_products", ctx, with_customer=False, product_type=product_type, term_months=term_months)


@mcp.tool(annotations=READ)
async def check_transfer_risk(ctx: Context, amount: Amount, beneficiary_id: int | None = None,
                              note: str | None = None) -> dict:
    """Kiểm tra rủi ro trước khi chuyển: thiếu số dư, số tiền lớn bất thường, người nhận lạ, giờ khuya, nội dung lừa đảo."""
    return await _run("check_transfer_risk", ctx, amount=amount, beneficiary_id=beneficiary_id, note=note)


# ================================================================= MỞ MÀN HÌNH + ĐIỀN SẴN (không thực hiện giao dịch)
@mcp.tool(annotations=PREPARE)
async def open_transfer_screen(
    ctx: Context, amount: Amount,
    beneficiary_id: Annotated[int | None, Field(description="Chỉ truyền khi find_beneficiary trả đúng 1 người")] = None,
    note: Annotated[str | None, Field(description="Nội dung chuyển khoản nếu khách đã nói", max_length=140)] = None,
    risk_acknowledged: Annotated[bool, Field(description="true chỉ khi khách đã nghe cảnh báo rủi ro cao và nói rõ vẫn "
                                                         "muốn tiếp tục")] = False,
) -> dict:
    """Mở màn hình CHUYỂN TIỀN trên app và điền sẵn số tiền (và người nhận nếu có). KHÔNG chuyển tiền: khách tự nhập
    phần còn lại và tự xác nhận OTP. Gọi sau khi khách đã xác nhận số tiền đọc lại."""
    return await _run("open_transfer_screen", ctx, amount=amount, beneficiary_id=beneficiary_id, note=note,
                      risk_acknowledged=risk_acknowledged)


@mcp.tool(annotations=PREPARE)
async def open_savings_screen(ctx: Context, amount: Amount,
                              term_months: Annotated[int | None, Field(description="Kỳ hạn nếu khách đã nói: 1,3,6,9,12,24")] = None) -> dict:
    """Mở màn hình GỬI TIẾT KIỆM ONLINE và điền sẵn số tiền (và kỳ hạn). KHÔNG tự mở sổ."""
    return await _run("open_savings_screen", ctx, amount=amount, term_months=term_months)


@mcp.tool(annotations=PREPARE)
async def open_loan_screen(
    ctx: Context, amount: Amount,
    loan_type: Annotated[str | None, Field(description="Chỉ truyền khi khách đã nói rõ loại vay: VAY_TIEU_DUNG / "
                                                       "VAY_CAM_CO_STK / VAY_MUA_OTO / VAY_MUA_NHA hoặc cách nói ('cầm cố "
                                                       "sổ tiết kiệm', 'mua nhà'). Bỏ trống thì khách tự chọn trên màn hình")] = None,
    term_months: Annotated[int | None, Field(ge=1, le=300)] = None,
) -> dict:
    """Mở màn hình ĐĂNG KÝ VAY và điền sẵn số tiền (loại vay, thời hạn nếu có). Chỉ là đăng ký, ngân hàng còn thẩm định."""
    return await _run("open_loan_screen", ctx, amount=amount, loan_type=loan_type, term_months=term_months)


@mcp.tool(annotations=PREPARE)
async def cancel_pending_action(ctx: Context, action_id: str) -> dict:
    """Hủy màn hình đã chuẩn bị khi khách đổi ý ('thôi, không chuyển nữa')."""
    return await _run("cancel_pending_action", ctx, action_id=action_id)


# ================================================================= RESOURCES
@mcp.resource("vb://categories", title="Danh mục giao dịch", mime_type="application/json")
async def categories() -> str:
    import json
    r = await anyio.to_thread.run_sync(lambda: T.TOOLS["list_categories"].__wrapped__())
    return json.dumps(r, ensure_ascii=False)


# ================================================================= REST cho giao diện app + health
def _ui_auth(request: Request) -> str:
    h = request.headers
    if not UI_API_KEY and not ALLOW_NO_AUTH:
        raise PermissionError("Server chưa cấu hình UI_API_KEY/MCP_API_KEY")
    if UI_API_KEY:
        got = h.get("x-api-key") or (h.get("authorization", "")[7:] if h.get("authorization", "").lower()
                                     .startswith("bearer ") else "")
        if not hmac.compare_digest(got or "", UI_API_KEY):
            raise PermissionError("Không có quyền truy cập")
    try:
        cid = _bound_customer(h.get("x-customer-id", ""))
    except ToolError as e:
        raise PermissionError(str(e))
    if not CUSTOMER_RE.match(cid):
        raise PermissionError("Thiếu X-Customer-Id")
    return cid


async def _rest(request: Request, fn, *args, **kwargs):
    try:
        cid = _ui_auth(request)
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=401)
    try:
        r = await anyio.to_thread.run_sync(lambda: fn(cid, *args, **kwargs))
    except T.ToolError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(r if isinstance(r, dict) else {"result": r}, headers={"Cache-Control": "no-store"})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    # Luôn 200 để AgentBase đánh dấu ACTIVE; trạng thái DB nằm trong body.
    st = await anyio.to_thread.run_sync(T.health)
    return JSONResponse({"status": "ok", "service": "voice-banking-mcp", "version": VERSION, **st})


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> JSONResponse:
    return JSONResponse({"service": "voice-banking-mcp", "mcp": "/mcp", "health": "/health"})


@mcp.custom_route("/api/me/accounts", methods=["GET"])
async def api_accounts(request: Request):
    return await _rest(request, lambda cid: T.TOOLS["get_account_balances"](customer_id=cid))


@mcp.custom_route("/api/me/transactions", methods=["GET"])
async def api_transactions(request: Request):
    limit = int(request.query_params.get("limit", "30"))
    return await _rest(request, T.get_transactions_for_ui, limit)


@mcp.custom_route("/api/me/beneficiaries", methods=["GET"])
async def api_beneficiaries(request: Request):
    return await _rest(request, lambda cid: T.TOOLS["list_beneficiaries"](customer_id=cid))


@mcp.custom_route("/api/actions/{action_id}", methods=["GET"])
async def api_get_action(request: Request):
    return await _rest(request, T.get_action_for_ui, request.path_params["action_id"])


@mcp.custom_route("/api/actions/{action_id}/status", methods=["POST"])
async def api_action_status(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Body phải là JSON {\"status\": \"opened|submitted|cancelled\"}"}, status_code=400)
    return await _rest(request, T.update_action_status_for_ui, request.path_params["action_id"], body.get("status", ""))


def build_http_app():
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,        # không giữ phiên trong RAM -> scale nhiều replica, restart không mất phiên
        json_response=True,         # trả JSON thay vì SSE, đi qua proxy/gateway ổn định hơn
        host=os.getenv("HOST", "0.0.0.0"),
    )
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
                           allow_headers=["*"], expose_headers=["mcp-session-id"])
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdio", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if a.stdio:
        mcp.run()
        return
    if not API_KEY:
        log.warning("MCP_API_KEY chưa đặt: %s", "chạy KHÔNG xác thực (ALLOW_NO_AUTH=true)" if ALLOW_NO_AUTH
                    else "mọi request sẽ bị từ chối")
    import uvicorn
    uvicorn.run(build_http_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")),
                log_level=os.getenv("LOG_LEVEL", "info").lower(), proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
