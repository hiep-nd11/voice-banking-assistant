"""Tool registry — schema cho LLM (OpenAI function-calling format).

Khớp các tool thật trên MCP server voice-banking-assistant (localhost:8080/mcp)
+ create_budget_plan tính locally từ dữ liệu MCP.
Nguyên tắc: mô tả rõ khi nào dùng tool; tham số đơn giản để LLM điền đúng.
"""

from __future__ import annotations

from app.agent.workflow_config import CONFIG as WORKFLOW_CONFIG

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Ngày hôm nay và các mốc thời gian (đầu tuần, tháng này, tháng trước). Gọi TRƯỚC khi tính "
            "khoảng ngày cho 'tháng này', 'tuần trước'...",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_profile",
            "description": "Tên, cách xưng hô, tuổi, nghề nghiệp, nhu cầu hỗ trợ của khách hàng đang đăng nhập.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balances",
            "description": "Số dư tài khoản thanh toán, các sổ tiết kiệm (lãi suất, ngày đến hạn), khoản vay (kỳ trả "
            "tiếp theo). Dùng khi khách hỏi số dư, tiền tiết kiệm, nợ vay.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": "Vài giao dịch gần nhất ('dạo này tôi tiêu gì', 'vừa rồi có ai chuyển tiền cho tôi không').",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Số giao dịch tối đa (1-20). Mặc định 5.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["in", "out"],
                        "description": "in = tiền vào, out = tiền ra. Optional.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_month_overview",
            "description": "Tổng quan 1 tháng: thu, chi, còn dư, 3 khoản chi lớn nhất, so với tháng trước. Dùng cho "
            "câu hỏi chung 'tháng này tôi tiêu thế nào'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Tháng dạng YYYY-MM. Bỏ trống = tháng này.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": "Tổng chi tiêu trong khoảng ngày, chia theo danh mục/tháng/nơi chi/nhóm (không tính gửi "
            "tiết kiệm, đầu tư, cho mượn). Dùng khi khách hỏi chi tiêu theo khoảng thời gian cụ thể.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Ngày bắt đầu YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Ngày kết thúc YYYY-MM-DD."},
                    "group_by": {
                        "type": "string",
                        "enum": ["category", "month", "merchant", "group"],
                        "description": "Cách nhóm chi tiêu. Mặc định 'category'.",
                    },
                    "top": {
                        "type": "integer",
                        "description": "Số nhóm hàng đầu trả về (1-20). Mặc định 5.",
                    },
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_income_summary",
            "description": "Tổng tiền nhận được (lương, thưởng, lãi...) trong khoảng ngày.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Ngày bắt đầu YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Ngày kết thúc YYYY-MM-DD."},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "Tìm giao dịch cụ thể + tổng tiền khớp điều kiện ('tháng này tôi trả tiền điện bao nhiêu', "
            "'đóng học phí khi nào'). KHÔNG dùng cho tổng hợp chi tiêu (dùng get_spending_summary).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Ngày bắt đầu YYYY-MM-DD."},
                    "date_to": {"type": "string", "description": "Ngày kết thúc YYYY-MM-DD."},
                    "category": {
                        "type": "string",
                        "description": "Danh mục ('tiền điện', 'đi chợ', 'học phí') hoặc mã. Optional.",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Từ khóa trong nội dung/người nhận ('hoc phi', 'shopee'). Optional.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["in", "out"],
                        "description": "in = tiền vào, out = tiền ra. Optional.",
                    },
                    "min_amount": {
                        "type": "integer",
                        "description": "Số tiền tối thiểu (VND). Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số kết quả tối đa (1-50). Mặc định 10.",
                    },
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "So sánh chi tiêu kỳ A (cũ) với kỳ B (mới), toàn bộ hoặc một danh mục. Dùng cho 'tháng này "
            "so với tháng trước thế nào' khi cần chi tiết theo danh mục.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a_from": {"type": "string", "description": "Kỳ A (cũ) bắt đầu YYYY-MM-DD."},
                    "a_to": {"type": "string", "description": "Kỳ A (cũ) kết thúc YYYY-MM-DD."},
                    "b_from": {"type": "string", "description": "Kỳ B (mới) bắt đầu YYYY-MM-DD."},
                    "b_to": {"type": "string", "description": "Kỳ B (mới) kết thúc YYYY-MM-DD."},
                    "category": {
                        "type": "string",
                        "description": "Chỉ so sánh 1 danh mục. Optional.",
                    },
                },
                "required": ["a_from", "a_to", "b_from", "b_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_trend",
            "description": "Số tiền của một khoản chi theo từng tháng ('tiền điện mấy tháng nay thế nào'), kèm trung "
            "bình các tháng trước và so sánh tháng này.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Danh mục ('tiền điện', 'đi chợ'...).",
                    },
                    "months": {
                        "type": "integer",
                        "description": "Số tháng gần nhất (2-18). Mặc định 6.",
                    },
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_unusual_transactions",
            "description": "Rà soát giao dịch bất thường (mặc định 30 ngày): người nhận lạ số tiền lớn, giờ khuya, "
            "trừ trùng, hóa đơn tăng vọt, nội dung giống lừa đảo. Dùng cho 'có gì bất thường không'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {
                        "type": "string",
                        "description": "Ngày bắt đầu YYYY-MM-DD. Optional.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Ngày kết thúc YYYY-MM-DD. Optional.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Sản phẩm tiết kiệm/vay của ngân hàng kèm lãi suất tham khảo (dữ liệu MOCK). Dùng khi khách "
            "quan tâm gửi tiết kiệm, vay vốn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_type": {
                        "type": "string",
                        "enum": ["savings", "loan"],
                        "description": "Loại sản phẩm. Optional.",
                    },
                    "term_months": {
                        "type": "integer",
                        "description": "Kỳ hạn tháng (1-36). Optional.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_budget_plan",
            "description": "Lập kế hoạch chi tiêu 50/30/20 (cần thiết/muốn mua/tích lũy) dựa trên thu nhập và chi tiêu "
            "thực tế 3 tháng gần nhất của khách. Dùng khi khách muốn lập kế hoạch chi tiêu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_income": {
                        "type": "number",
                        "description": "Thu nhập hàng tháng (VND) nếu khách nói rõ. Optional.",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Mục tiêu tích lũy nếu có. Optional.",
                    },
                },
                "required": [],
            },
        },
    },
]

TOOL_SCHEMAS.append(
    {
        "type": "function",
        "function": {
            "name": "start_banking_workflow",
            "description": "Mở kịch bản giao diện khi khách YÊU CẦU hành động hoặc xem một mục. Không dùng cho câu hỏi cách làm, giả định hoặc phủ định. Không thực hiện giao dịch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": list(WORKFLOW_CONFIG.scenarios)},
                    "recipient_name": {
                        "type": "string",
                        "description": "Tên/cách gọi người nhận, phải có nguyên văn trong câu khách vừa nói.",
                    },
                },
                "required": ["intent"],
                "additionalProperties": False,
            },
        },
    }
)

TOOL_NAMES = [t["function"]["name"] for t in TOOL_SCHEMAS]
