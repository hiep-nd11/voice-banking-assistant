"""
Bộ tool cho Voice Banking Assistant.

Nguyên tắc thiết kế (dùng để trình bày với giám khảo):
1. LLM KHÔNG tự tính số. Mọi con số do SQL/Python tính, trả kèm câu `speech` đã viết sẵn
   (số tiền đọc thành chữ) để TTS đọc đúng -> kiểm soát hallucination.
2. Agent KHÔNG thực hiện giao dịch. Tool open_*_screen chỉ tạo bản ghi pending_actions
   (mở màn hình + điền sẵn). Khách tự nhập phần còn lại và tự xác nhận OTP/sinh trắc học.
3. customer_id do server gắn theo phiên đăng nhập, không phải tham số LLM điền.
4. Số tài khoản trả cho LLM luôn được che (chỉ 4 số cuối). Bản đầy đủ chỉ đi qua REST
   tới giao diện app (đã xác thực).
5. Mọi lần gọi tool được ghi vb.tool_audit_log.
6. Cột nhãn eval (is_anomaly_seed) không bao giờ được đọc: tool chỉ truy vấn view vb.v_txn.
"""
from __future__ import annotations

import atexit
import contextvars
import json
import math
import os
import re
import secrets
import statistics
import time as _time
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .vn_money import parse_vnd_amount as _parse_amount
from .vn_money import vnd_speak, vnd_text, vnd_words

TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")
ACTION_TTL_MIN = int(os.getenv("ACTION_TTL_MINUTES", "15"))
MAX_TRANSFER = int(os.getenv("MAX_PREFILL_TRANSFER", "500000000"))   # 500 triệu: trên mức này không điền sẵn
BANK_HOTLINE = os.getenv("BANK_HOTLINE", "tổng đài chăm sóc khách hàng in ở mặt sau thẻ")

# ngữ cảnh audit theo request (MCP server set: session_id, model_name)
AUDIT_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("AUDIT_CTX", default={})

_pool: ConnectionPool | None = None


class ToolError(Exception):
    """Lỗi nghiệp vụ, thông điệp đọc được cho khách/agent."""


# ============================================================ DB & thời gian
def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=int(os.getenv("DB_POOL_MAX", "5")),
                               kwargs={"autocommit": True, "row_factory": dict_row}, open=True, timeout=10)
    return _pool


@atexit.register
def _close_pool():
    if _pool is not None:
        _pool.close()


def _q(sql: str, params=None) -> list[dict]:
    with _get_pool().connection() as c:
        cur = c.execute(sql, params)
        return [_norm(r) for r in cur.fetchall()] if cur.description else []


def _q1(sql: str, params=None) -> dict | None:
    rows = _q(sql, params)
    return rows[0] if rows else None


def _norm(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            v = int(v) if v == v.to_integral_value() else float(v)
        out[k] = v
    return out


def now() -> datetime:
    """Giờ hiện tại (giờ VN, naive). DEMO_NOW=2026-10-21T09:30 để cố định khi quay demo."""
    if os.getenv("DEMO_NOW"):
        return datetime.fromisoformat(os.environ["DEMO_NOW"])
    return datetime.now(TZ).replace(tzinfo=None)


def today() -> date:
    return now().date()


def _date(s, name="ngày") -> date:
    if isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        raise ToolError(f"{name} không hợp lệ: {s!r}, cần dạng YYYY-MM-DD")


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _prev_month(d: date) -> date:
    return _month_start(_month_start(d) - timedelta(days=1))


def _range(date_from, date_to) -> tuple[date, date]:
    """Chuẩn hóa khoảng ngày [from, to], không vượt quá hôm nay (dữ liệu tương lai bị ẩn)."""
    a, b = _date(date_from, "date_from"), _date(date_to, "date_to")
    if a > b:
        a, b = b, a
    b = min(b, today())
    if a > b:
        raise ToolError("Khoảng thời gian nằm sau ngày hôm nay, chưa có dữ liệu")
    return a, b


_WD = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


def _d_vi(d: date | datetime) -> str:
    return f"ngày {d.day} tháng {d.month}"


def _d_vi_full(d: date) -> str:
    return f"ngày {d.day} tháng {d.month} năm {d.year}"


def _range_vi(a: date, b: date) -> str:
    if a == _month_start(a) and (b == _next_month(a) - timedelta(days=1) or (b == today() and b.month == a.month
                                                                          and b.year == a.year)):
        return f"tháng {a.month}" + (f" năm {a.year}" if a.year != today().year else "") + \
            (" (tính đến hôm nay)" if b == today() and b < _next_month(a) - timedelta(days=1) else "")
    if a.year != b.year:
        return f"từ {_d_vi(a)} năm {a.year} đến {_d_vi(b)} năm {b.year}"
    return f"từ {_d_vi(a)} đến {_d_vi(b)}" + (f" năm {b.year}" if b.year != today().year else "")


def _t_vi(dt: datetime) -> str:
    h, m = dt.hour, dt.minute
    part = "sáng" if 4 <= h < 11 else "trưa" if h < 13 else "chiều" if h < 18 else "tối" if h < 22 else "đêm"
    if h < 4:
        part = "sáng"
    hh = h if h <= 12 else h - 12
    return f"{hh} giờ" + (f" {m}" if m else "") + f" {part}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _lower1(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").strip()


def _mask(acc: str | None) -> str | None:
    if not acc:
        return acc
    return "****" + acc[-4:]


# ============================================================ đăng ký tool + audit
TOOLS: dict = {}


def tool(fn):
    @wraps(fn)
    def wrapper(**kwargs):
        t0 = _time.perf_counter()
        err = False
        try:
            result = fn(**kwargs)
        except ToolError as e:
            result, err = {"error": str(e)}, True
        latency = int((_time.perf_counter() - t0) * 1000)
        try:
            ctx = AUDIT_CTX.get()
            _q("INSERT INTO vb.tool_audit_log (customer_id, session_id, tool_name, arguments, result_summary,"
               " is_error, latency_ms, model_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
               (kwargs.get("customer_id"), ctx.get("session_id"), fn.__name__,
                json.dumps(kwargs, default=str, ensure_ascii=False),
                json.dumps(result, default=str, ensure_ascii=False)[:800], err, latency, ctx.get("model_name")))
        except Exception:
            pass   # audit không được làm hỏng câu trả lời
        return result

    TOOLS[fn.__name__] = wrapper
    return wrapper


def call_tool(name: str, args: dict):
    if name not in TOOLS:
        return {"error": f"Không có tool {name}"}
    return TOOLS[name](**args)


# ============================================================ helper nghiệp vụ
def _customer(cid: str) -> dict:
    c = _q1("SELECT * FROM vb.customers WHERE customer_id = %s", (cid,))
    if not c:
        raise ToolError("Không tìm thấy khách hàng của phiên này")
    return c


def _pronoun(c: dict) -> str:
    return (c.get("salutation") or "quý khách").split()[0]


def _category_map() -> dict:
    return {r["category_code"]: r for r in _q("SELECT * FROM vb.categories")}


def resolve_category(text: str | None) -> list[str]:
    """Nhận mã danh mục hoặc cách nói tiếng Việt ('tiền điện', 'đi chợ') -> danh sách mã."""
    if not text:
        return []
    cats = _category_map()
    if text in cats:
        return [text]
    t = _strip(text)
    t = re.sub(r"^(tien|khoan|chi|chi phi|phi)\s+", "", t) if t not in ("tien dien", "tien nuoc") else t
    hits = []
    for code, c in cats.items():
        names = [_strip(c["name_vi"])] + [k.strip() for k in (c["keywords"] or "").split(",") if k.strip()]
        if any(t == n or (len(t) >= 3 and (t in n.split(",") or n == t)) for n in names):
            hits.append(code)
    if not hits:
        for code, c in cats.items():
            names = [_strip(c["name_vi"])] + [k.strip() for k in (c["keywords"] or "").split(",") if k.strip()]
            if any(len(n) >= 3 and (n in t or (len(t) >= 4 and t in n)) for n in names):
                hits.append(code)
    return hits


