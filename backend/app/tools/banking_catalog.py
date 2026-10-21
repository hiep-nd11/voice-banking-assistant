"""Curated UI features, validated against the upstream tools/list snapshot."""

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, create_model

from app.tools.registry import TOOL_SCHEMAS

FEATURES = {
    "profile": ("Hồ sơ khách hàng", "get_customer_profile"),
    "accounts": ("Tài khoản, tiết kiệm và khoản vay", "get_account_balances"),
    "beneficiaries": ("Danh bạ ngân hàng", "list_beneficiaries"),
    "find-recipient": ("Tìm người nhận", "find_beneficiary"),
    "month": ("Tổng quan tháng", "get_month_overview"),
    "spending": ("Phân tích chi tiêu", "get_spending_summary"),
    "income": ("Thu nhập", "get_income_summary"),
    "recent": ("Giao dịch gần nhất", "get_recent_transactions"),
    "transactions": ("Tra cứu giao dịch", "search_transactions"),
    "compare": ("So sánh hai giai đoạn", "compare_periods"),
    "trend": ("Xu hướng theo danh mục", "get_category_trend"),
    "alerts": ("Giao dịch cần chú ý", "detect_unusual_transactions"),
    "products": ("Sản phẩm tiết kiệm và vay", "search_products"),
    "budget": ("Kế hoạch chi tiêu 50/30/20", "create_budget_plan"),
    "amount": ("Đọc số tiền", "parse_vnd_amount"),
    "risk": ("Kiểm tra rủi ro chuyển tiền", "check_transfer_risk"),
    "prepare-transfer": ("Chuẩn bị chuyển tiền", "open_transfer_screen"),
    "prepare-savings": ("Chuẩn bị gửi tiết kiệm", "open_savings_screen"),
    "prepare-loan": ("Chuẩn bị đăng ký vay", "open_loan_screen"),
    "cancel": ("Hủy yêu cầu đã chuẩn bị", "cancel_pending_action"),
    "calendar": ("Mốc thời gian dữ liệu", "get_current_date"),
}
TOOLS = {
    t["name"]: t
    for t in json.loads(Path(__file__).with_name("banking_tools.json").read_text(encoding="utf-8"))
}
budget = next(t["function"] for t in TOOL_SCHEMAS if t["function"]["name"] == "create_budget_plan")
TOOLS[budget["name"]] = {
    **budget,
    "inputSchema": budget["parameters"],
    "annotations": {"readOnlyHint": True},
}
# Business minima verified against upstream execution; tools/list currently
# advertises only the generic 1,000 VND bound for both these operations.
TOOLS["open_savings_screen"]["inputSchema"]["properties"]["amount"]["minimum"] = 1_000_000
TOOLS["open_loan_screen"]["inputSchema"]["properties"]["amount"]["minimum"] = 5_000_000
TOOLS["create_budget_plan"]["inputSchema"]["properties"]["monthly_income"]["minimum"] = 1


def field_type(schema):
    if "anyOf" in schema:
        option = next(s for s in schema["anyOf"] if s.get("type") != "null")
        return field_type(option) | None
    if "enum" in schema:
        return Literal[tuple(schema["enum"])]
    return {"string": str, "integer": int, "number": float, "boolean": bool}[schema["type"]]


def request_model(name, schema):
    fields = {}
    for key, prop in schema.get("properties", {}).items():
        constraints = next((s for s in prop.get("anyOf", []) if s.get("type") != "null"), prop)
        limits = {
            target: constraints[source]
            for source, target in (
                ("minimum", "ge"),
                ("maximum", "le"),
                ("maxLength", "max_length"),
                ("pattern", "pattern"),
            )
            if source in constraints
        }
        if key in {"text", "name", "category", "action_id"}:
            limits["min_length"] = 1
        fields[key] = (
            field_type(prop),
            Field(
                default=... if key in schema.get("required", []) else prop.get("default"), **limits
            ),
        )
    return create_model(name, __config__=ConfigDict(extra="forbid", strict=True), **fields)


MODELS = {
    feature: request_model(feature, TOOLS[tool]["inputSchema"])
    for feature, (_, tool) in FEATURES.items()
}


def validate_dates(args):
    for key, value in args.items():
        if key in {"date_from", "date_to", "a_from", "a_to", "b_from", "b_to"}:
            date.fromisoformat(value)
        elif key == "month":
            date.fromisoformat(value + "-01")
    for start, end in [("date_from", "date_to"), ("a_from", "a_to"), ("b_from", "b_to")]:
        if start in args and end in args and args[start] > args[end]:
            raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")
