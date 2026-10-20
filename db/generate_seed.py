"""
Sinh dữ liệu MOCK cho Voice Banking Assistant -> db/seed.sql

    python db/generate_seed.py                    # mặc định: 01/05/2025 -> 25/10/2026
    python db/generate_seed.py --end 2026-10-31   # kéo dài đến ngày khác

Toàn bộ là dữ liệu tổng hợp (synthetic), sinh có seed cố định -> chạy lại ra đúng kết quả.
Tên người, số tài khoản, công ty đều là hư cấu. Lãi suất/sản phẩm là MOCK.

Persona
-------
KH0001  Trần Quốc Hưng, 51 tuổi, trưởng phòng kỹ thuật, Hà Nội. Lão thị, ngại thao tác app.  (persona chính)
        ~18 tháng giao dịch: lương, thưởng, cho thuê ki-ốt, tiết kiệm, vay ô tô, hóa đơn,
        học phí 2 con, gửi mẹ, hiếu hỉ, Tết, du lịch, mua sắm, y tế, phạt nguội, hoàn thuế...
        Chi tiêu hằng ngày dày (ăn sáng, ăn trưa, cà phê, cửa hàng tiện lợi, gửi xe, Grab...), ~110-120 giao dịch/tháng.
        Có 7 giao dịch bất thường cài sẵn (is_anomaly_seed) để chấm eval detect_unusual_transactions.
Chỉ có 1 khách hàng (demo cho một cá nhân).
"""
from __future__ import annotations

import argparse
import calendar
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

START = date(2025, 5, 1)
DEFAULT_END = date(2026, 10, 25)

# --------------------------------------------------------------------------- danh mục
# (code, tên, nhóm, chiều, tính là chi tiêu?, tính là thu nhập?, từ khóa)
CATEGORIES = [
    ("salary", "Lương", "income", "in", False, True, "luong,tien luong"),
    ("bonus", "Thưởng", "income", "in", False, True, "thuong,thuong tet,kpi"),
    ("rental_income", "Tiền cho thuê", "income", "in", False, True, "cho thue,tien thue,kiot,ki ot"),
    ("pension", "Lương hưu", "income", "in", False, True, "luong huu,huu tri,bhxh"),
    ("interest", "Lãi tiền gửi", "income", "in", False, True, "lai,tien lai,lai tiet kiem"),
    ("tax_refund", "Hoàn thuế", "income", "in", False, True, "hoan thue,thue tncn"),
    ("family_in", "Gia đình gửi", "income", "in", False, True, "con gui,gia dinh gui"),
    ("other_income", "Thu nhập khác", "income", "in", False, True, "ban do,thu khac"),
    ("transfer_in", "Nhận chuyển khoản", "internal", "in", False, False, "nhan tien,tra no,nhan chuyen khoan"),
    ("refund", "Hoàn tiền", "internal", "in", False, False, "hoan tien"),
    ("savings_withdrawal", "Tất toán tiết kiệm", "internal", "in", False, False, "tat toan,rut so"),

    ("groceries", "Đi chợ, siêu thị", "needs", "out", True, False, "di cho,sieu thi,cho,thuc pham,winmart,aeon"),
    ("dining", "Ăn uống", "wants", "out", True, False, "an uong,an ngoai,an sang,an trua,an toi,nha hang,quan an,bia,lien hoan"),
    ("coffee", "Cà phê, đồ uống", "wants", "out", True, False, "cafe,ca phe,cafe sang,do uong,tra sua,highlands,phuc long"),
    ("electricity", "Tiền điện", "needs", "out", True, False, "tien dien,dien,evn"),
    ("water", "Tiền nước", "needs", "out", True, False, "tien nuoc,nuoc"),
    ("internet_tv", "Internet, truyền hình", "needs", "out", True, False, "internet,mang,wifi,truyen hinh,fpt"),
    ("telecom", "Điện thoại", "needs", "out", True, False, "dien thoai,cuoc dien thoai,viettel,nap tien dien thoai"),
    ("housing_fee", "Phí chung cư, gửi xe", "needs", "out", True, False, "phi chung cu,phi dich vu,gui xe,quan ly"),
    ("gas_cooking", "Gas nấu ăn", "needs", "out", True, False, "gas,ga"),
    ("fuel_transport", "Xăng xe, đi lại", "needs", "out", True, False, "xang,do xang,di lai,grab,taxi,vetc,phi duong"),
    ("car_care", "Bảo dưỡng, sửa xe", "needs", "out", True, False, "bao duong,sua xe,rua xe,gara,lop,dang kiem"),
    ("health", "Y tế, thuốc men", "needs", "out", True, False, "thuoc,y te,kham benh,benh vien,nha khoa,mat kinh"),
    ("education", "Học phí, học thêm", "needs", "out", True, False, "hoc phi,hoc them,truong,hoc"),
    ("insurance", "Bảo hiểm", "needs", "out", True, False, "bao hiem"),
    ("loan_payment", "Trả nợ vay", "needs", "out", True, False, "tra no,tra gop,khoan vay,vay oto"),
    ("family", "Gia đình (vợ, con, bố mẹ)", "needs", "out", True, False, "gia dinh,cho vo,cho con,gui me,bieu bo me"),
    ("taxes_fees", "Thuế, phí, phạt", "needs", "out", True, False, "thue,phi,phat,phat nguoi,le phi"),
    ("shopping", "Mua sắm", "wants", "out", True, False, "mua sam,shopee,lazada,quan ao,dien may,do dung"),
    ("entertainment", "Giải trí, dịch vụ số", "wants", "out", True, False, "netflix,giai tri,google,phim,dich vu so"),
    ("travel", "Du lịch", "wants", "out", True, False, "du lich,khach san,ve may bay,tour"),
    ("gifts_social", "Hiếu hỉ, quà tặng", "wants", "out", True, False, "dam cuoi,mung cuoi,phung vieng,qua,li xi,hieu hi"),
    ("charity", "Từ thiện, ủng hộ", "wants", "out", True, False, "tu thien,ung ho,quy"),
    ("home_repair", "Sửa chữa nhà", "needs", "out", True, False, "sua nha,tho,xay"),
    ("atm_withdraw", "Rút tiền mặt", "needs", "out", True, False, "rut tien,atm,tien mat"),
    ("transfer_out", "Chuyển khoản khác", "wants", "out", True, False, "chuyen khoan,chuyen tien"),
    ("lend_money", "Cho vay, cho mượn", "internal", "out", False, False, "cho muon,cho vay"),
    ("savings_deposit", "Gửi tiết kiệm", "savings", "out", False, False, "gui tiet kiem,mo so"),
    ("investment", "Đầu tư (chứng chỉ quỹ)", "savings", "out", False, False, "dau tu,chung chi quy"),
    ("deposit_refund", "Trả tiền cọc", "internal", "out", False, False, "tra coc,tien coc"),
]