def _unknown_category(category: str) -> ToolError:
    names = ", ".join(c["name_vi"] for c in _category_map().values())
    return ToolError(f"Không xác định được danh mục '{category}'. Các danh mục có: {names}. "
                     "Có thể tìm theo từ khóa (keyword) thay cho danh mục.")


def _cat_filter(category: str | None) -> tuple[str, list]:
    if not category:
        return "", []
    codes = resolve_category(category)
    if not codes:
        raise _unknown_category(category)
    return " AND category_code = ANY(%s)", [codes]


def _payment_balance(cid: str) -> int:
    r = _q1("""SELECT t.balance_after FROM vb.v_txn t
               WHERE t.customer_id = %s AND t.account_type = 'payment' AND t.txn_time <= %s
               ORDER BY t.txn_time DESC, t.txn_id DESC LIMIT 1""", (cid, now()))
    if r:
        return int(r["balance_after"])
    a = _q1("SELECT balance FROM vb.accounts WHERE customer_id=%s AND account_type='payment' AND status='active'"
            " LIMIT 1", (cid,))
    return int(a["balance"]) if a else 0


def _txn_item(r: dict) -> dict:
    return {
        "txn_id": r["txn_id"],
        "time": r["txn_time"].isoformat(timespec="minutes"),
        "amount": r["amount"],
        "amount_text": vnd_text(r["amount"]),
        "direction": r["direction"],
        "category": r.get("category_name"),
        "category_code": r.get("category_code"),
        "description": r["description"],
        "counterparty": r.get("counterparty_name") or r.get("merchant"),
        "account": r.get("account_nickname"),
    }


_BENEF_CACHE: dict = {}


def _benef_names(cid: str) -> dict:
    if cid not in _BENEF_CACHE:
        _BENEF_CACHE[cid] = {r["account_number"]: f"{r['relationship']} {r['display_name']}" for r in
                             _q("SELECT * FROM vb.beneficiaries WHERE customer_id=%s", (cid,))}
    return _BENEF_CACHE[cid]


def _txn_speech(r: dict) -> str:
    """Câu đọc cho TTS. Tên trong sao kê là chữ không dấu -> chỉ đọc tên có dấu lấy từ danh bạ đã lưu."""
    verb = "nhận" if r["direction"] == "in" else "chi"
    what = (r.get("category_name") or "").lower()
    who = _benef_names(r["customer_id"]).get(r.get("counterparty_account") or "", "") if r.get("customer_id") else ""
    s = f"{_d_vi(r['txn_time'])}, {verb} {vnd_speak(r['amount'])}"
    if what:
        s += f" {'' if r['direction'] == 'in' else 'cho '}{what}"
    if who:
        s += f" ({who})" if r["direction"] == "in" else f", gửi {who}"
    return s


# ============================================================ 0. TIỆN ÍCH
@tool
def get_current_date() -> dict:
    """Ngày hôm nay + các mốc hay dùng để tính khoảng thời gian."""
    t = today()
    this_m = _month_start(t)
    last_m = _prev_month(t)
    week_start = t - timedelta(days=t.weekday())
    return {
        "today": t.isoformat(),
        "weekday": _WD[t.weekday()],
        "this_week_start": week_start.isoformat(),
        "last_week": [(week_start - timedelta(days=7)).isoformat(), (week_start - timedelta(days=1)).isoformat()],
        "this_month_start": this_m.isoformat(),
        "last_month": [last_m.isoformat(), (this_m - timedelta(days=1)).isoformat()],
        "this_year_start": date(t.year, 1, 1).isoformat(),
        "speech": f"Hôm nay là {_WD[t.weekday()]}, {_d_vi_full(t)}.",
    }


@tool
def parse_vnd_amount(text: str) -> dict:
    """Hiểu số tiền khách nói ('một triệu rưỡi', '500k', 'hai củ') -> số VND + câu đọc lại để xác nhận."""
    return _parse_amount(text)


@tool
def list_categories() -> dict:
    rows = _q("SELECT category_code, name_vi, group_code, direction FROM vb.categories ORDER BY direction, group_code, 1")
    return {"categories": rows}


# ============================================================ 1. HỒ SƠ & SỐ DƯ
@tool
def get_customer_profile(customer_id: str) -> dict:
    c = _customer(customer_id)
    t = today()
    dob = c["date_of_birth"]
    age = t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day)) if dob else None
    return {
        "full_name": c["full_name"], "salutation": c["salutation"], "age": age, "city": c["city"],
        "occupation": c["occupation"], "accessibility_needs": c["accessibility_needs"],
        "speech_hint": f"Xưng hô với khách là '{c['salutation']}'.",
    }


@tool
def get_account_balances(customer_id: str) -> dict:
    c = _customer(customer_id)
    p = _pronoun(c)
    t, n = today(), now()
    accs = _q("SELECT * FROM vb.accounts WHERE customer_id=%s AND status='active' AND opened_at <= %s "
              "ORDER BY CASE account_type WHEN 'payment' THEN 1 WHEN 'savings' THEN 2 ELSE 3 END, account_id",
              (customer_id, t))
    out, speech = [], []
    pay_total = sav_total = 0
    for a in accs:
        item = {"account_id": a["account_id"], "type": a["account_type"], "name": a["nickname"],
                "account_number": _mask(a["account_number"]), "parent_account_id": a["parent_account_id"]}
        if a["account_type"] == "payment":
            last = _q1("SELECT balance_after FROM vb.v_txn WHERE account_id=%s AND txn_time <= %s "
                       "ORDER BY txn_time DESC, txn_id DESC LIMIT 1", (a["account_id"], n))
            bal = int(last["balance_after"]) if last else int(a["balance"])
        else:
            bal = int(a["balance"])
        if a["account_type"] == "payment":
            pay_total += bal
            item.update(balance=bal, balance_text=vnd_text(bal))
            speech.append(f"{_lower1(a['nickname'])} đang có {vnd_speak(bal)}")
        elif a["account_type"] == "savings":
            sav_total += bal
            days = (a["maturity_date"] - t).days if a["maturity_date"] else None
            item.update(balance=bal, balance_text=vnd_text(bal), interest_rate=a["interest_rate"],
                        term_months=a["term_months"], maturity_date=a["maturity_date"].isoformat()
                        if a["maturity_date"] else None, days_to_maturity=days)
            s = f"{_lower1(a['nickname'])} {vnd_speak(bal)}"
            if days is not None and 0 <= days <= 30:
                s += f", sẽ đến hạn {_d_vi(a['maturity_date'])}, tức là còn {days} ngày"
            speech.append(s)
        elif a["account_type"] == "loan":
            nxt = t.replace(day=15) if t.day <= 15 else _next_month(t).replace(day=15)
            item.update(outstanding=bal, outstanding_text=vnd_text(bal), monthly_payment=a["monthly_payment"],
                        next_payment_date=nxt.isoformat(), interest_rate=a["interest_rate"],
                        maturity_date=a["maturity_date"].isoformat() if a["maturity_date"] else None)
            speech.append(f"{a['nickname'].lower()} còn dư nợ {vnd_speak(bal)}, kỳ trả tiếp theo {_d_vi(nxt)} "
                          f"là {vnd_speak(a['monthly_payment'] or 0)}")
        out.append(item)
    return {
        "as_of": n.isoformat(timespec="minutes"),
        "accounts": out,
        "total_payment": pay_total, "total_savings": sav_total,
        "speech": (f"Thưa {c['salutation']}, " + "; ".join(speech) + ".") if speech else
                  f"{p.capitalize()} chưa có tài khoản nào đang hoạt động.",
    }


# ============================================================ 2. GIAO DỊCH
@tool
def get_recent_transactions(customer_id: str, limit: int = 5, direction: str | None = None) -> dict:
    """N giao dịch gần nhất của tài khoản thanh toán."""
    c = _customer(customer_id)
    limit = max(1, min(int(limit), 20))
    sql = "SELECT * FROM vb.v_txn WHERE customer_id=%s AND txn_time <= %s AND account_type = 'payment'"
    params: list = [customer_id, now()]
    if direction in ("in", "out"):
        sql += " AND direction=%s"
        params.append(direction)
    rows = _q(sql + " ORDER BY txn_time DESC, txn_id DESC LIMIT %s", params + [limit])
    return {
        "items": [_txn_item(r) for r in rows],
        "speech": (f"{len(rows)} giao dịch gần nhất của {c['salutation']}: " +
                   "; ".join(_txn_speech(r) for r in rows) + ".") if rows else "Chưa có giao dịch nào.",
    }


