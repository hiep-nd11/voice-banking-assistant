"""MCP client adapter — gọi tool qua MCP server (voice-banking-assistant) thay vì query DB trực tiếp.

Điều phối tool cho orchestrator: local tool tính tại chỗ, còn lại forward qua MCP.
Server MCP chạy stateless (JSON-RPC qua HTTP POST), gắn cố định 1 khách hàng qua VB_CUSTOMER_ID.
"""
from __future__ import annotations

import json
from datetime import date

import httpx

from app.core.config import settings

# Tool tính locally từ dữ liệu MCP (không có sẵn bên server)
LOCAL_TOOLS = {"create_budget_plan"}


async def call_mcp(name: str, args: dict | None = None) -> dict:
    """Gọi 1 tool trên MCP server, trả dict kết quả (đã parse JSON từ text content)."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": {k: v for k, v in (args or {}).items() if v is not None}},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-Api-Key": settings.mcp_api_key,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(settings.mcp_base_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("error"):
        return {"error": f"MCP error: {data['error'].get('message', data['error'])}"}
    result = data.get("result") or {}
    if result.get("isError"):
        # ToolError bên server: content[0].text là thông điệp lỗi
        texts = [c.get("text", "") for c in result.get("content") or []]
        return {"error": "; ".join(t for t in texts if t) or "tool error"}
    for c in result.get("content") or []:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return {"raw": c["text"]}
    return {"error": f"tool {name} không trả nội dung"}


# ---------------------------------------------------------------- kế hoạch chi tiêu 50/30/20 (local)
def _needs_wants_label(label: str) -> str:
    return "needs" if "thiết yếu" in (label or "") else "wants"


async def _create_budget_plan(args: dict) -> dict:
    """50/30/20 từ dữ liệu thật: thu nhập trung bình 3 tháng + nhóm chi needs/wants qua MCP."""
    cur = await call_mcp("get_current_date", {})
    today = date.fromisoformat(cur["today"])

    # cửa sổ 3 tháng gần nhất (kể cả tháng này)
    def month_start(d: date) -> date:
        return date(d.year, d.month, 1)

    def prev_month(d: date) -> date:
        return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)

    m0 = month_start(today)
    win_from = prev_month(prev_month(m0))

    income_r = await call_mcp("get_income_summary", {"date_from": win_from.isoformat(), "date_to": today.isoformat()})
    groups_r = await call_mcp("get_spending_summary", {
        "date_from": win_from.isoformat(), "date_to": today.isoformat(), "group_by": "group", "top": 10,
    })
    if "error" in income_r or "error" in groups_r:
        return {"error": income_r.get("error") or groups_r.get("error")}

    income = args.get("monthly_income") or (income_r.get("total_income") or 0) // 3
    if not income:
        return {"error": "Không có dữ liệu thu nhập để lập kế hoạch. Hỏi khách thu nhập hàng tháng."}

    cur_needs = cur_wants = 0
    for it in groups_r.get("items", []):
        if _needs_wants_label(it.get("label", "")) == "needs":
            cur_needs += it.get("total", 0)
        else:
            cur_wants += it.get("total", 0)
    cur_needs, cur_wants = cur_needs // 3, cur_wants // 3  # trung bình/tháng

    plan = {
        "needs": {"target": int(income * 0.5), "current_avg": cur_needs,
                  "includes": "Ăn uống, đi lại, hóa đơn, sức khỏe, giáo dục (chi thiết yếu)"},
        "wants": {"target": int(income * 0.3), "current_avg": cur_wants,
                  "includes": "Mua sắm, giải trí, chi tiêu cá nhân"},
        "savings": {"target": int(income * 0.2), "current_avg": max(0, income - cur_needs - cur_wants),
                    "includes": "Tiết kiệm/đầu tư hàng tháng"},
    }
    adjustments = []
    if cur_needs > plan["needs"]["target"]:
        adjustments.append(f"Nhóm chi thiết yếu đang {cur_needs:,}đ/tháng, vượt khung 50% ({plan['needs']['target']:,}đ).")
    if cur_wants > plan["wants"]["target"]:
        adjustments.append(f"Nhóm muốn mua đang {cur_wants:,}đ/tháng, vượt khung 30% ({plan['wants']['target']:,}đ) — "
                           f"giảm khoảng {cur_wants - plan['wants']['target']:,}đ/tháng.")
    if not adjustments:
        adjustments.append("Chi tiêu hiện tại nằm trong khung 50/30/20. Duy trì và tối ưu phần tích lũy 20%.")

    return {
        "monthly_income": income,
        "monthly_income_fmt": f"{income:,}đ".replace(",", "."),
        "window": f"{win_from.isoformat()} -> {today.isoformat()} (trung bình 3 tháng)",
        "rule": "50/30/20 (50% cần thiết — 30% muốn mua — 20% tích lũy)",
        "plan": plan,
        "adjustments": adjustments,
        "goal": args.get("goal"),
    }


async def dispatch_tool(name: str, customer_id, args: dict) -> dict:
    """Điều phối tool: local tool tính tại chỗ, còn lại gọi qua MCP server."""
    args = args or {}
    if name in LOCAL_TOOLS:
        if name == "create_budget_plan":
            return await _create_budget_plan(args)
    return await call_mcp(name, args)