# --------------------------------------------------------------------------- sản phẩm (MOCK)
PRODUCTS = [
    # code, tên, loại, mô tả, lãi %/năm, kỳ hạn, min, max, max_term, kênh
    ("TK_ONLINE_1T", "Tiết kiệm online kỳ hạn 1 tháng", "savings", "Gửi trên app, rút gốc linh hoạt cuối kỳ", 3.0, 1, 1_000_000, None, None, "app"),
    ("TK_ONLINE_3T", "Tiết kiệm online kỳ hạn 3 tháng", "savings", "Gửi trên app, lãi trả cuối kỳ", 3.4, 3, 1_000_000, None, None, "app"),
    ("TK_ONLINE_6T", "Tiết kiệm online kỳ hạn 6 tháng", "savings", "Gửi trên app, lãi trả cuối kỳ", 4.4, 6, 1_000_000, None, None, "app"),
    ("TK_ONLINE_9T", "Tiết kiệm online kỳ hạn 9 tháng", "savings", "Gửi trên app, lãi trả cuối kỳ", 4.5, 9, 1_000_000, None, None, "app"),
    ("TK_ONLINE_12T", "Tiết kiệm online kỳ hạn 12 tháng", "savings", "Gửi trên app, lãi trả cuối kỳ", 5.0, 12, 1_000_000, None, None, "app"),
    ("TK_ONLINE_24T", "Tiết kiệm online kỳ hạn 24 tháng", "savings", "Gửi trên app, lãi trả cuối kỳ", 5.3, 24, 1_000_000, None, None, "app"),
    ("VAY_TIEU_DUNG", "Vay tiêu dùng tín chấp", "loan", "Không cần tài sản bảo đảm, xét duyệt theo thu nhập", 11.5, None, 10_000_000, 300_000_000, 60, "app"),
    ("VAY_CAM_CO_STK", "Vay cầm cố sổ tiết kiệm", "loan", "Vay đến 95% giá trị sổ, giải ngân nhanh", 7.0, None, 5_000_000, 2_000_000_000, 12, "app"),
    ("VAY_MUA_OTO", "Vay mua ô tô", "loan", "Tài sản bảo đảm là chính xe mua", 8.5, None, 100_000_000, 2_000_000_000, 96, "branch"),
    ("VAY_MUA_NHA", "Vay mua nhà, sửa nhà", "loan", "Thế chấp bất động sản", 7.5, None, 100_000_000, 5_000_000_000, 300, "branch"),
]