@tool
def search_transactions(customer_id: str, date_from: str, date_to: str, category: str | None = None,
                        keyword: str | None = None, direction: str | None = None, min_amount: int | None = None,
                        limit: int = 10) -> dict:
    """Liệt kê giao dịch cụ thể + tổng số tiền khớp điều kiện."""
    _customer(customer_id)
    a, b = _range(date_from, date_to)
    where = " WHERE customer_id=%s AND txn_time >= %s AND txn_time < %s AND txn_time <= %s"
    params: list = [customer_id, a, b + timedelta(days=1), now()]
    cf, cp = _cat_filter(category)
    where += cf
    params += cp
    if direction in ("in", "out"):
        where += " AND direction=%s"
        params.append(direction)
    if min_amount:
        where += " AND amount >= %s"
        params.append(int(min_amount))
    if keyword:
        kw = f"%{_strip(keyword)}%"
        # nội dung sao kê lưu không dấu -> so khớp với từ khóa đã bỏ dấu
        where += (" AND (lower(description) LIKE %s OR lower(coalesce(counterparty_name,'')) LIKE %s"
                  " OR lower(coalesce(merchant,'')) LIKE %s)")
        params += [kw, kw, kw]
    agg = _q1("""SELECT count(*) AS n, count(*) FILTER (WHERE direction='out') AS n_out,
                        count(*) FILTER (WHERE direction='in') AS n_in,
                        coalesce(sum(amount) FILTER (WHERE direction='out'),0) AS total_out,
                        coalesce(sum(amount) FILTER (WHERE direction='in'),0) AS total_in FROM vb.v_txn""" + where, params)
    rows = _q("SELECT * FROM vb.v_txn" + where + " ORDER BY txn_time DESC, txn_id DESC LIMIT %s",
              params + [max(1, min(int(limit), 50))])
    label = (category or keyword or "").strip()
    # tiền ra và tiền vào tách riêng, không cộng lẫn (vd cho em mượn 20 triệu rồi em trả 20 triệu)
    parts = []
    if agg["n_out"]:
        parts.append(f"chi {vnd_speak(agg['total_out'])} ({agg['n_out']} lần)")
    if agg["n_in"]:
        parts.append(f"nhận {vnd_speak(agg['total_in'])} ({agg['n_in']} lần)")
    speech = (f"{_range_vi(a, b).capitalize()} có {agg['n']} giao dịch" + (f" {label}" if label else "") +
              (": " + ", ".join(parts) if parts else "") + ".")
    if rows and agg["n"] <= 5:
        speech += " Cụ thể: " + "; ".join(_txn_speech(r) for r in rows) + "."
    # total: tổng tiền ra; chỉ khi kết quả toàn là tiền vào thì là tổng tiền vào
    total = agg["total_in"] if agg["n_in"] and not agg["n_out"] else agg["total_out"]
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), "count": agg["n"], "total": total,
            "total_text": vnd_text(total), "total_out": agg["total_out"], "total_out_text": vnd_text(agg["total_out"]),
            "total_in": agg["total_in"], "total_in_text": vnd_text(agg["total_in"]),
            "items": [_txn_item(r) for r in rows], "speech": speech}


# ============================================================ 3. THỐNG KÊ
GROUP_VI = {"needs": "Chi thiết yếu", "wants": "Chi tiêu cá nhân, mua sắm, giải trí"}


def _spending_rows(cid, a: date, b: date):
    return _q("""SELECT category_code, category_name, group_code, sum(amount) AS total, count(*) AS n
                 FROM vb.v_txn WHERE customer_id=%s AND direction='out' AND is_spending
                   AND txn_time >= %s AND txn_time < %s AND txn_time <= %s
                 GROUP BY 1,2,3 ORDER BY total DESC""", (cid, a, b + timedelta(days=1), now()))


def _income_total(cid, a: date, b: date) -> int:
    r = _q1("""SELECT coalesce(sum(amount),0) AS s FROM vb.v_txn WHERE customer_id=%s AND direction='in'
               AND is_income AND txn_time >= %s AND txn_time < %s AND txn_time <= %s""",
            (cid, a, b + timedelta(days=1), now()))
    return int(r["s"])


@tool
def get_spending_summary(customer_id: str, date_from: str, date_to: str, group_by: str = "category",
                         top: int = 5) -> dict:
    """Tổng chi tiêu trong khoảng ngày (không tính gửi tiết kiệm, đầu tư, cho mượn), chia theo nhóm."""
    c = _customer(customer_id)
    a, b = _range(date_from, date_to)
    params = (customer_id, a, b + timedelta(days=1), now())
    if group_by == "category":
        rows = _spending_rows(customer_id, a, b)
        key = "category_name"
    elif group_by == "month":
        rows = _q("""SELECT to_char(date_trunc('month', txn_time), 'YYYY-MM') AS label, sum(amount) AS total,
                            count(*) AS n FROM vb.v_txn WHERE customer_id=%s AND direction='out' AND is_spending
                     AND txn_time >= %s AND txn_time < %s AND txn_time <= %s GROUP BY 1 ORDER BY 1""", params)
        key = "label"
    elif group_by == "merchant":
        rows = _q("""SELECT coalesce(merchant, counterparty_name, category_name) AS label, sum(amount) AS total,
                            count(*) AS n FROM vb.v_txn WHERE customer_id=%s AND direction='out' AND is_spending
                     AND txn_time >= %s AND txn_time < %s AND txn_time <= %s GROUP BY 1 ORDER BY 2 DESC LIMIT 20""",
                  params)
        key = "label"
    elif group_by == "group":
        rows = _q("""SELECT group_code AS label, sum(amount) AS total, count(*) AS n FROM vb.v_txn
                     WHERE customer_id=%s AND direction='out' AND is_spending AND txn_time >= %s AND txn_time < %s
                     AND txn_time <= %s GROUP BY 1 ORDER BY 2 DESC""", params)
        for r in rows:
            r["label"] = GROUP_VI.get(r["label"], r["label"])
        key = "label"
    else:
        raise ToolError("group_by phải là category / month / merchant / group")
    total = sum(r["total"] for r in rows)
    income = _income_total(customer_id, a, b)
    items = [{"label": r[key], "code": r.get("category_code"), "total": r["total"], "total_text": vnd_text(r["total"]),
              "count": r["n"], "share_pct": round(100 * r["total"] / total, 1) if total else 0} for r in rows]
    top_items = items[:max(1, int(top))] if group_by != "month" else items
    speech = f"{_range_vi(a, b).capitalize()}, {c['salutation']} đã chi tổng cộng {vnd_speak(total)}"
    if group_by in ("category", "merchant", "group") and top_items:
        speech += ". Nhiều nhất là " + ", ".join(
            f"{i['label'] if group_by == 'merchant' else i['label'].lower()} {vnd_speak(i['total'])}"
            for i in top_items[:3])
    speech += f". Tổng thu nhập cùng kỳ là {vnd_speak(income)}."
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), "total_spending": total,
            "total_spending_text": vnd_text(total), "total_income": income, "total_income_text": vnd_text(income),
            "net": income - total, "net_text": vnd_text(income - total), "group_by": group_by, "items": top_items,
            "note": "Chi tiêu không gồm gửi tiết kiệm, đầu tư, cho mượn.",
            "speech": speech}


