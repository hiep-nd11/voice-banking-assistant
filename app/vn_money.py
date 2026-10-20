"""
Xử lý số tiền tiếng Việt cho voice bot. Toàn bộ là luật cố định (không dùng LLM):

- vnd_words(n)      : 1250000 -> "một triệu hai trăm năm mươi nghìn đồng"   (để TTS đọc chính xác)
- vnd_speak(n)      : như trên nhưng làm tròn đến nghìn, dùng khi đọc số liệu thống kê
- vnd_text(n)       : 1250000 -> "1.250.000đ"                               (để hiển thị)
- parse_vnd_amount  : "một triệu rưỡi", "2 củ", "500k", "1tr2", "năm lít" -> số nguyên VND

Lý do tách riêng: STT trả về chữ, LLM rất dễ hiểu sai "một triệu hai" thành 1.000.002 hoặc
"hai trăm năm" thành 205. Số tiền phải do code tính và đọc lại cho khách xác nhận.
"""
from __future__ import annotations

import re
import unicodedata

# ============================================================== số -> chữ
_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_GROUP_UNITS = ["", " nghìn", " triệu", " tỷ"]


def _read_triple(n: int, full: bool) -> str:
    """Đọc số 0..999. full=True: nhóm không đứng đầu -> đọc cả 'không trăm', 'linh'."""
    h, t, u = n // 100, (n // 10) % 10, n % 10
    parts: list[str] = []
    if h or full:
        parts.append(f"{_DIGITS[h]} trăm")
    if t == 0:
        if u and (h or full):
            parts.append("linh")
    elif t == 1:
        parts.append("mười")
    else:
        parts.append(f"{_DIGITS[t]} mươi")
    if u:
        if u == 1 and t >= 2:
            parts.append("mốt")
        elif u == 4 and t >= 2:
            parts.append("tư")
        elif u == 5 and t >= 1:
            parts.append("lăm")
        else:
            parts.append(_DIGITS[u])
    return " ".join(parts)


def read_number(n: int) -> str:
    """Đọc số nguyên không âm thành chữ tiếng Việt."""
    n = int(n)
    if n < 0:
        return "âm " + read_number(-n)
    if n == 0:
        return "không"
    if n >= 1_000_000_000:
        ty, rest = divmod(n, 1_000_000_000)
        head = read_number(ty) + " tỷ"
        if rest == 0:
            return head
        # phần dưới tỷ: đọc đầy đủ như nhóm không đứng đầu
        return head + " " + _read_below_billion(rest, leading=False)
    return _read_below_billion(n, leading=True)


def _read_below_billion(n: int, leading: bool) -> str:
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    out = []
    first = True
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        full = not (first and leading)
        out.append(_read_triple(g, full) + _GROUP_UNITS[i])
        first = False
    return " ".join(out)


def vnd_words(n: int) -> str:
    """Đọc chính xác số tiền: dùng khi xác nhận số tiền giao dịch."""
    return f"{read_number(int(n))} đồng"


def vnd_speak(n: int) -> str:
    """Đọc số tiền thống kê: làm tròn đến nghìn cho gọn (trên 1 triệu)."""
    n = int(round(n))
    if abs(n) >= 1_000_000:
        n = int(round(n / 1000.0)) * 1000
    return vnd_words(n)


def vnd_text(n: int) -> str:
    return f"{int(round(n)):,}đ".replace(",", ".")


# ============================================================== chữ -> số
def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


# Từ chỉ chữ số (so khớp sau khi bỏ dấu để chịu được STT/viết không dấu).
# Lưu ý: bỏ dấu thì "năm" (5) và "nam" trùng nhau; "mười"/"mươi" trùng -> xử lý riêng bằng bản có dấu.
_DIGIT_WORDS = {
    "không": 0, "khong": 0,
    "một": 1, "mot": 1, "mốt": 1, "mot'": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4, "bon": 4, "tư": 4, "tu": 4,
    "năm": 5, "nam": 5, "lăm": 5, "lam": 5, "nhăm": 5, "nham": 5,
    "sáu": 6, "sau": 6,
    "bảy": 7, "bay": 7, "bẩy": 7,
    "tám": 8, "tam": 8,
    "chín": 9, "chin": 9,
}
# chỉ những từ này mới được coi là "đơn vị lẻ" sau chục (21 -> hai mươi mốt, 25 -> hai mươi lăm)
_UNIT_ONLY = {"mốt", "tư", "lăm", "nhăm"}

