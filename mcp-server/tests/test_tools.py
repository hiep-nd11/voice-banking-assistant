"""Test tool trên Postgres thật đã nạp seed (bỏ qua nếu không có DB)."""
import os

import pytest

os.environ.setdefault("DEMO_NOW", "2026-10-21T09:30")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")

from app import tools as T  # noqa: E402

try:
    T._q1("SELECT 1 AS x FROM vb.customers LIMIT 1")
except Exception:  # pragma: no cover
    pytest.skip("Không kết nối được Postgres có schema vb", allow_module_level=True)

C = "KH0001"


def call(name, **kw):
    return T.call_tool(name, kw)


def test_balance_is_as_of_now_not_future():
    r = call("get_account_balances", customer_id=C)
    pay = next(a for a in r["accounts"] if a["type"] == "payment")
    last = T._q1("SELECT balance_after FROM vb.transactions WHERE account_id='TK000101' AND txn_time <= %s "
                 "ORDER BY txn_time DESC, txn_id DESC LIMIT 1", (T.now(),))
    assert pay["balance"] == last["balance_after"]
    assert "speech" in r and "anh Hưng" in r["speech"]


def test_future_transactions_hidden():
    r = call("search_transactions", customer_id=C, date_from="2026-10-01", date_to="2026-12-31")
    assert all(i["time"] <= "2026-10-21T09:30" for i in r["items"])


def test_spending_excludes_internal_moves():
    r = call("get_spending_summary", customer_id=C, date_from="2025-10-01", date_to="2025-10-31")
    codes = {i["code"] for i in r["items"]}
    assert not codes & {"savings_deposit", "investment", "lend_money"}


def test_month_overview_numbers_match_sql():
    r = call("get_month_overview", customer_id=C, month="2026-09")
    s = T._q1("""SELECT sum(amount) AS s FROM vb.v_txn WHERE customer_id=%s AND direction='out' AND is_spending
                 AND txn_time >= '2026-09-01' AND txn_time < '2026-10-01'""", (C,))["s"]
    assert r["total_spending"] == s


def test_category_resolution():
    assert T.resolve_category("tiền điện") == ["electricity"]
    assert "groceries" in T.resolve_category("đi chợ")
    assert T.resolve_category("học phí") == ["education"]


def test_beneficiary_isolation():
    # beneficiary 10 không thuộc KH0001 (không tồn tại)
    r = call("open_transfer_screen", customer_id=C, amount=1_000_000, beneficiary_id=10)
    assert "error" in r


def test_transfer_never_executes_and_masks_account():
    before = T._q1("SELECT count(*) AS n FROM vb.transactions")["n"]
    r = call("open_transfer_screen", customer_id=C, amount=1_500_000, beneficiary_id=2)
    after = T._q1("SELECT count(*) AS n FROM vb.transactions")["n"]
    assert before == after and r["executed"] is False
    assert r["ui_action"]["prefill"]["beneficiary"]["account_number"].startswith("****")
    full = T.get_action_for_ui(C, r["ui_action"]["action_id"])
    assert full["prefill"]["beneficiary"]["account_number"] == "0071004567890"
    with pytest.raises(T.ToolError):
        T.get_action_for_ui("KH0002", r["ui_action"]["action_id"])     # khách khác không đọc được


def test_high_risk_requires_acknowledgement():
    r = call("open_transfer_screen", customer_id=C, amount=5_000_000, note="chuyen tien xac minh theo yeu cau cong an")
    assert r.get("blocked") is True and r["ui_action"] is None
    r2 = call("open_transfer_screen", customer_id=C, amount=5_000_000, note="chuyen tien xac minh theo yeu cau cong an",
              risk_acknowledged=True)
    assert r2["ui_action"]["screen"] == "transfer"


def test_amount_limits():
    assert "error" in call("open_transfer_screen", customer_id=C, amount=900_000_000)
    assert "error" in call("open_savings_screen", customer_id=C, amount=500_000)
    assert "error" in call("open_loan_screen", customer_id=C, amount=900_000_000, loan_type="cầm cố sổ tiết kiệm")


def test_cancel_action():
    r = call("open_savings_screen", customer_id=C, amount=10_000_000, term_months=6)
    aid = r["ui_action"]["action_id"]
    assert call("cancel_pending_action", customer_id=C, action_id=aid)["ui_action"]["type"] == "close"
    assert "error" in call("cancel_pending_action", customer_id=C, action_id=aid)


def test_detection_catches_seeded_scam():
    r = call("detect_unusual_transactions", customer_id=C, date_from="2026-08-01", date_to="2026-08-31")
    amounts = {i["amount"] for i in r["items"]}
    assert {45_000_000, 30_000_000} <= amounts


def test_audit_log_written():
    n0 = T._q1("SELECT count(*) AS n FROM vb.tool_audit_log")["n"]
    call("get_current_date")
    assert T._q1("SELECT count(*) AS n FROM vb.tool_audit_log")["n"] == n0 + 1


def test_unknown_customer():
    assert "error" in call("get_account_balances", customer_id="KH9999")


def test_insufficient_balance_warns_but_not_blocked_as_scam():
    bal = T._payment_balance(C)
    r = call("open_transfer_screen", customer_id=C, amount=bal + 1_000_000, beneficiary_id=1)
    assert not r.get("blocked") and r["ui_action"]["screen"] == "transfer"
    assert r["risk"]["insufficient_balance"] is True and "công an" not in r["speech"]


def test_search_keeps_in_and_out_separate():
    r = call("search_transactions", customer_id=C, date_from="2025-11-01", date_to="2026-10-21", keyword="tuan")
    assert r["total_out"] == 20_000_000 and r["total_in"] == 20_000_000 and r["total"] == 20_000_000


def test_loan_screen_does_not_pick_product_for_user():
    r = call("open_loan_screen", customer_id=C, amount=100_000_000, loan_type="vay tiền")
    assert "product_code" not in r["ui_action"]["prefill"]
    assert "Chọn loại vay" in r["ui_action"]["required_user_inputs"]
    r2 = call("open_loan_screen", customer_id=C, amount=50_000_000, loan_type="vay nhanh")
    assert "product_code" not in r2["ui_action"]["prefill"]


@pytest.mark.parametrize("name,rel", [("vợ tôi", "vợ"), ("mẹ tôi", "mẹ"), ("em Tuấn", "em trai"), ("con Khoa", "con trai"),
                                      ("con gái tôi", "con gái"), ("thằng cu Khoa", "con trai")])
def test_find_beneficiary_natural_phrases(name, rel):
    r = T.call_tool("find_beneficiary", {"customer_id": C, "name": name})
    assert r["count"] == 1 and r["matches"][0]["relationship"] == rel