@tool
def get_income_summary(customer_id: str, date_from: str, date_to: str) -> dict:
    c = _customer(customer_id)
    a, b = _range(date_from, date_to)
    rows = _q("""SELECT category_name, category_code, sum(amount) AS total, count(*) AS n FROM vb.v_txn
                 WHERE customer_id=%s AND direction='in' AND is_income AND txn_time >= %s AND txn_time < %s
                 AND txn_time <= %s GROUP BY 1,2 ORDER BY 3 DESC""", (customer_id, a, b + timedelta(days=1), now()))
    total = sum(r["total"] for r in rows)
    items = [{"label": r["category_name"], "code": r["category_code"], "total": r["total"],
              "total_text": vnd_text(r["total"]), "count": r["n"]} for r in rows]
    speech = f"{_range_vi(a, b).capitalize()}, {c['salutation']} nhận tổng cộng {vnd_speak(total)}"
    if items:
        speech += ", gồm " + ", ".join(f"{i['label'].lower()} {vnd_speak(i['total'])}" for i in items[:4])
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), "total_income": total,
            "total_income_text": vnd_text(total), "items": items, "speech": speech + "."}


@tool
def get_month_overview(customer_id: str, month: str | None = None) -> dict:
    """Tổng quan một tháng: thu, chi, còn dư, 3 khoản chi lớn nhất, so với tháng trước. Mặc định tháng này."""
    c = _customer(customer_id)
    m = _month_start(_date(month + "-01" if month and len(month) == 7 else month) if month else today())
    end = min(_next_month(m) - timedelta(days=1), today())
    if m > today():
        raise ToolError("Tháng này chưa tới")
    partial = end < _next_month(m) - timedelta(days=1)
    rows = _spending_rows(customer_id, m, end)
    spend = sum(r["total"] for r in rows)
    income = _income_total(customer_id, m, end)
    pm = _prev_month(m)
    # so sánh công bằng: tháng trước cùng số ngày nếu tháng này chưa hết
    pend = min(pm + timedelta(days=(end - m).days), _next_month(pm) - timedelta(days=1)) if partial else \
        _next_month(pm) - timedelta(days=1)
    prev_spend = sum(r["total"] for r in _spending_rows(customer_id, pm, pend))
    change = round(100 * (spend - prev_spend) / prev_spend, 1) if prev_spend else None
    n_txn = _q1("SELECT count(*) AS n FROM vb.v_txn WHERE customer_id=%s AND txn_time >= %s AND txn_time < %s "
                "AND txn_time <= %s",
                (customer_id, m, end + timedelta(days=1), now()))["n"]
    top3 = [{"label": r["category_name"], "code": r["category_code"], "total": r["total"],
             "total_text": vnd_text(r["total"])} for r in rows[:3]]
    label = f"tháng {m.month}" + (" này" if m == _month_start(today()) else "")
    speech = (f"{label.capitalize()}{' tính đến hôm nay' if partial else ''}, {c['salutation']} nhận "
              f"{vnd_speak(income)} và chi {vnd_speak(spend)}")
    speech += f", còn dư {vnd_speak(income - spend)}" if income >= spend else \
        f", chi nhiều hơn thu {vnd_speak(spend - income)}"
    if top3:
        speech += ". Chi nhiều nhất cho " + ", ".join(f"{t['label'].lower()} {vnd_speak(t['total'])}" for t in top3)
    if change is not None:
        cmp = "cùng kỳ tháng trước" if partial else "tháng trước"
        if abs(change) < 5:
            speech += f". Chi tiêu gần bằng {cmp}"
        else:
            speech += f". So với {cmp}, chi tiêu {'tăng' if change > 0 else 'giảm'} {abs(round(change))} phần trăm"
    return {"month": m.strftime("%Y-%m"), "until": end.isoformat(), "is_partial_month": partial,
            "total_income": income, "total_income_text": vnd_text(income), "total_spending": spend,
            "total_spending_text": vnd_text(spend), "net": income - spend, "net_text": vnd_text(income - spend),
            "top_categories": top3, "prev_month_spending_same_period": prev_spend,
            "spending_change_pct": change, "transaction_count": n_txn, "speech": speech + "."}


@tool
def compare_periods(customer_id: str, a_from: str, a_to: str, b_from: str, b_to: str,
                    category: str | None = None) -> dict:
    """So sánh chi tiêu kỳ A (cũ) với kỳ B (mới), tổng hoặc theo một danh mục."""
    c = _customer(customer_id)
    a1, a2 = _range(a_from, a_to)
    b1, b2 = _range(b_from, b_to)
    codes = resolve_category(category) if category else None
    if category and not codes:
        raise _unknown_category(category)

    def tot(x, y):
        rows = _spending_rows(customer_id, x, y)
        return {r["category_code"]: r for r in rows}

    A, B = tot(a1, a2), tot(b1, b2)
    keys = codes or sorted(set(A) | set(B))
    cats = _category_map()
    items = []
    for k in keys:
        va, vb_ = (A.get(k) or {}).get("total", 0), (B.get(k) or {}).get("total", 0)
        items.append({"code": k, "label": cats[k]["name_vi"], "a": va, "b": vb_, "diff": vb_ - va,
                      "diff_text": vnd_text(vb_ - va), "change_pct": round(100 * (vb_ - va) / va, 1) if va else None})
    items.sort(key=lambda i: -abs(i["diff"]))
    ta, tb = sum(i["a"] for i in items), sum(i["b"] for i in items)
    what = cats[codes[0]]["name_vi"].lower() if codes and len(codes) == 1 else "chi tiêu"
    speech = f"{what.capitalize()} {_range_vi(b1, b2)} là {vnd_speak(tb)}, còn {_range_vi(a1, a2)} là {vnd_speak(ta)}"
    if ta:
        pct = round(100 * (tb - ta) / ta)
        speech += f", {'tăng' if tb > ta else 'giảm'} {abs(pct)} phần trăm" if pct else ", gần như không đổi"
    if not codes:
        movers = [i for i in items if abs(i["diff"]) >= 300_000][:2]
        if movers:
            speech += ". Thay đổi nhiều nhất: " + ", ".join(
                f"{i['label'].lower()} {'tăng' if i['diff'] > 0 else 'giảm'} {vnd_speak(abs(i['diff']))}" for i in movers)
    return {"period_a": [a1.isoformat(), a2.isoformat()], "period_b": [b1.isoformat(), b2.isoformat()],
            "total_a": ta, "total_b": tb, "items": items[:10], "speech": speech + "."}


@tool
def get_category_trend(customer_id: str, category: str, months: int = 6) -> dict:
    """Số tiền theo từng tháng của một khoản (vd tiền điện) trong N tháng gần nhất, kèm trung bình."""
    _customer(customer_id)
    codes = resolve_category(category)
    if not codes:
        raise _unknown_category(category)
    months = max(2, min(int(months), 18))
    end_m = _month_start(today())
    start_m = end_m
    for _ in range(months - 1):
        start_m = _prev_month(start_m)
    rows = _q("""SELECT to_char(date_trunc('month', txn_time),'YYYY-MM') AS m, sum(amount) AS total
                 FROM vb.v_txn WHERE customer_id=%s AND category_code = ANY(%s) AND direction='out'
                 AND txn_time >= %s AND txn_time <= %s GROUP BY 1 ORDER BY 1""", (customer_id, codes, start_m, now()))
    by = {r["m"]: r["total"] for r in rows}
    series = []
    d = start_m
    while d <= end_m:
        k = d.strftime("%Y-%m")
        series.append({"month": k, "total": by.get(k, 0), "total_text": vnd_text(by.get(k, 0))})
        d = _next_month(d)
    prev = [s["total"] for s in series[:-1] if s["total"]]
    avg = int(sum(prev) / len(prev)) if prev else 0
    cur = series[-1]["total"]
    name = _category_map()[codes[0]]["name_vi"].lower() if len(codes) == 1 else category
    partial = today() < _next_month(end_m) - timedelta(days=1)
    speech = f"{name.capitalize()} tháng này{' tính đến hôm nay' if partial else ''} là {vnd_speak(cur)}"
    if avg:
        ratio = cur / avg if avg else 0
        speech += f", trung bình {len(prev)} tháng trước là {vnd_speak(avg)}"
        if ratio >= 1.5:
            speech += f", tức là cao gấp {str(round(ratio, 1)).replace('.', ',')} lần"
        elif ratio <= 0.67 and cur and not partial:   # tháng chưa hết thì chưa kết luận "thấp"
            speech += ", thấp hơn hẳn mọi khi"
    last = max(series[:-1], key=lambda s: s["month"]) if len(series) > 1 else None
    if last:
        speech += f". Tháng trước là {vnd_speak(last['total'])}"
    return {"category": codes, "series": series, "avg_previous": avg, "current": cur,
            "is_partial_month": partial, "speech": speech + "."}