_BIG_UNITS = {
    "nghìn": 1_000, "nghin": 1_000, "ngàn": 1_000, "ngan": 1_000, "k": 1_000,
    "triệu": 1_000_000, "trieu": 1_000_000, "tr": 1_000_000, "củ": 1_000_000, "cu": 1_000_000,
    "tỷ": 1_000_000_000, "tỉ": 1_000_000_000, "ty": 1_000_000_000, "ti": 1_000_000_000, "tỏi": 1_000_000_000,
    # tiếng lóng: 1 lít / 1 xị = 100 nghìn
    "lít": 100_000, "lit": 100_000, "xị": 100_000, "xi": 100_000,
}
_HUNDRED = {"trăm", "tram"}
_TENS = {"mươi", "muoi"}            # hai mươi = 20 (bản có dấu "mươi")
_TEN = {"mười", "muoi'"}            # mười = 10
_CHUC = {"chục", "chuc"}
_LINH = {"linh", "lẻ", "le"}
_HALF_AFTER = {"rưỡi", "ruoi", "rưởi"}
_HALF_BEFORE = {"nửa", "nua"}
_CURRENCY = {"đồng", "dong", "vnđ", "vnd", "đ", "d", "vn"}

# từ xưng hô / giới từ đứng trước tên người (so khớp không dấu)
_TITLES = {"anh", "chi", "em", "chu", "co", "bac", "ong", "ba", "cau", "di", "mo", "thim", "con", "chau", "thang",
           "cu", "be", "cai", "cho", "gui"}
# số đứng sau các từ này (không kèm đơn vị) là ngày/tháng/lớp..., không phải số tiền: "tiền học tháng 11"
_NOT_MONEY_BEFORE = {"thang", "ngay", "lop", "tuan", "ky", "phong", "tang"}

_NUM_RE = re.compile(r"\d{1,3}(?:[.,\s]\d{3})+(?!\d)|\d+(?:[.,]\d+)?")


def _tokenize(text: str) -> list[tuple[str, object]]:
    """Tách thành token (loại, giá trị). Giữ dấu để phân biệt mười / mươi."""
    t = unicodedata.normalize("NFC", text.lower())
    # "1tr2", "500k", "2củ5" -> chèn khoảng trắng giữa số và chữ
    t = re.sub(r"(\d)([^\d\s.,])", r"\1 \2", t)
    t = re.sub(r"([^\d\s.,])(\d)", r"\1 \2", t)
    tokens: list[tuple[str, object]] = []
    pos = 0
    for m in re.finditer(r"\d{1,3}(?:[.,\s]\d{3})+(?!\d)|\d+(?:[.,]\d+)?|[^\W\d_]+'?|\S", t):
        tok = m.group(0)
        if tok[0].isdigit():
            if re.fullmatch(r"\d{1,3}(?:[.,\s]\d{3})+", tok):
                tokens.append(("num", int(re.sub(r"[.,\s]", "", tok))))
            elif re.fullmatch(r"\d+[.,]\d+", tok):
                tokens.append(("num", float(tok.replace(",", "."))))
            else:
                tokens.append(("num", int(tok)))
            continue
        w = tok
        if w in _HUNDRED:
            tokens.append(("hundred", 100))
        elif w == "mươi":
            tokens.append(("tens", 10))
        elif w == "mười":
            tokens.append(("ten", 10))
        elif w == "muoi":   # không dấu: không phân biệt được -> đoán theo ngữ cảnh khi parse
            tokens.append(("tens_or_ten", 10))
        elif w in _CHUC:
            tokens.append(("chuc", 10))
        elif w in _LINH:
            tokens.append(("linh", 0))
        elif w in _HALF_AFTER:
            tokens.append(("half", 0))
        elif w in _HALF_BEFORE:
            tokens.append(("half_before", 0))
        elif w in _BIG_UNITS:
            tokens.append(("unit", _BIG_UNITS[w]))
        elif w in _DIGIT_WORDS:
            tokens.append(("digit", (_DIGIT_WORDS[w], w in _UNIT_ONLY)))
        elif w in _CURRENCY:
            tokens.append(("currency", 0))
        else:
            tokens.append(("word", w))
        pos = m.end()
    # Tên người trùng chữ số: "anh Nam hai triệu", "chị Ba hai triệu", "ông Tám 2 triệu".
    # Chữ số đứng ngay sau từ xưng hô VÀ tiếp theo là một số khác -> là tên, không phải số tiền.
    # ("anh hai triệu", "chị ba mươi triệu" vẫn là số tiền vì sau đó là đơn vị / "mươi".)
    for i in range(len(tokens) - 2):
        if tokens[i][0] == "word" and _strip_accents(tokens[i][1]) in _TITLES and tokens[i + 1][0] == "digit" \
                and tokens[i + 2][0] in ("digit", "num", "ten", "tens_or_ten"):
            tokens[i + 1] = ("word", "<ten>")
    return tokens


