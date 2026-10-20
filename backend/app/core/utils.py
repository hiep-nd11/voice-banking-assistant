"""Tiện ích chung: định dạng tiền tệ, ngày tháng, chuẩn hóa category tiếng Việt."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

# Danh mục chi tiêu + từ khóa nhận diện (chuẩn hóa không dấu, thường).
CATEGORY_ALIASES: dict[str, list[str]] = {
    "an_uong": ["an uong", "an", "uong", "do an", "food", "nha hang", "ca phe", "quan an", "com"],
    "di_lai": ["di lai", "xe", "grab", "xang", "bus", "taxi", "transport", "ve", "parking", "gui xe"],
    "mua_sam": ["mua sam", "shopping", "shopee", "lazada", "quan ao", "do gia dung", "ttvn", "sieu thi"],
    "hoa_don_tien_ich": ["hoa don", "tien ich", "dien", "nuoc", "internet", "wifi", "cuoc dt", "utility", "utilities"],
    "giai_tri": ["giai tri", "phim", "netflix", "game", "spotify", "karaoke", "du lich", "entertainment"],
    "suc_khoe": ["suc khoe", "y te", "thuoc", "benh vien", "kham", "health"],
    "giao_duc": ["giao duc", "hoc", "sach", "khoa hoc", "hoc phi", "education"],
    "chuyen_khoan": ["chuyen khoan", "chuyen tien", "transfer", "ck", "thu huong"],
    "khac": ["khac", "other"],
}
ALL_CATEGORIES = list(CATEGORY_ALIASES.keys())

CATEGORY_LABEL_VI: dict[str, str] = {
    "an_uong": "Ăn uống",
    "di_lai": "Đi lại",
    "mua_sam": "Mua sắm",
    "hoa_don_tien_ich": "Hóa đơn & tiện ích",
    "giai_tri": "Giải trí",
    "suc_khoe": "Sức khỏe",
    "giao_duc": "Giáo dục",
    "chuyen_khoan": "Chuyển khoản",
    "khac": "Khác",
}


def strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    return strip_accents(s or "").lower().strip()


def resolve_category(text: str) -> str | None:
    """Tìm category khớp với text tự do (LLM có thể trả 'Ăn uống' hoặc 'an uong')."""
    n = norm(text)
    if not n:
        return None
    if n in CATEGORY_ALIASES:
        return n
    for cat, aliases in CATEGORY_ALIASES.items():
        if n == cat or any(n == norm(a) or norm(a) in n for a in [cat.replace("_", " "), *aliases]):
            return cat
    return None


def fmt_money(v: Decimal | float | int | None) -> str:
    """1234500 -> '1.234.500₫' (định dạng Việt Nam)."""
    if v is None:
        return "0₫"
    d = Decimal(str(v))
    sign = "-" if d < 0 else ""
    return f"{sign}{abs(int(d)):,}".replace(",", ".") + "₫"


def fmt_money_k(v: Decimal | float | int | None) -> str:
    """Rút gọn: 25_000_000 -> '25tr', 450_000 -> '450k'."""
    d = float(v or 0)
    if abs(d) >= 1_000_000_000:
        return f"{d/1_000_000_000:.1f} tỷ".replace(".0", "")
    if abs(d) >= 1_000_000:
        return f"{d/1_000_000:.1f} tr".replace(".0", "")
    if abs(d) >= 1_000:
        return f"{d/1_000:.0f}k"
    return f"{d:.0f}"


def resolve_period_dates(period: str | None, ref_date: date | None = None) -> tuple[date, date]:
    """Bước (from_date, to_date) inclusive cho 'week' | 'month' | 'quarter' theo ref_date (mặc định hôm nay).

    Tool tự resolve theo ngày server — không để LLM tự tính ngày (nguyên tắc: LLM không làm toán).
    """
    today = ref_date or date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
    elif period == "quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, q_start_month, 1)
    else:  # month (mặc định)
        start = date(today.year, today.month, 1)
    return start, today


def period_label(period: str) -> str:
    return {"week": "tuần này", "month": "tháng này", "quarter": "quý này"}.get(period or "month", "tháng này")


def prev_period_dates(period: str, start: date, end: date) -> tuple[date, date]:
    """Kỳ dương lịch liền trước — dùng cho so sánh trong report."""
    if period == "week":
        return start - timedelta(days=7), end - timedelta(days=7)
    if period == "quarter":
        q_start_month = ((start.month - 1) // 3) * 3 + 1
        prev_q_end = date(start.year, q_start_month, 1) - timedelta(days=1)
        pm, py = q_start_month - 3, start.year
        if pm <= 0:
            pm += 12
            py -= 1
        return date(py, pm, 1), prev_q_end
    # month: tháng dương lịch trước (đầy đủ các ngày)
    prev_end = start - timedelta(days=1)
    return date(prev_end.year, prev_end.month, 1), prev_end


def fmt_date(d: date | datetime) -> str:
    return d.strftime("%d/%m/%Y") if isinstance(d, datetime) else d.strftime("%d/%m/%Y")