# ============================================================ 4. CẢNH BÁO BẤT THƯỜNG
SCAM_KEYWORDS = ["xac minh", "giai toa", "phong toa", "dieu tra", "cong an", "vien kiem sat", "toa an",
                 "loi nhuan", "hoa hong", "nhan thuong", "trung thuong", "dau tu ung dung", "nap tien dau tu",
                 "rua tien", "ho so vay", "phi giai ngan"]
BILL_CATS = {"electricity", "water", "internet_tv", "telecom", "housing_fee"}


def _scam_hit(text: str | None) -> list[str]:
    t = _strip(text or "")
    return [k for k in SCAM_KEYWORDS if k in t]


def _detect(cid: str, a: date, b: date) -> list[dict]:
    rows = _q("""SELECT * FROM vb.v_txn WHERE customer_id=%s AND txn_time < %s AND txn_time <= %s
                 ORDER BY txn_time, txn_id""", (cid, b + timedelta(days=1), now()))
    saved = {r["account_number"] for r in _q("SELECT account_number FROM vb.beneficiaries WHERE customer_id=%s", (cid,))}
    seen_cp: set = set(saved)
    seen_merchant: set = set()
    hist_cat: dict[str, list] = {}
    atm_hist: list = []
    new_cp_first: dict[str, datetime] = {}
    flagged = []
    prev = None
    recent: list[dict] = []   # cửa sổ 30 phút để bắt trừ trùng
    for r in rows:
        in_window = r["txn_time"].date() >= a
        reasons = []
        cp = r["counterparty_account"]
        if r["direction"] == "out" and in_window:
            amt, hour = r["amount"], r["txn_time"].hour
            known = cp in seen_cp if cp else True
            bal_before = (r["balance_after"] or 0) + amt if r["account_type"] == "payment" else None
            if r["channel"] == "transfer" and cp and not known and amt >= 10_000_000:
                s = f"chuyển {vnd_speak(amt)} cho người nhận chưa từng giao dịch"
                if bal_before and amt >= 0.5 * bal_before:
                    s += f", bằng {round(100 * amt / bal_before)} phần trăm số dư lúc đó"
                reasons.append(s)
            if r["channel"] in ("transfer", "card", "atm", "qr") and (hour >= 22 or hour < 5) and amt >= 1_000_000:
                reasons.append(f"giao dịch {vnd_speak(amt)} lúc {_t_vi(r['txn_time'])}, giờ khuya")
            if r["channel"] == "transfer" and cp and cp in new_cp_first and \
                    r["txn_time"] - new_cp_first[cp] <= timedelta(hours=48) and amt >= 1_000_000:
                reasons.append("chuyển nhiều lần liên tiếp cho cùng một người lạ trong 2 ngày")
            hits = _scam_hit(r["description"]) if r["channel"] == "transfer" else []
            if hits:
                reasons.append("nội dung chuyển khoản giống các vụ lừa đảo thường gặp")
            for p in recent:
                if p["amount"] == amt and p["description"] == r["description"] and p["direction"] == "out" and \
                        r["txn_time"] - p["txn_time"] <= timedelta(minutes=30):
                    reasons.append(f"{(r['category_name'] or 'khoản này').lower()} bị trừ hai lần cùng số tiền "
                                   f"{vnd_speak(amt)}, cách nhau "
                                   f"{max(1, int((r['txn_time'] - p['txn_time']).total_seconds() // 60))} phút")
                    break
            hc = hist_cat.get(r["category_code"], [])
            if r["category_code"] in BILL_CATS and len(hc) >= 3 and not any("trừ hai lần" in x for x in reasons):
                last12 = [h["amount"] for h in hc if r["txn_time"] - h["txn_time"] <= timedelta(days=366)]
                med = statistics.median(last12) if last12 else 0
                if last12 and amt > 1.3 * max(last12) and amt > 1.5 * med:
                    reasons.append(f"{r['category_name'].lower()} {vnd_speak(amt)}, cao bất thường so với mức "
                                   f"thường là khoảng {vnd_speak(med)}")
            if r["category_code"] == "atm_withdraw":
                h180 = [x["amount"] for x in atm_hist if r["txn_time"] - x["txn_time"] <= timedelta(days=180)]
                if h180 and amt >= 10_000_000 and amt >= 3 * statistics.median(h180):
                    reasons.append(f"rút tiền mặt {vnd_speak(amt)}, gấp nhiều lần mức rút thường ngày")
            if r["channel"] == "card" and (hour >= 22 or hour < 5) and r["merchant"] and \
                    r["merchant"] not in seen_merchant and amt >= 500_000 and not reasons:
                reasons.append(f"quẹt thẻ lúc {_t_vi(r['txn_time'])} ở nơi chưa từng giao dịch")
        if reasons:
            n_high = len(reasons) >= 2 or any("lừa đảo" in x or "trừ hai lần" in x for x in reasons)
            flagged.append({**_txn_item(r), "reasons": reasons, "severity": "high" if n_high else "medium",
                            "speech": _cap(f"{_d_vi(r['txn_time'])}, {_t_vi(r['txn_time'])}: {reasons[0]}")})
        # cập nhật lịch sử SAU khi xét
        if r["direction"] == "out" and r["channel"] == "transfer" and cp and cp not in seen_cp and cp not in new_cp_first:
            new_cp_first[cp] = r["txn_time"]
        if cp:
            seen_cp.add(cp)
        if r["merchant"]:
            seen_merchant.add(r["merchant"])
        hist_cat.setdefault(r["category_code"], []).append(r)
        if r["category_code"] == "atm_withdraw":
            atm_hist.append(r)
        recent = [p for p in recent if r["txn_time"] - p["txn_time"] <= timedelta(minutes=30)] + [r]
    return flagged