_NUMERIC_KINDS = {"num", "digit", "hundred", "tens", "ten", "tens_or_ten", "chuc", "linh", "half", "half_before",
                  "unit"}


def _runs(tokens):
    """Các đoạn liên tiếp gồm token số (cho phép xen 'đồng'). Bỏ đoạn kiểu 'tháng 11', 'lớp 12' (không có đơn vị)."""
    runs, cur, prev, cur_prev = [], [], None, None

    def close():
        if cur and not (cur_prev in _NOT_MONEY_BEFORE and not any(k == "unit" for k, _ in cur)):
            runs.append(cur)

    for kind, val in tokens:
        if kind in _NUMERIC_KINDS:
            if not cur:
                cur_prev = prev
            cur.append((kind, val))
        elif kind == "currency" and cur:
            cur.append((kind, val))
        else:
            close()
            cur = []
            prev = _strip_accents(val) if kind == "word" else None
    close()
    return runs


def _is_amount_run(run) -> bool:
    kinds = {k for k, _ in run}
    if "unit" in kinds or "num" in kinds:
        return True
    # "một trăm năm mươi" (không đơn vị) vẫn là số; nhưng một chữ "năm" lẻ thì không
    return bool(kinds & {"hundred", "tens", "ten", "chuc"})


class _ParseError(ValueError):
    pass


def _parse_small(seg) -> float:
    """Phần số nhỏ hơn 1000 (hoặc số viết bằng chữ số) trước một đơn vị lớn."""
    if not seg:
        return 0
    nums = [v for k, v in seg if k == "num"]
    if nums:
        if len(seg) == 1:
            return nums[0]
        # "1 trăm", "5 mươi" (STT trộn chữ và số): đổi num thành digit nếu < 10
        seg = [("digit", (v, False)) if k == "num" and isinstance(v, int) and v < 10 else (k, v) for k, v in seg]
        if any(k == "num" for k, _ in seg):
            if [k for k, _ in seg] == ["num", "half"]:   # "1,5 rưỡi" (hiếm) / "2 rưỡi"
                return nums[0] + 0.5
            raise _ParseError("không hiểu cách nói số")
    h = t = 0
    pending = None          # chữ số vừa đọc, chưa biết vai trò
    seen_hundred = seen_tens = seen_linh = False
    for i, (kind, val) in enumerate(seg):
        if kind == "digit":
            d, unit_only = val
            if pending is not None:
                # "hai lăm" = 25, "ba mốt" = 31 (nói tắt). Chỉ nhận khi chữ sau là mốt/tư/lăm/nhăm:
                # "hai ba triệu" thường nghĩa là "hai, ba triệu" (khoảng), không phải 23 triệu -> hỏi lại
                if not unit_only:
                    raise _ParseError("hai chữ số liền nhau, không rõ số tiền")
                t, pending = pending * 10, d
                seen_tens = True
            else:
                pending = d
        elif kind == "hundred":
            h = (pending if pending is not None else 1) * 100
            pending = None
            seen_hundred = True
        elif kind in ("tens", "chuc"):
            if pending is None:
                if kind == "chuc":      # "chục nghìn" = 10 nghìn
                    t = 10
                    seen_tens = True
                    continue
                raise _ParseError("thiếu chữ số trước 'mươi'")
            t, pending = pending * 10, None
            seen_tens = True
        elif kind == "ten":
            t, seen_tens = 10, True
        elif kind == "tens_or_ten":
            if pending is not None:
                t, pending = pending * 10, None
            else:
                t = 10
            seen_tens = True
        elif kind == "linh":
            seen_linh = True
        elif kind == "half":
            # "trăm rưỡi" = +50 ; "hai mươi rưỡi" hiếm -> +5
            if seen_hundred and not seen_tens and pending is None:
                t = 50
                seen_tens = True
            else:
                raise _ParseError("không hiểu 'rưỡi'")
        elif kind == "half_before":
            raise _ParseError("không hiểu 'nửa'")
    u = 0
    if pending is not None:
        if seen_hundred and not seen_tens and not seen_linh:
            # "hai trăm năm" = 250 (cách nói thường ngày); 205 phải nói "hai trăm linh năm"
            t = pending * 10
        else:
            u = pending
    return h + t + u