class Gen:
    def __init__(self, end: date, seed: int):
        self.end = end
        self.r = random.Random(seed)
        self.txns: list[dict] = []
        self.customers: list[dict] = []
        self.accounts: list[dict] = []
        self.beneficiaries: list[dict] = []

    # ------------------------------------------------------------ tiện ích
    def months(self, start: date):
        d = start.replace(day=1)
        while d <= self.end:
            yield d.year, d.month
            d = date(d.year + d.month // 12, d.month % 12 + 1, 1)

    @staticmethod
    def day(y, m, d):
        return date(y, m, min(d, calendar.monthrange(y, m)[1]))

    @staticmethod
    def workday_before(d: date) -> date:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    def at(self, d: date, h1=8, h2=20) -> datetime:
        """Thời điểm ngẫu nhiên trong ngày, từ h1 giờ đến trước h2 giờ."""
        secs = self.r.randint(h1 * 3600, h2 * 3600 - 1)
        return datetime.combine(d, time()) + timedelta(seconds=secs)

    def rnd(self, a, b, step=1000):
        return self.r.randrange(a // step, b // step + 1) * step

    def add(self, acc, ts, amount, direction, channel, cat, desc, cp=None, merchant=None, anomaly=None):
        if ts.date() > self.end or ts.date() < START:
            return
        cp = cp or {}
        self.txns.append(dict(account_id=acc, txn_time=ts, amount=int(amount), direction=direction,
                              channel=channel, description=desc, counterparty_name=cp.get("name"),
                              counterparty_account=cp.get("acc"), counterparty_bank=cp.get("bank"),
                              merchant=merchant, category_code=cat, is_anomaly_seed=anomaly is not None,
                              anomaly_note=anomaly))

    # ------------------------------------------------------------ chung: chi tiêu lặt vặt theo tháng
    def daily_life(self, pay, card, y, m, profile):
        """profile: dict tỉ lệ / tần suất các loại chi tiêu lặt vặt."""
        r = self.r
        dim = calendar.monthrange(y, m)[1]
        for _ in range(profile["market"]):
            d = self.day(y, m, r.randint(1, dim))
            amt = self.rnd(*profile["market_amt"])
            name = r.choice(profile["market_names"])
            self.add(pay, self.at(d, 6, 11), amt, "out", "qr", "groceries", f"QR thanh toan {name}", merchant=name)
        for _ in range(profile["supermarket"]):
            d = self.day(y, m, r.randint(1, dim))
            shop = r.choice(profile["supermarkets"])
            acc, ch = (card, "card") if card and r.random() < 0.6 else (pay, "qr")
            self.add(acc, self.at(d, 9, 21), self.rnd(*profile["super_amt"]), "out", ch, "groceries",
                     f"{'POS' if ch == 'card' else 'QR'} {shop}", merchant=shop)
        for _ in range(profile["cafe"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["cafes"])
            self.add(pay, self.at(d, 7, 17), self.rnd(*profile["cafe_amt"]), "out", "qr", "coffee",
                     f"QR {name}", merchant=name)
        for _ in range(profile["meal"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["restaurants"])
            acc, ch = (card, "card") if card and r.random() < 0.5 else (pay, "qr")
            self.add(acc, self.at(d, 11, 21), self.rnd(*profile["meal_amt"]), "out", ch, "dining",
                     f"{'POS' if ch == 'card' else 'QR'} {name}", merchant=name)
        for _ in range(profile["fuel"]):
            d = self.day(y, m, r.randint(1, dim))
            acc, ch = (card, "card") if card and r.random() < 0.5 else (pay, "qr")
            self.add(acc, self.at(d, 6, 21), self.rnd(*profile["fuel_amt"]), "out", ch, "fuel_transport",
                     f"{'POS' if ch == 'card' else 'QR'} {profile['fuel_name']}", merchant=profile["fuel_name"])
        for _ in range(profile["atm"]):
            d = self.day(y, m, r.randint(1, dim))
            self.add(pay, self.at(d, 8, 20), self.rnd(*profile["atm_amt"], step=500_000), "out", "atm",
                     "atm_withdraw", f"RUT TIEN ATM {profile['atm_place']}", merchant="ATM")
        for _ in range(profile["pharmacy"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["pharmacies"])
            self.add(pay, self.at(d, 8, 20), self.rnd(*profile["pharmacy_amt"]), "out", "qr", "health",
                     f"QR {name}", merchant=name)
        # ăn sáng / ăn trưa ngày đi làm
        workdays = [self.day(y, m, k) for k in range(1, dim + 1) if self.day(y, m, k).weekday() < 5]
        for d in r.sample(workdays, min(len(workdays), profile["breakfast"])):
            name = r.choice(profile["breakfasts"])
            self.add(pay, self.at(d, 6, 8), self.rnd(*profile["breakfast_amt"]), "out", "qr", "dining",
                     f"QR {name}", merchant=name)
        for d in r.sample(workdays, min(len(workdays), profile["lunch"])):
            name = r.choice(profile["lunches"])
            self.add(pay, self.at(d, 11, 13), self.rnd(*profile["lunch_amt"]), "out", "qr", "dining",
                     f"QR {name}", merchant=name)
        for _ in range(profile["convenience"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["conveniences"])
            self.add(pay, self.at(d, 7, 21), self.rnd(*profile["convenience_amt"]), "out", "qr", "groceries",
                     f"QR {name}", merchant=name)
        for _ in range(profile["fruit"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["fruits"])
            self.add(pay, self.at(d, 16, 20), self.rnd(*profile["fruit_amt"]), "out", "qr", "groceries",
                     f"QR {name}", merchant=name)
        for _ in range(profile["parking"]):
            d = self.day(y, m, r.randint(1, dim))
            name = r.choice(profile["parkings"])
            self.add(pay, self.at(d, 8, 20), r.choice(profile["parking_amt"]), "out", "qr", "fuel_transport",
                     f"QR {name}", merchant=name)
        for _ in range(profile["ride"]):
            d = self.day(y, m, r.randint(1, dim))
            acc, ch, desc, merch = (card, "card", "GRAB VIETNAM", "GRAB") if card and r.random() < 0.6 \
                else (pay, "qr", "QR BE GROUP", "BE")
            self.add(acc, self.at(d, 7, 21), self.rnd(*profile["ride_amt"]), "out", ch, "fuel_transport", desc,
                     merchant=merch)
        for _ in range(profile["barber"]):
            d = self.day(y, m, r.randint(1, dim))
            self.add(pay, self.at(d, 8, 19), self.rnd(*profile["barber_amt"], step=10_000), "out", "qr", "shopping",
                     f"QR {profile['barber_name']}", merchant=profile["barber_name"])

    # ================================================================== KH0001
    def persona_hung(self):
        r = self.r
        cid = "KH0001"
        PAY = "TK000101"
        CARD = PAY   # quẹt thẻ ghi nợ (debit) của chính tài khoản thanh toán
        self.customers.append(dict(
            customer_id=cid, full_name="Trần Quốc Hưng", salutation="anh Hưng", date_of_birth=date(1975, 3, 12),
            gender="nam", occupation="Trưởng phòng kỹ thuật, công ty cơ khí", city="Hà Nội", segment="affluent",
            accessibility_needs="Lão thị (mắt kém khi nhìn gần), khó đọc chữ nhỏ trên điện thoại",
            persona_note=("Persona chính. 51 tuổi, vợ là giáo viên, con trai học đại học ở TP.HCM, con gái lớp 11, "
                          "mẹ ở quê Nam Định. Có ki-ốt cho thuê, vay mua ô tô, 2 sổ tiết kiệm (1 sổ sắp đáo hạn "
                          "28/10/2026) mở từ tài khoản thanh toán, thẻ ghi nợ. Ngại thao tác nhiều bước trên app vì mắt kém.")))

        self.accounts += [
            dict(account_id=PAY, customer_id=cid, account_number="108872345601", account_type="payment",
                 nickname="Tài khoản thanh toán", product_code=None, interest_rate=0.1,
                 term_months=None, opened_at=date(2012, 6, 10), maturity_date=None, monthly_payment=None,
                 status="active"),
            dict(parent_account_id=PAY, account_id="TK000102", customer_id=cid, account_number="208872345602", account_type="savings",
                 nickname="Sổ tiết kiệm 12 tháng", product_code="TK_ONLINE_12T",
                 interest_rate=5.0, term_months=12, opened_at=date(2025, 10, 28), maturity_date=date(2026, 10, 28),
                 monthly_payment=None, status="active", fixed_balance=180_000_000),
            dict(parent_account_id=PAY, account_id="TK000103", customer_id=cid, account_number="208872345603", account_type="savings",
                 nickname="Tiết kiệm online 6 tháng", product_code="TK_ONLINE_6T",
                 interest_rate=4.4, term_months=6, opened_at=date(2026, 6, 15), maturity_date=date(2026, 12, 15),
                 monthly_payment=None, status="active", fixed_balance=50_000_000),
            dict(parent_account_id=PAY, account_id="TK000105", customer_id=cid, account_number="308872345605", account_type="loan",
                 nickname="Khoản vay mua ô tô", product_code="VAY_MUA_OTO", interest_rate=8.9,
                 term_months=60, opened_at=date(2024, 6, 15), maturity_date=date(2029, 6, 15),
                 monthly_payment=9_350_000, status="active", fixed_balance=None),
            dict(parent_account_id=PAY, account_id="TK000106", customer_id=cid, account_number="208872345606", account_type="savings",
                 nickname="Sổ tiết kiệm 12 tháng (đã tất toán)", product_code="TK_ONLINE_12T",
                 interest_rate=4.9, term_months=12, opened_at=date(2024, 10, 28), maturity_date=date(2025, 10, 28),
                 monthly_payment=None, status="closed", fixed_balance=0),
            dict(parent_account_id=PAY, account_id="TK000107", customer_id=cid, account_number="208872345607", account_type="savings",
                 nickname="Tiết kiệm online 6 tháng (đã tất toán)", product_code="TK_ONLINE_6T",
                 interest_rate=4.2, term_months=6, opened_at=date(2025, 12, 15), maturity_date=date(2026, 6, 15),
                 monthly_payment=None, status="closed", fixed_balance=0),
        ]

        # --- người nhận quen (cũng là danh bạ đã lưu)
        WIFE = dict(name="LE THI MAI", acc="101876543210", bank="VietinBank")
        SON = dict(name="TRAN MINH KHOA", acc="0071004567890", bank="Vietcombank")
        DAUGHTER = dict(name="TRAN NGOC ANH", acc="101876500321", bank="VietinBank")
        MOTHER = dict(name="PHAM THI LUA", acc="3204205123456", bank="Agribank")
        TEACHER = dict(name="NGUYEN THI HOA", acc="19034567812011", bank="Techcombank")
        BROTHER = dict(name="TRAN QUOC TUAN", acc="0451000234567", bank="Vietcombank")
        BQL = dict(name="BQL CHUNG CU SONG HONG PARK", acc="115000987654", bank="VietinBank")
        TENANT1 = dict(name="NGUYEN VAN TOAN", acc="19033445566018", bank="Techcombank")
        TENANT2 = dict(name="PHAM THI THU", acc="0801123456789", bank="MB")
        EMPLOYER = dict(name="CONG TY CP CO KHI THANH CONG", acc="113000556677", bank="VietinBank")
        UNI = dict(name="TRUONG DH KY THUAT CONG NGHE TP HCM", acc="0601000778899", bank="BIDV")
        SCHOOL = dict(name="TRUONG THPT NGUYEN GIA THIEU", acc="115000223344", bank="VietinBank")
        INSURER = dict(name="CONG TY BAO HIEM NHAN THO AN PHAT", acc="0011004455667", bank="Vietcombank")
        GARAGE = dict(name="GARA OTO HUNG PHAT", acc="19036677889012", bank="Techcombank")
        FUND = dict(name="CONG TY QUAN LY QUY AN THINH", acc="0011009988776", bank="Vietcombank")
        BUILDER = dict(name="NGUYEN VAN LONG", acc="0981234567", bank="MB")       # thợ sửa nhà (người nhận mới, hợp lệ)
        SCAMMER = dict(name="NGUYEN THI HUONG", acc="0398765432", bank="VPBank")  # lừa đảo giả danh
        SCAM_CO = dict(name="CONG TY TNHH DAU TU SO VINA", acc="2223334445556", bank="ACB")
        COLLEAGUES = [dict(name="VU DINH NAM", acc="113000881122", bank="VietinBank"),
                      dict(name="NGUYEN THI THAO", acc="19037788990011", bank="Techcombank"),
                      dict(name="LE MINH DUC", acc="0021000667788", bank="Vietcombank"),
                      dict(name="PHAM VAN QUANG", acc="0961122334", bank="MB")]

        self.beneficiaries += [
            dict(customer_id=cid, display_name="Lê Thị Mai", relationship="vợ", aliases=["vợ", "bà xã", "mai", "nhà tôi"], **_acc(WIFE)),
            dict(customer_id=cid, display_name="Trần Minh Khoa", relationship="con trai", aliases=["con trai", "khoa", "thằng khoa", "cu khoa"], **_acc(SON)),
            dict(customer_id=cid, display_name="Trần Ngọc Anh", relationship="con gái", aliases=["con gái", "ngọc anh", "bé anh", "cái anh"], **_acc(DAUGHTER)),
            dict(customer_id=cid, display_name="Phạm Thị Lụa", relationship="mẹ", aliases=["mẹ", "bà nội", "mẹ ở quê"], **_acc(MOTHER)),
            dict(customer_id=cid, display_name="Trần Quốc Tuấn", relationship="em trai", aliases=["em trai", "tuấn", "chú tuấn"], **_acc(BROTHER)),
            dict(customer_id=cid, display_name="Nguyễn Thị Hoa", relationship="cô giáo dạy thêm", aliases=["cô hoa", "cô giáo", "tiền học thêm"], **_acc(TEACHER)),
            dict(customer_id=cid, display_name="BQL chung cư Sông Hồng Park", relationship="phí chung cư", aliases=["chung cư", "ban quản lý", "phí chung cư"], **_acc(BQL)),
        ]

        profile = dict(
            market=4, market_amt=(50_000, 250_000), market_names=["CHO NGOC LAM", "HANG RAU CO THAO", "THIT LON MINH HANG"],
            supermarket=3, super_amt=(300_000, 1_100_000), supermarkets=["WINMART LONG BIEN", "GO LONG BIEN", "AEON MALL LONG BIEN"],
            cafe=12, cafe_amt=(35_000, 75_000), cafes=["HIGHLANDS COFFEE", "CAFE GIANG", "CONG CAPHE", "PHUC LONG", "CAFE MOC THANH CONG"],
            meal=4, meal_amt=(150_000, 900_000), restaurants=["NHA HANG LAU NAM", "PHO THIN", "BUN CHA HUONG LIEN", "BIA HOI HA NOI", "NHA HANG SEN"],
            fuel=3, fuel_amt=(500_000, 900_000), fuel_name="PETROLIMEX CH 36",
            atm=1, atm_amt=(1_000_000, 2_000_000), atm_place="NGOC LAM LONG BIEN",
            pharmacy=1, pharmacy_amt=(120_000, 680_000), pharmacies=["NHA THUOC LONG CHAU", "PHARMACITY"],
            breakfast=16, breakfast_amt=(30_000, 65_000),
            breakfasts=["PHO GA NGOC LAM", "BUN RIEU CO HUONG", "XOI YEN", "BANH MI MINH NHAT", "BANH CUON BA HOANH", "PHO BO GIA TRUYEN"],
            lunch=12, lunch_amt=(45_000, 95_000),
            lunches=["COM VAN PHONG THANH CONG", "BUN CHA HANG QUAT", "COM RANG DUONG LANG", "PHO 10 LY QUOC SU", "BUN BO NAM BO"],
            convenience=8, convenience_amt=(18_000, 160_000),
            conveniences=["CIRCLE K NGOC LAM", "WINMART+ NGUYEN VAN CU", "FAMILYMART LONG BIEN", "BACH HOA XANH LONG BIEN"],
            fruit=3, fruit_amt=(90_000, 350_000), fruits=["HOA QUA SACH CLEVERFOOD", "TRAI CAY THANH HA", "BANH NGOT ANH HOA"],
            parking=4, parking_amt=[25_000, 30_000, 40_000, 50_000],
            parkings=["BAI DO XE TRAN HUNG DAO", "VINCOM BA TRIEU PARKING", "BAI XE BV BACH MAI", "IPARKING HA NOI"],
            ride=2, ride_amt=(45_000, 190_000),
            barber=1, barber_amt=(80_000, 120_000), barber_name="CAT TOC NAM HUNG LONG BIEN",
        )

        elec_base = {1: 980_000, 2: 920_000, 3: 1_050_000, 4: 1_350_000, 5: 1_900_000, 6: 2_550_000, 7: 2_800_000,
                     8: 2_700_000, 9: 2_150_000, 10: 1_450_000, 11: 1_080_000, 12: 1_020_000}
        loan_no = 11  # kỳ trả góp của tháng 5/2025

        for y, m in self.months(START):
            prev_m = 12 if m == 1 else m - 1
            prev_y = y - 1 if m == 1 else y
            dim = calendar.monthrange(y, m)[1]
            # ------------------------------------------------ THU
            salary = 52_000_000 if (y, m) < (2026, 1) else 56_000_000
            d = self.workday_before(self.day(y, m, 5))
            self.add(PAY, datetime.combine(d, time(9, r.randint(5, 50))), salary, "in", "salary", "salary",
                     f"{EMPLOYER['name']} TRA LUONG T{prev_m}/{prev_y}", EMPLOYER)
            # tiền thuê ki-ốt
            if (y, m) <= (2026, 6):
                d = self.day(y, m, r.randint(1, 4))
                self.add(PAY, self.at(d, 8, 21), 6_500_000, "in", "transfer", "rental_income",
                         f"{TENANT1['name']} chuyen tien thue kiot thang {m}", TENANT1)
            else:
                d = self.day(y, m, r.randint(2, 5))
                self.add(PAY, self.at(d, 8, 21), 7_000_000, "in", "transfer", "rental_income",
                         f"{TENANT2['name']} tien thue kiot T{m}", TENANT2)
            # lãi không kỳ hạn cuối tháng
            self.add(PAY, datetime.combine(self.day(y, m, dim), time(23, 50)), self.rnd(6_000, 24_000, 1), "in",
                     "interest", "interest", "TRA LAI TIEN GUI KHONG KY HAN")

            # ------------------------------------------------ CHI CỐ ĐỊNH
            d = self.day(y, m, 3)
            self.add(PAY, self.at(d, 19, 22), 4_000_000, "out", "transfer", "family",
                     f"TRAN QUOC HUNG gui con tien sinh hoat thang {m}", SON)
            d = self.day(y, m, 6)
            self.add(PAY, self.at(d, 10, 21), 6_000_000, "out", "transfer", "family",
                     f"TRAN QUOC HUNG chuyen tien chi tieu gia dinh T{m}", WIFE)
            d = self.day(y, m, 10)
            self.add(PAY, self.at(d, 8, 20), 3_000_000, "out", "transfer", "family",
                     f"TRAN QUOC HUNG gui me tien thang {m}", MOTHER)
            d = self.day(y, m, 8)
            self.add(PAY, self.at(d, 9, 20), 2_080_000, "out", "transfer", "housing_fee",
                     f"Phi dich vu can ho B1205 va gui xe oto T{m}", BQL)
            d = self.day(y, m, 15)
            self.add(PAY, datetime.combine(d, time(6, 2)), 9_350_000, "out", "auto_debit", "loan_payment",
                     f"TRICH NO KHOAN VAY OTO 308872345605 KY {loan_no}")
            loan_no += 1
            # học thêm con gái (nghỉ tháng 7)
            if m != 7:
                d = self.day(y, m, 28)
                self.add(PAY, self.at(d, 18, 22), 2_400_000, "out", "transfer", "education",
                         f"Hoc phi hoc them Toan Ly thang {m} chau Ngoc Anh", TEACHER)
            # điện
            elec = int(elec_base[m] * r.uniform(0.92, 1.08))
            d = self.day(y, m, r.randint(18, 21))
            if (y, m) == (2026, 10):
                elec = 4_180_000   # ANOMALY: tăng vọt bất thường
                self.add(PAY, datetime.combine(date(2026, 10, 19), time(9, 14)), elec, "out", "bill", "electricity",
                         "THANH TOAN TIEN DIEN T10/2026 MA KH PD13000123456", merchant="EVN HA NOI",
                         anomaly="Tiền điện tháng 10 gấp gần 3 lần các tháng mùa thu trước đó")
            else:
                ts = datetime.combine(d, time(9, r.randint(0, 59)))
                self.add(PAY, ts, elec, "out", "bill", "electricity",
                         f"THANH TOAN TIEN DIEN T{m}/{y} MA KH PD13000123456", merchant="EVN HA NOI")
                if (y, m) == (2026, 9):  # ANOMALY: bị trừ trùng
                    self.add(PAY, ts + timedelta(minutes=3), elec, "out", "bill", "electricity",
                             f"THANH TOAN TIEN DIEN T{m}/{y} MA KH PD13000123456", merchant="EVN HA NOI",
                             anomaly="Tiền điện tháng 9 bị trừ hai lần cùng số tiền, cách nhau 3 phút")
            d = self.day(y, m, r.randint(18, 22))
            self.add(PAY, self.at(d, 8, 20), self.rnd(190_000, 290_000, 10), "out", "bill", "water",
                     f"THANH TOAN TIEN NUOC T{m}/{y} MA KH 2501234567", merchant="NUOC SACH HA NOI")
            self.add(PAY, datetime.combine(self.day(y, m, 12), time(7, 30)), 285_000, "out", "auto_debit",
                     "internet_tv", f"FPT TELECOM THANH TOAN CUOC INTERNET TRUYEN HINH T{m}", merchant="FPT TELECOM")
            self.add(PAY, self.at(self.day(y, m, 11), 8, 20), self.rnd(290_000, 420_000), "out", "bill", "telecom",
                     f"THANH TOAN CUOC VIETTEL TRA SAU 0912xxx678 T{prev_m}", merchant="VIETTEL")
            self.add(PAY, self.at(self.day(y, m, r.randint(1, 9)), 8, 20), 500_000, "out", "qr", "fuel_transport",
                     "NAP TIEN TAI KHOAN GIAO THONG VETC", merchant="VETC")
            if m % 2 == 0 or r.random() < 0.3:
                self.add(PAY, self.at(self.day(y, m, r.randint(1, dim)), 8, 19), 480_000, "out", "qr",
                         "gas_cooking", "QR GAS PETROLIMEX LONG BIEN", merchant="GAS PETROLIMEX")
            self.add(PAY, self.at(self.day(y, m, r.randint(1, dim)), 8, 18), self.rnd(100_000, 150_000, 10_000),
                     "out", "qr", "car_care", "QR RUA XE OTO MINH TRI", merchant="RUA XE MINH TRI")
            # đầu tư định kỳ từ 2026
            if (y, m) >= (2026, 1):
                self.add(PAY, self.at(self.day(y, m, 7), 9, 17), 2_000_000, "out", "transfer", "investment",
                         "MUA CHUNG CHI QUY AN THINH DINH KY", FUND)
            # dịch vụ số trên thẻ
            if (y, m) >= (2025, 11):
                self.add(CARD, datetime.combine(self.day(y, m, 2), time(4, 0)) + timedelta(minutes=r.randint(0, 40)),
                         260_000, "out", "card", "entertainment", "NETFLIX.COM SINGAPORE", merchant="NETFLIX")
            self.add(CARD, self.at(self.day(y, m, 16), 8, 18), 45_000, "out", "card", "entertainment",
                     "GOOGLE *GOOGLE ONE", merchant="GOOGLE ONE")

            # ------------------------------------------------ CHI LẶT VẶT
            self.daily_life(PAY, CARD, y, m, profile)
            for _ in range(r.choice([1, 1, 2, 3])):          # mua online
                d = self.day(y, m, r.randint(1, dim))
                if r.random() < 0.6:
                    self.add(CARD, self.at(d, 9, 22), self.rnd(150_000, 1_200_000), "out", "card", "shopping",
                             "SHOPEE VN", merchant="SHOPEE")
                else:
                    self.add(PAY, self.at(d, 9, 22), self.rnd(120_000, 900_000), "out", "qr", "shopping",
                             "QR LAZADA VN", merchant="LAZADA")
            # tiền tiêu vặt con gái, đưa thêm vợ, con trai xin thêm
            for _ in range(r.randint(2, 3)):
                self.add(PAY, self.at(self.day(y, m, r.randint(1, dim)), 7, 21), r.choice([100_000, 200_000, 300_000, 500_000]),
                         "out", "transfer", "family", r.choice(["Bo cho con tien tieu vat", "Bo gui Ngoc Anh an sang",
                                                              "Bo cho con tien mua sach"]), DAUGHTER)
            if r.random() < 0.7:
                self.add(PAY, self.at(self.day(y, m, r.randint(12, dim)), 9, 21), r.choice([1_000_000, 1_500_000, 2_000_000]),
                         "out", "transfer", "family", "TRAN QUOC HUNG chuyen em mua do", WIFE)
            if r.random() < 0.3:
                self.add(PAY, self.at(self.day(y, m, r.randint(15, dim)), 19, 22), r.choice([500_000, 1_000_000]),
                         "out", "transfer", "family", "Bo gui them con tien tieu", SON)
            # nạp tiền điện thoại cho mẹ
            self.add(PAY, self.at(self.day(y, m, r.randint(1, 6)), 8, 20), r.choice([100_000, 100_000, 200_000]),
                     "out", "qr", "telecom", "NAP TIEN DIEN THOAI VINAPHONE 0915xxx246", merchant="VINAPHONE")
            # liên hoan với đồng nghiệp: góp tiền / được trả lại
            for _ in range(r.randint(1, 3)):
                who = r.choice(COLLEAGUES)
                d = self.day(y, m, r.randint(1, dim))
                if r.random() < 0.55:
                    self.add(PAY, self.at(d, 12, 21), self.rnd(150_000, 600_000, 10_000), "out", "transfer", "dining",
                             r.choice(["TRAN QUOC HUNG gop tien an trua", "gop lien hoan phong ky thuat",
                                       "Hung gui tien an toi"]), who)
                else:
                    self.add(PAY, self.at(d, 12, 21), self.rnd(150_000, 800_000, 10_000), "in", "transfer", "transfer_in",
                             r.choice(["tra anh Hung tien an", "chuyen tra tien lien hoan", "gui lai anh Hung tien bia"]), who)
            # thỉnh thoảng đi xem phim / mua sách
            if r.random() < 0.3:
                self.add(CARD, self.at(self.day(y, m, r.randint(1, dim)), 18, 21), self.rnd(180_000, 420_000, 10_000),
                         "out", "card", "entertainment", "CGV VINCOM LONG BIEN", merchant="CGV")
            if r.random() < 0.3:
                self.add(PAY, self.at(self.day(y, m, r.randint(1, dim)), 9, 20), self.rnd(120_000, 450_000),
                         "out", "qr", "shopping", "QR NHA SACH TIEN PHONG", merchant="NHA SACH TIEN PHONG")
            # hiếu hỉ: mùa cưới nhiều hơn
            n_wed = 2 if m in (10, 11, 12, 3, 4) else (1 if r.random() < 0.5 else 0)
            for _ in range(n_wed):
                d = self.day(y, m, r.randint(1, dim))
                who = r.choice(["DO VAN THANG", "VU THI HANH", "PHAM DUC MANH", "NGO THI LAN", "BUI QUANG HUY",
                                "TRINH VAN KHAI", "DANG THU TRANG", "HOANG MINH DUC"])
                acct = str(r.randint(10**9, 10**10 - 1))
                self.add(PAY, self.at(d, 9, 21), r.choice([500_000, 500_000, 1_000_000, 1_000_000, 2_000_000]),
                         "out", "transfer", "gifts_social", f"TRAN QUOC HUNG mung dam cuoi",
                         dict(name=who, acc=acct, bank=r.choice(["Vietcombank", "BIDV", "Techcombank", "MB"])))
            if r.random() < 0.25:
                d = self.day(y, m, r.randint(1, dim))
                acct = str(r.randint(10**9, 10**10 - 1))
                self.add(PAY, self.at(d, 8, 20), r.choice([500_000, 1_000_000]), "out", "transfer", "gifts_social",
                         "TRAN QUOC HUNG kinh vieng", dict(name="GIA DINH ONG NGUYEN VAN TAM", acc=acct, bank="Agribank"))

        # ------------------------------------------------ SỰ KIỆN MỘT LẦN / THEO MÙA
        E = []   # (ngày, giờ, phút, acc, amount, dir, channel, cat, desc, cp, merchant)
        E += [
            # học phí con trai đại học
            (date(2025, 8, 25), 10, 15, PAY, 18_500_000, "out", "transfer", "education", "Nop hoc phi HK1 2025-2026 SV TRAN MINH KHOA MSSV 22110456", UNI, None),
            (date(2026, 1, 20), 10, 40, PAY, 18_500_000, "out", "transfer", "education", "Nop hoc phi HK2 2025-2026 SV TRAN MINH KHOA MSSV 22110456", UNI, None),
            (date(2026, 8, 24), 9, 30, PAY, 19_800_000, "out", "transfer", "education", "Nop hoc phi HK1 2026-2027 SV TRAN MINH KHOA MSSV 22110456", UNI, None),
            # học phí + quỹ lớp con gái
            (date(2025, 9, 8), 19, 20, PAY, 3_200_000, "out", "transfer", "education", "Nop hoc phi va quy lop 11A3 HK1 Tran Ngoc Anh", SCHOOL, None),
            (date(2026, 1, 12), 19, 5, PAY, 1_600_000, "out", "transfer", "education", "Nop hoc phi HK2 lop 11A3 Tran Ngoc Anh", SCHOOL, None),
            (date(2026, 9, 7), 20, 10, PAY, 3_500_000, "out", "transfer", "education", "Nop hoc phi va quy lop 12A3 HK1 Tran Ngoc Anh", SCHOOL, None),
            # bảo hiểm
            (date(2025, 8, 8), 10, 5, PAY, 18_600_000, "out", "transfer", "insurance", "Dong phi bao hiem nhan thu HD AP-2019-556677 nam 7", INSURER, None),
            (date(2026, 8, 7), 10, 25, PAY, 18_600_000, "out", "transfer", "insurance", "Dong phi bao hiem nhan thu HD AP-2019-556677 nam 8", INSURER, None),
            (date(2026, 3, 12), 15, 0, CARD, 7_450_000, "out", "card", "insurance", "BAO HIEM VAT CHAT XE OTO 30H-123.45", None, "BAO HIEM PTI"),
            # thưởng, hoàn thuế, thu khác
            (date(2025, 7, 15), 14, 0, PAY, 5_000_000, "in", "salary", "bonus", f"{EMPLOYER['name']} THUONG KPI 6 THANG DAU NAM 2025", EMPLOYER, None),
            (date(2025, 8, 29), 15, 30, PAY, 2_000_000, "in", "salary", "bonus", f"{EMPLOYER['name']} THUONG LE 2/9", EMPLOYER, None),
            (date(2026, 2, 10), 9, 30, PAY, 42_000_000, "in", "salary", "bonus", f"{EMPLOYER['name']} THUONG TET BINH NGO 2026", EMPLOYER, None),
            (date(2026, 7, 15), 14, 10, PAY, 6_000_000, "in", "salary", "bonus", f"{EMPLOYER['name']} THUONG KPI 6 THANG DAU NAM 2026", EMPLOYER, None),
            (date(2026, 5, 20), 10, 45, PAY, 3_240_000, "in", "transfer", "tax_refund", "KHO BAC NHA NUOC HOAN THUE TNCN NAM 2025 MST 8012345678", dict(name="KHO BAC NHA NUOC HA NOI", acc="3949", bank="VietinBank"), None),
            (date(2025, 9, 20), 16, 0, PAY, 12_000_000, "in", "transfer", "other_income", "LE VAN BINH chuyen tien mua xe may Air Blade cu", dict(name="LE VAN BINH", acc="0912000111", bank="MB"), None),
            # em trai mượn tiền rồi trả
            (date(2025, 11, 20), 20, 15, PAY, 20_000_000, "out", "transfer", "lend_money", "TRAN QUOC HUNG cho chu Tuan muon tien", BROTHER, None),
            (date(2026, 3, 25), 19, 40, PAY, 20_000_000, "in", "transfer", "transfer_in", "TRAN QUOC TUAN tra anh Hung tien muon", BROTHER, None),
            # ki-ốt đổi người thuê: trả cọc người cũ, nhận cọc người mới
            (date(2026, 6, 30), 16, 30, PAY, 13_000_000, "out", "transfer", "deposit_refund", "Tra lai tien coc thue kiot", TENANT1, None),
            (date(2026, 7, 1), 11, 0, PAY, 14_000_000, "in", "transfer", "transfer_in", "PHAM THI THU dat coc thue kiot 2 thang", TENANT2, None),
            # sửa nhà (người nhận mới, số tiền lớn nhưng HỢP LỆ - ca khó cho bộ phát hiện)
            (date(2026, 4, 18), 10, 20, PAY, 25_000_000, "out", "transfer", "home_repair", "Thanh toan tien sua bep va thay ong nuoc can ho B1205", BUILDER, None),
            # xe
            (date(2025, 7, 20), 9, 30, PAY, 4_200_000, "out", "transfer", "car_care", "Thanh toan bao duong xe 30H-12345 moc 40000km", GARAGE, None),
            (date(2026, 1, 18), 10, 0, PAY, 3_600_000, "out", "transfer", "car_care", "Thanh toan bao duong xe 30H-12345 moc 50000km", GARAGE, None),
            (date(2026, 7, 25), 15, 10, CARD, 5_800_000, "out", "card", "car_care", "POS GARA OTO HUNG PHAT THAY LOP", None, "GARA OTO HUNG PHAT"),
            (date(2026, 6, 19), 8, 40, PAY, 340_000, "out", "qr", "car_care", "QR PHI DANG KIEM XE CO GIOI 29-07D", None, "TRUNG TAM DANG KIEM 29-07D"),
            (date(2026, 4, 2), 10, 10, PAY, 800_000, "out", "bill", "taxes_fees", "NOP PHAT VI PHAM GIAO THONG BIEN 30H-12345 QUA DVC", None, "CONG DICH VU CONG QUOC GIA"),
            (date(2025, 12, 10), 9, 30, PAY, 410_000, "out", "bill", "taxes_fees", "NOP THUE SU DUNG DAT PHI NONG NGHIEP NAM 2025", None, "CONG DICH VU CONG QUOC GIA"),
            # y tế
            (date(2025, 9, 14), 16, 0, PAY, 2_200_000, "out", "qr", "health", "QR MAT KINH SAI GON CAT KINH DOC SACH", None, "MAT KINH SAI GON"),
            (date(2025, 11, 15), 11, 30, CARD, 2_850_000, "out", "card", "health", "POS BENH VIEN DA KHOA HONG PHUC KHAM SUC KHOE", None, "BENH VIEN DA KHOA HONG PHUC"),
            (date(2026, 3, 8), 17, 20, PAY, 1_500_000, "out", "qr", "health", "QR NHA KHOA KIM LAM RANG", None, "NHA KHOA KIM"),
            # mua sắm lớn trên thẻ
            (date(2025, 6, 14), 18, 30, CARD, 13_490_000, "out", "card", "shopping", "POS DIEN MAY XANH LONG BIEN DIEU HOA", None, "DIEN MAY XANH"),
            (date(2025, 8, 16), 19, 0, CARD, 4_500_000, "out", "card", "gifts_social", "POS PNJ AEON LONG BIEN QUA SINH NHAT VO", None, "PNJ"),
            (date(2026, 9, 2), 17, 45, CARD, 8_990_000, "out", "card", "shopping", "POS THE GIOI DI DONG DIEN THOAI CHO CON", None, "THE GIOI DI DONG"),
            # du lịch
            (date(2025, 7, 12), 21, 0, CARD, 4_800_000, "out", "card", "travel", "AGODA.COM KHACH SAN SAM SON", None, "AGODA"),
            (date(2026, 5, 10), 20, 30, CARD, 12_600_000, "out", "card", "travel", "VIETNAM AIRLINES VE HN-DN 4 NGUOI", None, "VIETNAM AIRLINES"),
            (date(2026, 6, 21), 14, 20, CARD, 7_900_000, "out", "card", "travel", "POS KHACH SAN MUONG THANH DA NANG", None, "MUONG THANH DA NANG"),
            (date(2026, 6, 22), 19, 10, CARD, 1_850_000, "out", "card", "dining", "POS NHA HANG HAI SAN BE MAN DA NANG", None, "HAI SAN BE MAN"),
            (date(2026, 6, 23), 9, 30, CARD, 2_400_000, "out", "card", "travel", "POS SUN WORLD BA NA HILLS", None, "SUN WORLD BA NA"),
            # Tết Bính Ngọ (17/02/2026)
            (date(2026, 2, 11), 10, 0, PAY, 5_000_000, "out", "atm", "atm_withdraw", "RUT TIEN ATM NGOC LAM LONG BIEN", None, "ATM"),
            (date(2026, 2, 12), 9, 20, PAY, 5_000_000, "out", "atm", "atm_withdraw", "RUT TIEN ATM NGOC LAM LONG BIEN", None, "ATM"),
            (date(2026, 2, 12), 20, 0, PAY, 5_000_000, "out", "transfer", "family", "TRAN QUOC HUNG bieu me an Tet", MOTHER, None),
            (date(2026, 2, 13), 15, 0, CARD, 3_650_000, "out", "card", "shopping", "POS GO LONG BIEN MUA SAM TET", None, "GO LONG BIEN"),
            (date(2026, 2, 9), 16, 30, PAY, 2_500_000, "out", "qr", "gifts_social", "QR HOP QUA TET BIBICA", None, "CUA HANG QUA TET HA THANH"),
            # từ thiện
            (date(2025, 9, 12), 12, 0, PAY, 1_000_000, "out", "transfer", "charity", "UNG HO DONG BAO VUNG BAO LU", dict(name="UY BAN MTTQ VIET NAM", acc="1500201113838", bank="Agribank"), None),
            (date(2026, 5, 2), 20, 0, PAY, 500_000, "out", "transfer", "charity", "Ung ho quy khuyen hoc xa Hai Hau", dict(name="QUY KHUYEN HOC XA HAI HAU", acc="3204205999888", bank="Agribank"), None),
        ]
        # tiết kiệm: tất toán / gửi mới (dòng tiền trên tài khoản thanh toán)
        E += [
            (date(2025, 10, 28), 8, 5, PAY, 150_000_000, "in", "internal", "savings_withdrawal", "TAT TOAN SO TIET KIEM 208872345606", None, None),
            (date(2025, 10, 28), 8, 5, PAY, 7_350_000, "in", "interest", "interest", "TRA LAI SO TIET KIEM 208872345606 KY HAN 12T", None, None),
            (date(2025, 10, 28), 8, 30, PAY, 180_000_000, "out", "internal", "savings_deposit", "GUI TIET KIEM ONLINE 12 THANG SO 208872345602", None, None),
            (date(2025, 12, 15), 9, 0, PAY, 50_000_000, "out", "internal", "savings_deposit", "GUI TIET KIEM ONLINE 6 THANG SO 208872345607", None, None),
            (date(2026, 6, 15), 8, 5, PAY, 50_000_000, "in", "internal", "savings_withdrawal", "TAT TOAN SO TIET KIEM 208872345607", None, None),
            (date(2026, 6, 15), 8, 5, PAY, 1_050_000, "in", "interest", "interest", "TRA LAI SO TIET KIEM 208872345607 KY HAN 6T", None, None),
            (date(2026, 6, 15), 8, 40, PAY, 50_000_000, "out", "internal", "savings_deposit", "GUI TIET KIEM ONLINE 6 THANG SO 208872345603", None, None),
        ]
        # ------------------------------------------------ GIAO DỊCH BẤT THƯỜNG CÀI SẴN (nhãn eval)
        A = [
            (datetime(2026, 7, 9, 14, 20), PAY, 20_000_000, "atm", "atm_withdraw", "RUT TIEN ATM HOAN KIEM", None, "ATM",
             "Rút tiền mặt 20 triệu một lần, gấp gần 10 lần mức rút thường ngày"),
            (datetime(2026, 8, 14, 22, 47), PAY, 45_000_000, "transfer", "transfer_out",
             "HO TRO XAC MINH TAI KHOAN THEO YEU CAU CO QUAN DIEU TRA", SCAMMER, None,
             "Chuyển 45 triệu cho người lạ lúc gần 23h, nội dung giả danh cơ quan điều tra (lừa đảo)"),
            (datetime(2026, 8, 15, 8, 12), PAY, 30_000_000, "transfer", "transfer_out",
             "CHUYEN TIEN XAC MINH LAN 2 DE GIAI TOA TAI KHOAN", SCAMMER, None,
             "Chuyển tiếp 30 triệu cho cùng người lạ trong vòng 1 ngày"),
            (datetime(2026, 9, 6, 3, 12), CARD, 1_990_000, "card", "entertainment", "APPLE.COM/BILL ITUNES.COM", None,
             "APPLE.COM/BILL", "Giao dịch thẻ quốc tế lúc 3 giờ sáng ở merchant chưa từng dùng"),
            (datetime(2026, 10, 3, 21, 5), PAY, 15_000_000, "transfer", "transfer_out",
             "NAP TIEN DAU TU UNG DUNG VINA INVEST LOI NHUAN 3% NGAY", SCAM_CO, None,
             "Chuyển 15 triệu cho công ty lạ, nội dung đầu tư hứa lãi cao"),
        ]

        for (d, hh, mm, acc, amt, dr, ch, cat, desc, cp, merch) in E:
            self.add(acc, datetime.combine(d, time(hh, mm)), amt, dr, ch, cat, desc, cp, merch)
        for (ts, acc, amt, ch, cat, desc, cp, merch, note) in A:
            self.add(acc, ts, amt, "out", ch, cat, desc, cp, merch, anomaly=note)

        self._balances({PAY: 150_000_000})

    # ================================================================== số dư
    def _balances(self, opening: dict):
        """Tính balance_after theo thứ tự thời gian."""
        for acc, bal in opening.items():
            rows = sorted((t for t in self.txns if t["account_id"] == acc), key=lambda t: t["txn_time"])
            low = None
            for t in rows:
                bal += t["amount"] if t["direction"] == "in" else -t["amount"]
                t["balance_after"] = bal
                low = bal if low is None else min(low, bal)
            if low is not None and low < 0:
                raise SystemExit(f"Số dư {acc} bị âm ({low:,}) - cần chỉnh lại kịch bản")
            for a in self.accounts:
                if a["account_id"] == acc:
                    a["balance"] = bal
                    a["min_balance_seen"] = low


def _acc(cp):
    return dict(account_number=cp["acc"], bank_name=cp["bank"])


# --------------------------------------------------------------------------- SQL
def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (date, datetime)):
        return f"'{v.isoformat(sep=' ') if isinstance(v, datetime) else v.isoformat()}'"
    if isinstance(v, list):
        return "ARRAY[" + ",".join(q(x) for x in v) + "]::text[]" if v else "'{}'::text[]"
    return "'" + str(v).replace("'", "''") + "'"


def insert(table, cols, rows, chunk=500):
    out = []
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        vals = ",\n".join("(" + ",".join(q(r.get(c)) for c in cols) + ")" for r in part)
        out.append(f"INSERT INTO {table} ({','.join(cols)}) VALUES\n{vals};")
    return "\n".join(out)


def build(end: date, seed: int) -> tuple[str, dict]:
    g = Gen(end, seed)
    g.persona_hung()
    for a in g.accounts:
        if "fixed_balance" in a and a["fixed_balance"] is not None:
            a["balance"] = a["fixed_balance"]
        if a["account_id"] == "TK000105":
            # dư nợ gốc còn lại theo trả góp đều (annuity): gốc 450tr, 8,9%/năm, 60 kỳ, 9,35tr/kỳ.
            # 10 kỳ đã trả trước 05/2025 + các kỳ trích nợ có trong dữ liệu.
            paid = sum(1 for t in g.txns if t["category_code"] == "loan_payment") + 10
            i = a["interest_rate"] / 100 / 12
            k = (1 + i) ** paid
            a["balance"] = max(0, round((450_000_000 * k - a["monthly_payment"] * (k - 1) / i) / 1000) * 1000)
        a.setdefault("balance", 0)

    g.txns.sort(key=lambda t: (t["txn_time"], t["account_id"]))
    stats = {
        "customers": len(g.customers), "accounts": len(g.accounts), "transactions": len(g.txns),
        "anomalies": sum(t["is_anomaly_seed"] for t in g.txns),
        "per_customer": {},
        "period": f"{START} -> {end}",
    }
    acc_owner = {a["account_id"]: a["customer_id"] for a in g.accounts}
    for t in g.txns:
        c = acc_owner[t["account_id"]]
        stats["per_customer"][c] = stats["per_customer"].get(c, 0) + 1
    stats["min_balance"] = {a["account_id"]: a.get("min_balance_seen") for a in g.accounts if a.get("min_balance_seen") is not None}

    parts = [
        "-- Sinh tự động bởi db/generate_seed.py. DỮ LIỆU MOCK / TỔNG HỢP, không phải dữ liệu thật.",
        f"-- Khoảng thời gian: {START} -> {end}. Seed ngẫu nhiên: {seed}.",
        "SET search_path TO vb;",
        "BEGIN;",
        insert("categories", ["category_code", "name_vi", "group_code", "direction", "is_spending", "is_income", "keywords"],
               [dict(zip(["category_code", "name_vi", "group_code", "direction", "is_spending", "is_income", "keywords"], c))
                for c in CATEGORIES]),
        insert("products", ["product_code", "name_vi", "product_type", "short_desc", "interest_rate", "term_months",
                            "min_amount", "max_amount", "max_term_months", "channel"],
               [dict(zip(["product_code", "name_vi", "product_type", "short_desc", "interest_rate", "term_months",
                          "min_amount", "max_amount", "max_term_months", "channel"], p)) for p in PRODUCTS]),
        insert("customers", ["customer_id", "full_name", "salutation", "date_of_birth", "gender", "occupation", "city",
                             "segment", "accessibility_needs", "persona_note"], g.customers),
        insert("accounts", ["account_id", "customer_id", "parent_account_id", "account_number", "account_type", "nickname", "product_code",
                            "balance", "interest_rate", "term_months", "opened_at", "maturity_date",
                            "monthly_payment", "status"], g.accounts),
        insert("beneficiaries", ["customer_id", "display_name", "relationship", "aliases", "account_number", "bank_name"],
               g.beneficiaries),
        insert("transactions", ["account_id", "txn_time", "amount", "direction", "channel", "description",
                                "counterparty_name", "counterparty_account", "counterparty_bank", "merchant",
                                "category_code", "balance_after", "is_anomaly_seed", "anomaly_note"], g.txns),
        "COMMIT;",
        "",
    ]
    return "\n".join(parts), stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=DEFAULT_END.isoformat(), help="ngày cuối của dữ liệu (YYYY-MM-DD)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=str(Path(__file__).with_name("seed.sql")))
    a = ap.parse_args()
    sql, stats = build(date.fromisoformat(a.end), a.seed)
    Path(a.out).write_text(sql, encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    print(f"-> {a.out}")