@tool
def detect_unusual_transactions(customer_id: str, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Rà soát giao dịch bất thường bằng luật (mặc định 30 ngày gần nhất), kèm lý do từng giao dịch."""
    c = _customer(customer_id)
    b = _date(date_to) if date_to else today()
    a = _date(date_from) if date_from else b - timedelta(days=30)
    a, b = _range(a, b)
    items = _detect(customer_id, a, b)
    items.sort(key=lambda x: x["time"], reverse=True)
    if not items:
        speech = f"{_range_vi(a, b).capitalize()}, em không thấy giao dịch nào bất thường."
    else:
        speech = (f"{_range_vi(a, b).capitalize()} có {len(items)} giao dịch cần {c['salutation']} chú ý. " +
                  ". ".join(i["speech"] for i in items[:3]) + ". ")
        if any(i["severity"] == "high" for i in items):
            speech += (f"Nếu {_pronoun(c)} không thực hiện hoặc bị ai đó yêu cầu chuyển tiền, hãy gọi ngay "
                       f"{BANK_HOTLINE} để được hỗ trợ.")
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), "count": len(items), "items": items,
            "speech": speech.strip()}


# ============================================================ 5. NGƯỜI NHẬN
_NAME_TITLES = {"anh", "chi", "em", "chu", "co", "bac", "ong", "ba", "cau", "di", "con", "chau", "thang", "cu", "be",
                "cai", "thay"}


@tool
def list_beneficiaries(customer_id: str) -> dict:
    _customer(customer_id)
    rows = _q("SELECT beneficiary_id, display_name, relationship, bank_name, account_number FROM vb.beneficiaries "
              "WHERE customer_id=%s ORDER BY beneficiary_id", (customer_id,))
    items = [{"beneficiary_id": r["beneficiary_id"], "name": r["display_name"], "relationship": r["relationship"],
              "bank": r["bank_name"], "account_number": _mask(r["account_number"])} for r in rows]
    return {"items": items, "speech": "Danh bạ đã lưu gồm: " +
            ", ".join(f"{i['relationship']} {i['name']}" for i in items) + "." if items else "Chưa lưu người nhận nào."}


@tool
def find_beneficiary(customer_id: str, name: str) -> dict:
    """Tìm người nhận đã lưu theo tên hoặc cách gọi ('vợ', 'con trai', 'mẹ', 'cô Hoa')."""
    _customer(customer_id)
    t = _strip(name)
    t = re.sub(r"^(cho|gui|chuyen cho|chuyen tien cho)\s+", "", t)
    # các cách gọi để thử lần lượt: nguyên văn -> bỏ "tôi/của tôi" -> bỏ từ xưng hô ở đầu ("em Tuấn", "con Khoa")
    no_poss = re.sub(r"\s+(cua toi|cua em|nha minh|toi|minh)$", "", t)
    no_title = no_poss
    while len(no_title.split()) > 1 and no_title.split()[0] in _NAME_TITLES:
        no_title = no_title.split(" ", 1)[1]
    rows = _q("SELECT * FROM vb.beneficiaries WHERE customer_id=%s", (customer_id,))
    keys_of = {r["beneficiary_id"]: [_strip(r["display_name"]), _strip(r["relationship"] or "")] +
               [_strip(x) for x in r["aliases"]] for r in rows}
    hits = []
    for cand in dict.fromkeys([t, no_poss, no_title]):
        hits = [r for r in rows if cand in keys_of[r["beneficiary_id"]]]
        if hits:
            break
    if not hits:
        hits = [r for r in rows if any(len(no_title) >= 2 and (no_title in k.split() or (len(no_title) >= 3 and
                                                                no_title in k)) for k in keys_of[r["beneficiary_id"]])]
    items = [{"beneficiary_id": r["beneficiary_id"], "name": r["display_name"], "relationship": r["relationship"],
              "bank": r["bank_name"], "account_number": _mask(r["account_number"])} for r in hits]
    if len(items) == 1:
        i = items[0]
        speech = f"Người nhận là {i['relationship']} {i['name']}, tài khoản {i['bank']} đuôi {i['account_number'][-4:]}."
    elif items:
        speech = "Có " + str(len(items)) + " người phù hợp: " + ", ".join(f"{i['relationship']} {i['name']}" for i in items) + \
                 ". Cần hỏi lại khách muốn chuyển cho ai."
    else:
        speech = f"Không có '{name}' trong danh bạ đã lưu. Khách sẽ tự nhập số tài khoản trên màn hình chuyển tiền."
    return {"matches": items, "count": len(items), "speech": speech}


# ============================================================ 6. SẢN PHẨM (MOCK)
@tool
def search_products(product_type: str | None = None, term_months: int | None = None) -> dict:
    sql, params = "SELECT * FROM vb.products WHERE TRUE", []
    if product_type in ("savings", "loan"):
        sql += " AND product_type=%s"
        params.append(product_type)
    if term_months:
        sql += " AND (term_months=%s OR term_months IS NULL)"
        params.append(int(term_months))
    rows = _q(sql + " ORDER BY product_type, term_months NULLS LAST, product_code", params)
    items = [{"product_code": r["product_code"], "name": r["name_vi"], "type": r["product_type"],
              "interest_rate_mock": r["interest_rate"], "term_months": r["term_months"], "min_amount": r["min_amount"],
              "max_amount": r["max_amount"], "max_term_months": r["max_term_months"], "channel": r["channel"],
              "description": r["short_desc"]} for r in rows]
    return {"items": items, "disclaimer": "Lãi suất là dữ liệu MOCK phục vụ demo, không phải biểu lãi suất thật.",
            "speech": "; ".join(f"{i['name']} lãi {str(i['interest_rate_mock']).replace('.', ',')} phần trăm một năm"
                                for i in items[:6]) + ". Lãi suất chỉ mang tính tham khảo."}


# ============================================================ 7. KIỂM TRA RỦI RO TRƯỚC KHI MỞ MÀN HÌNH CHUYỂN TIỀN
@tool
def check_transfer_risk(customer_id: str, amount: int, beneficiary_id: int | None = None,
                        note: str | None = None) -> dict:
    """Cảnh báo trước khi chuyển: thiếu số dư, số tiền lớn bất thường, người nhận lạ, giờ khuya, nội dung lừa đảo."""
    c = _customer(customer_id)
    amount = int(amount)
    if amount <= 0:
        raise ToolError("Số tiền phải lớn hơn 0")
    n = now()
    bal = _payment_balance(customer_id)
    reasons, level = [], 0
    insufficient = amount > bal
    if insufficient:
        # thiếu số dư không phải dấu hiệu lừa đảo: nhắc khách, vẫn mở màn hình (app sẽ chặn khi xác nhận)
        reasons.append(f"số dư hiện có {vnd_speak(bal)} không đủ để chuyển {vnd_speak(amount)}")
        level = max(level, 1)
    elif amount >= 0.5 * bal and amount >= 5_000_000:
        reasons.append(f"số tiền này bằng {round(100 * amount / bal)} phần trăm số dư tài khoản")
        level = max(level, 1)
    hist = _q("""SELECT amount FROM vb.v_txn WHERE customer_id=%s AND direction='out' AND channel='transfer'
                 AND txn_time >= %s AND txn_time <= %s""", (customer_id, n - timedelta(days=180), n))
    if hist:
        p90 = sorted(h["amount"] for h in hist)[int(0.9 * (len(hist) - 1))]
        if amount >= 2 * p90 and amount >= 10_000_000:
            reasons.append(f"số tiền lớn hơn nhiều so với các lần chuyển thường ngày (thường dưới {vnd_speak(p90)})")
            level = max(level, 1)
    if beneficiary_id is None:
        if amount >= 10_000_000:
            reasons.append("người nhận chưa có trong danh bạ, cần kiểm tra kỹ tên chủ tài khoản trước khi xác nhận")
            level = max(level, 1)
    else:
        if not _q1("SELECT 1 AS x FROM vb.beneficiaries WHERE beneficiary_id=%s AND customer_id=%s",
                   (beneficiary_id, customer_id)):
            raise ToolError("Người nhận không có trong danh bạ của khách hàng này")
    if n.hour >= 22 or n.hour < 5:
        reasons.append("đang là đêm khuya, kẻ gian thường hối thúc chuyển tiền vào giờ này")
        level = max(level, 1)
    hits = _scam_hit(note)
    if hits:
        reasons.append("nội dung chuyển khoản có từ ngữ hay gặp trong các vụ lừa đảo")
        level = 2
    recent_new = _q("""SELECT count(DISTINCT counterparty_account) AS k FROM vb.v_txn t
                       WHERE customer_id=%s AND direction='out' AND channel='transfer' AND txn_time >= %s
                       AND txn_time <= %s AND counterparty_account IS NOT NULL
                       AND NOT EXISTS (SELECT 1 FROM vb.beneficiaries b WHERE b.customer_id=t.customer_id
                                       AND b.account_number=t.counterparty_account)
                       AND NOT EXISTS (SELECT 1 FROM vb.v_txn o WHERE o.customer_id=t.customer_id
                                       AND o.counterparty_account=t.counterparty_account AND o.txn_time < t.txn_time)""",
                    (customer_id, n - timedelta(hours=24), n))
    if recent_new and recent_new[0]["k"] >= 1 and amount >= 5_000_000:
        reasons.append("trong 24 giờ qua đã chuyển tiền cho người lạ")
        level = max(level, 2)
    lvl = ["low", "medium", "high"][level]
    p = _pronoun(c)
    if lvl == "low":
        speech = ""
    elif lvl == "medium":
        speech = f"Lưu ý: {'; '.join(reasons[:2])}. {p.capitalize()} kiểm tra kỹ thông tin trước khi xác nhận nhé."
    else:
        speech = (f"Cảnh báo: {'; '.join(reasons)}. Ngân hàng, công an hay tòa án không bao giờ yêu cầu chuyển tiền "
                  f"để xác minh. Nếu có ai đang hướng dẫn {p} chuyển tiền qua điện thoại, {p} hãy dừng lại và gọi "
                  f"{BANK_HOTLINE}.")
    return {"risk_level": lvl, "reasons": reasons, "matched_scam_keywords": hits, "insufficient_balance": insufficient,
            "balance": bal, "balance_text": vnd_text(bal), "speech": speech}


# ============================================================ 8. MỞ MÀN HÌNH + ĐIỀN SẴN (KHÔNG THỰC HIỆN GIAO DỊCH)
def _create_action(cid, action_type, screen, prefill, required, risk=None) -> dict:
    aid = "act_" + secrets.token_urlsafe(9)
    n = now()
    _q("""INSERT INTO vb.pending_actions (action_id, customer_id, action_type, screen, prefill, required_user_inputs,
                                          risk, session_id, created_at, updated_at, expires_at)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
       (aid, cid, action_type, screen, json.dumps(prefill, ensure_ascii=False), required,
        json.dumps(risk, ensure_ascii=False) if risk else None, AUDIT_CTX.get().get("session_id"),
        n, n, n + timedelta(minutes=ACTION_TTL_MIN)))
    return {"action_id": aid, "expires_at": (n + timedelta(minutes=ACTION_TTL_MIN)).isoformat(timespec="seconds")}