def _parse_run(run) -> tuple[int, list[str]]:
    """Ghép các đoạn theo đơn vị lớn. Trả về (số tiền, các giả định đã dùng)."""
    notes: list[str] = []
    has_currency = any(k == "currency" for k, _ in run)
    run = [(k, v) for k, v in run if k != "currency"]
    # "nửa triệu"
    if run and run[0][0] == "half_before":
        if len(run) >= 2 and run[1][0] == "unit":
            rest, n2 = _parse_run(run[2:]) if len(run) > 2 else (0, [])
            return int(run[1][1] // 2 + rest), n2
        raise _ParseError("không hiểu 'nửa'")

    total = 0
    section = 0          # giá trị đang tích lũy dưới đơn vị lớn nhất hiện tại
    seg = []
    last_unit = None
    i = 0
    while i < len(run):
        kind, val = run[i]
        if kind == "unit":
            small = _parse_small(seg) if seg else (1 if last_unit is None else 0)
            if not seg and last_unit is not None:
                raise _ParseError("đơn vị lặp")
            if last_unit is not None and val > last_unit:
                # "trăm nghìn tỷ" hoặc "năm trăm nghìn" đã gộp: nhân dồn
                section = (section + small) * val
            else:
                section += small * val
            last_unit = val
            seg = []
            # "rưỡi" ngay sau đơn vị: + nửa đơn vị
            if i + 1 < len(run) and run[i + 1][0] == "half":
                section += val / 2
                i += 1
        else:
            seg.append((kind, val))
        i += 1
    total = section
    if seg:
        tail = _parse_small(seg)
        if last_unit is None:
            if tail < 1000 and not has_currency:
                notes.append(f"Không nghe thấy đơn vị, hiểu là {int(tail)} nghìn đồng")
                total = tail * 1000
            else:
                total = tail
        else:
            # "một triệu hai" = 1.200.000 ; "năm triệu hai lăm" = 5.250.000 ; "1 triệu 250" = 1.250.000
            nd = len(str(int(tail))) if tail >= 1 else 1
            if any(k in ("hundred",) for k, _ in seg) or tail >= 1000:
                # nói đủ "trăm" mà thiếu "nghìn": "hai triệu ba trăm" = 2.300.000
                scale = last_unit / 1000
            else:
                scale = last_unit / (10 ** nd)
            if scale < 1:
                raise _ParseError("phần lẻ không hợp lệ")
            total += tail * scale
            notes.append("Phần số sau đơn vị được hiểu theo cách nói tắt")
    if total != int(total):
        total = round(total)
    return int(total), notes


def parse_vnd_amount(text: str) -> dict:
    """Hiểu số tiền trong câu nói tiếng Việt. Không bao giờ đoán bừa: không chắc thì trả ok=False."""
    if not text or not text.strip():
        return {"ok": False, "reason": "Câu nói trống"}
    try:
        runs = [r for r in _runs(_tokenize(text)) if _is_amount_run(r)]
    except Exception:  # pragma: no cover - phòng lỗi tokenizer
        runs = []
    if not runs:
        return {"ok": False, "reason": "Không tìm thấy số tiền trong câu", "text": text}

    parsed, errors = [], []
    for r in runs:
        try:
            amt, notes = _parse_run(r)
            if amt > 0:
                parsed.append((amt, notes))
        except _ParseError as e:
            errors.append(str(e))
    if not parsed:
        return {"ok": False, "reason": "Không hiểu số tiền: " + "; ".join(errors), "text": text}

    if len(parsed) > 1:
        return {"ok": False, "reason": "Câu có nhiều số tiền, cần hỏi lại khách",
                "candidates": [{"amount": a, "amount_text": vnd_text(a), "words": vnd_words(a)} for a, _ in parsed],
                "text": text}
    amount, notes = parsed[0]
    if amount < 1000:
        return {"ok": False, "reason": f"Số tiền {amount} đồng quá nhỏ, có thể nghe nhầm", "text": text}
    return {
        "ok": True,
        "amount": amount,
        "amount_text": vnd_text(amount),
        "words": vnd_words(amount),
        "assumptions": notes,
        "needs_confirmation": True,
        "speech": f"Số tiền là {vnd_words(amount)}, đúng không ạ?",
    }