def _ui_prefill(prefill: dict) -> dict:
    """Bản prefill trả cho LLM: che số tài khoản."""
    p = json.loads(json.dumps(prefill))
    if p.get("beneficiary"):
        p["beneficiary"]["account_number"] = _mask(p["beneficiary"]["account_number"])
    if p.get("source_account"):
        p["source_account"] = _mask(p["source_account"])
    return p


@tool
def open_transfer_screen(customer_id: str, amount: int, beneficiary_id: int | None = None,
                         note: str | None = None, risk_acknowledged: bool = False) -> dict:
    """Mở màn hình CHUYỂN TIỀN và điền sẵn số tiền (và người nhận nếu khách chọn từ danh bạ).
    Không thực hiện giao dịch: khách tự nhập phần còn lại và tự xác nhận OTP/sinh trắc học.
    Rủi ro cao -> KHÔNG mở, trả cảnh báo; chỉ mở khi khách nghe cảnh báo xong vẫn muốn tiếp tục
    (gọi lại với risk_acknowledged=true)."""
    c = _customer(customer_id)
    p = _pronoun(c)
    amount = int(amount)
    if amount < 1_000:
        raise ToolError("Số tiền chuyển tối thiểu là 1.000 đồng")
    if amount > MAX_TRANSFER:
        raise ToolError(f"Số tiền trên {vnd_text(MAX_TRANSFER)} không được điền sẵn qua trợ lý giọng nói, "
                        "khách vui lòng thao tác trực tiếp hoặc ra quầy")
    risk = TOOLS["check_transfer_risk"].__wrapped__(customer_id=customer_id, amount=amount,
                                                     beneficiary_id=beneficiary_id, note=note)
    if risk["risk_level"] == "high" and not risk_acknowledged:
        return {"ui_action": None, "blocked": True, "risk": risk, "executed": False,
                "next_step": "Đọc cảnh báo cho khách. Chỉ gọi lại với risk_acknowledged=true nếu khách nói rõ vẫn muốn "
                             "tiếp tục và không có ai đang hướng dẫn họ chuyển tiền.",
                "speech": risk["speech"] + f" {p.capitalize()} có chắc chắn vẫn muốn tiếp tục không ạ?"}
    prefill: dict = {"amount": amount, "amount_text": vnd_text(amount), "amount_words": vnd_words(amount)}
    required = []
    if beneficiary_id is not None:
        b = _q1("SELECT * FROM vb.beneficiaries WHERE beneficiary_id=%s AND customer_id=%s", (beneficiary_id, customer_id))
        prefill["beneficiary"] = {"beneficiary_id": b["beneficiary_id"], "name": b["display_name"],
                                  "relationship": b["relationship"], "bank": b["bank_name"],
                                  "account_number": b["account_number"]}
        required.append("Kiểm tra lại tên người nhận hiển thị trên màn hình")
    else:
        required += ["Ngân hàng người nhận", "Số tài khoản người nhận", "Kiểm tra tên chủ tài khoản hiện ra"]
    if note:
        prefill["note"] = note[:140]
    else:
        required.append("Nội dung chuyển khoản")
    required.append("Xác nhận giao dịch bằng mã OTP hoặc sinh trắc học")
    act = _create_action(customer_id, "transfer", "transfer", prefill, required, risk)
    who = f" cho {prefill['beneficiary']['relationship']} {prefill['beneficiary']['name']}" if beneficiary_id else ""
    speech = (f"Em đã mở màn hình chuyển tiền{who} và điền sẵn số tiền {vnd_words(amount)}. "
              + (f"{p.capitalize()} vui lòng tự nhập số tài khoản và ngân hàng người nhận, rồi xác nhận bằng mã OTP."
                 if beneficiary_id is None else f"{p.capitalize()} kiểm tra lại tên người nhận rồi xác nhận bằng mã OTP."))
    if risk["risk_level"] == "medium":
        speech = risk["speech"] + " " + speech
    elif risk["risk_level"] == "high":
        speech = "Em vẫn nhắc lại: hãy dừng lại nếu có ai đang hướng dẫn qua điện thoại. " + speech
    return {"ui_action": {"type": "navigate", "screen": "transfer", **act, "prefill": _ui_prefill(prefill),
                          "required_user_inputs": required},
            "risk": risk, "executed": False, "speech": speech}


@tool
def open_savings_screen(customer_id: str, amount: int, term_months: int | None = None) -> dict:
    """Mở màn hình GỬI TIẾT KIỆM ONLINE, điền sẵn số tiền (và kỳ hạn nếu khách đã nói). Không tự mở sổ."""
    c = _customer(customer_id)
    p = _pronoun(c)
    amount = int(amount)
    prods = _q("SELECT * FROM vb.products WHERE product_type='savings' ORDER BY term_months")
    min_amt = min(r["min_amount"] for r in prods)
    if amount < min_amt:
        raise ToolError(f"Số tiền gửi tiết kiệm online tối thiểu là {vnd_text(min_amt)}")
    prod = None
    if term_months:
        prod = next((r for r in prods if r["term_months"] == int(term_months)), None)
        if not prod:
            raise ToolError("Kỳ hạn chưa hỗ trợ. Các kỳ hạn có: " + ", ".join(f"{r['term_months']} tháng" for r in prods))
    bal = _payment_balance(customer_id)
    src = _q1("SELECT account_number FROM vb.accounts WHERE customer_id=%s AND account_type='payment' AND status='active'"
              " LIMIT 1", (customer_id,))
    prefill: dict = {"amount": amount, "amount_text": vnd_text(amount), "amount_words": vnd_words(amount),
                     "source_account": src["account_number"] if src else None}
    required = []
    if prod:
        est = round(amount * float(prod["interest_rate"]) / 100 * prod["term_months"] / 12, -3)
        prefill.update(term_months=prod["term_months"], product_code=prod["product_code"],
                       interest_rate_mock=prod["interest_rate"], estimated_interest=int(est))
    else:
        required.append("Chọn kỳ hạn gửi")
    required += ["Chọn cách nhận lãi và tái tục khi đến hạn", "Xác nhận bằng mã OTP hoặc sinh trắc học"]
    warn = ""
    if amount > bal:
        warn = f"Lưu ý: tài khoản thanh toán hiện có {vnd_speak(bal)}, chưa đủ {vnd_speak(amount)}. "
    act = _create_action(customer_id, "savings", "savings_open", prefill, required,
                         {"insufficient_balance": amount > bal, "balance": bal})
    speech = warn + f"Em đã mở màn hình gửi tiết kiệm và điền sẵn số tiền {vnd_words(amount)}"
    if prod:
        speech += (f", kỳ hạn {prod['term_months']} tháng, lãi suất tham khảo "
                   f"{str(prod['interest_rate']).replace('.', ',')} phần trăm một năm, đến hạn ước nhận khoảng "
                   f"{vnd_speak(prefill['estimated_interest'])} tiền lãi")
    speech += f". {p.capitalize()} " + ("chọn kỳ hạn, " if not prod else "") + "chọn cách nhận lãi rồi xác nhận bằng mã OTP."
    return {"ui_action": {"type": "navigate", "screen": "savings_open", **act, "prefill": _ui_prefill(prefill),
                          "required_user_inputs": required},
            "executed": False, "balance": bal, "speech": speech}


def _annuity(principal: int, rate_pct: float, months: int) -> int:
    r = rate_pct / 100 / 12
    if r == 0:
        return math.ceil(principal / months)
    return int(round(principal * r / (1 - (1 + r) ** -months), -3))


@tool
def open_loan_screen(customer_id: str, amount: int, loan_type: str | None = None,
                     term_months: int | None = None) -> dict:
    """Mở màn hình ĐĂNG KÝ VAY, điền sẵn số tiền (và loại vay/thời hạn nếu có). Chỉ là đăng ký, ngân hàng còn thẩm định."""
    c = _customer(customer_id)
    p = _pronoun(c)
    amount = int(amount)
    prods = {r["product_code"]: r for r in _q("SELECT * FROM vb.products WHERE product_type='loan'")}
    # Khách không nói rõ loại vay ("vay tiền") -> KHÔNG tự chọn sản phẩm, để khách chọn trên màn hình.
    code = (loan_type or "").upper() if (loan_type or "").upper() in prods else None
    if loan_type and not code:
        # cho phép nói tự nhiên: "cầm cố sổ", "mua nhà", "ô tô"; so khớp theo từ ("vay nhanh" không phải "nhà")
        t = f" {_strip(loan_type)} "
        code = next((k for k, kw in [("VAY_CAM_CO_STK", "cam co"), ("VAY_CAM_CO_STK", "so tiet kiem"),
                                      ("VAY_MUA_NHA", "nha"), ("VAY_MUA_OTO", "o to"), ("VAY_MUA_OTO", "oto"),
                                      ("VAY_MUA_OTO", "mua xe"), ("VAY_TIEU_DUNG", "tieu dung"),
                                      ("VAY_TIEU_DUNG", "tin chap")] if f" {kw} " in t), None)
    prod = prods[code] if code else None
    min_amt = prod["min_amount"] if prod else min(r["min_amount"] for r in prods.values())
    max_amt = prod["max_amount"] if prod else max(r["max_amount"] for r in prods.values())
    note = []
    if code == "VAY_CAM_CO_STK":
        sav = _q1("SELECT coalesce(sum(balance),0) AS s FROM vb.accounts WHERE customer_id=%s AND account_type='savings'"
                  " AND status='active'", (customer_id,))["s"]
        max_amt = min(max_amt, int(sav * 0.95))
        note.append(f"Vay cầm cố tối đa 95% giá trị sổ, tức khoảng {vnd_speak(max_amt)}")
    name = prod["name_vi"] if prod else "Khoản vay"
    if amount < min_amt:
        raise ToolError(f"{name} tối thiểu {vnd_text(min_amt)}")
    if amount > max_amt:
        raise ToolError(f"{name} tối đa {vnd_text(max_amt)}")
    prefill: dict = {"amount": amount, "amount_text": vnd_text(amount), "amount_words": vnd_words(amount)}
    required = []
    if prod:
        prefill.update(product_code=code, product_name=prod["name_vi"], interest_rate_mock=prod["interest_rate"])
    else:
        required.append("Chọn loại vay")
    required.append("Mục đích vay")
    if term_months:
        tm = int(term_months)
        max_term = prod["max_term_months"] if prod else max(r["max_term_months"] for r in prods.values())
        if tm < 1 or tm > max_term:
            raise ToolError(f"Thời hạn vay tối đa {max_term} tháng")
        prefill["term_months"] = tm
        if prod:
            prefill["estimated_monthly_payment"] = _annuity(amount, float(prod["interest_rate"]), tm)
    else:
        required.append("Thời hạn vay")
    required += ["Thông tin thu nhập và giấy tờ theo yêu cầu", "Xác nhận đăng ký bằng mã OTP"]
    act = _create_action(customer_id, "loan", "loan_apply", prefill, required, {"notes": note})
    speech = (f"Em đã mở màn hình đăng ký {prod['name_vi'].lower() if prod else 'vay'} "
              f"và điền sẵn số tiền {vnd_words(amount)}")
    if term_months:
        speech += f", thời hạn {term_months} tháng"
        if prod:
            speech += (f", mỗi tháng trả khoảng {vnd_speak(prefill['estimated_monthly_payment'])} theo lãi suất "
                       f"tham khảo {str(prod['interest_rate']).replace('.', ',')} phần trăm một năm")
    todo = (["chọn loại vay"] if not prod else []) + ["điền mục đích vay"] + \
        ([] if term_months else ["thời hạn vay"]) + ["thông tin thu nhập"]
    speech += (f". {p.capitalize()} {', '.join(todo[:-1])} và {todo[-1]}, rồi xác nhận. "
               "Đây mới là bước đăng ký, ngân hàng sẽ thẩm định trước khi duyệt.")
    if prod and prod["channel"] == "branch":
        speech += " Khoản vay này cần hoàn thiện hồ sơ tại chi nhánh."
    return {"ui_action": {"type": "navigate", "screen": "loan_apply", **act, "prefill": _ui_prefill(prefill),
                          "required_user_inputs": required},
            "executed": False, "speech": speech}


@tool
def cancel_pending_action(customer_id: str, action_id: str) -> dict:
    """Hủy thao tác đã chuẩn bị khi khách đổi ý ('thôi không chuyển nữa')."""
    r = _q1("UPDATE vb.pending_actions SET status='cancelled', updated_at=%s WHERE action_id=%s AND customer_id=%s "
            "AND status IN ('created','opened') RETURNING action_id", (now(), action_id, customer_id))
    if not r:
        raise ToolError("Không tìm thấy thao tác đang chờ để hủy")
    return {"ui_action": {"type": "close", "action_id": action_id}, "speech": "Em đã hủy, không có giao dịch nào được thực hiện."}


# ============================================================ API cho giao diện app (không đưa cho LLM)
def get_action_for_ui(customer_id: str, action_id: str) -> dict:
    r = _q1("SELECT * FROM vb.pending_actions WHERE action_id=%s AND customer_id=%s", (action_id, customer_id))
    if not r:
        raise ToolError("Không tìm thấy thao tác")
    if r["status"] in ("created", "opened") and r["expires_at"] < now():
        _q("UPDATE vb.pending_actions SET status='expired', updated_at=%s WHERE action_id=%s", (now(), action_id))
        r["status"] = "expired"
    for k in ("created_at", "updated_at", "expires_at"):
        r[k] = r[k].isoformat(timespec="seconds")
    return r


def update_action_status_for_ui(customer_id: str, action_id: str, status: str) -> dict:
    if status not in ("opened", "submitted", "cancelled"):
        raise ToolError("status phải là opened / submitted / cancelled")
    allowed_from = {"opened": ("created",), "submitted": ("created", "opened"), "cancelled": ("created", "opened")}
    r = _q1("UPDATE vb.pending_actions SET status=%s, updated_at=%s WHERE action_id=%s AND customer_id=%s "
            "AND status = ANY(%s) AND expires_at >= %s RETURNING action_id, status",
            (status, now(), action_id, customer_id, list(allowed_from[status]), now()))
    if not r:
        raise ToolError("Không cập nhật được (sai mã, đã hết hạn hoặc trạng thái không hợp lệ)")
    return r


def get_transactions_for_ui(customer_id: str, limit: int = 30) -> dict:
    rows = _q("SELECT * FROM vb.v_txn WHERE customer_id=%s AND txn_time <= %s "
              "ORDER BY txn_time DESC, txn_id DESC LIMIT %s", (customer_id, now(), max(1, min(int(limit), 200))))
    return {"items": [_txn_item(r) for r in rows]}


def health() -> dict:
    try:
        _q1("SELECT 1 AS ok")
        return {"db": "ok"}
    except Exception as e:  # pragma: no cover
        return {"db": "error", "detail": type(e).__name__}
