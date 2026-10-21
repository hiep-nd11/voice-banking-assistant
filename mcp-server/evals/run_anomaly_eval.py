"""
Eval bộ phát hiện giao dịch bất thường (detect_unusual_transactions) trên dữ liệu mock.

    DATABASE_URL=... python -m evals.run_anomaly_eval

Nhãn đúng lấy từ cột transactions.is_anomaly_seed (chỉ script eval đọc cột này, tool không đọc).
Giai đoạn chấm: 01/11/2025 -> hôm nay. 6 tháng đầu (05-10/2025) làm lịch sử nền cho các luật so sánh.

LƯU Ý TRUNG THỰC: dữ liệu mock và luật do cùng một nhóm viết, nên kết quả chưa chứng minh độ chính xác
trên dữ liệu thật. Bộ dữ liệu có cài sẵn 1 ca "khó" hợp lệ (thanh toán 25 triệu cho thợ sửa nhà mới)
để đo báo nhầm.
"""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DEMO_NOW", "2026-10-25T23:00")

from app import tools as T  # noqa: E402

START = date(2025, 11, 1)


def main():
    end = T.today()
    tp = fp = fn = 0
    rows_out = []
    for c in T._q("SELECT customer_id FROM vb.customers ORDER BY 1"):
        cid = c["customer_id"]
        truth = {r["txn_id"]: r["anomaly_note"] for r in T._q(
            """SELECT t.txn_id, t.anomaly_note FROM vb.transactions t JOIN vb.accounts a USING (account_id)
               WHERE a.customer_id=%s AND t.is_anomaly_seed AND t.txn_time >= %s AND t.txn_time <= %s""",
            (cid, START, T.now()))}
        pred = {i["txn_id"]: i for i in T._detect(cid, START, end)}
        for tid in pred.keys() & truth.keys():
            tp += 1
            rows_out.append(("TP", cid, pred[tid]["time"], pred[tid]["amount_text"], "; ".join(pred[tid]["reasons"])))
        for tid in pred.keys() - truth.keys():
            fp += 1
            rows_out.append(("FP", cid, pred[tid]["time"], pred[tid]["amount_text"], "; ".join(pred[tid]["reasons"])))
        for tid in truth.keys() - pred.keys():
            fn += 1
            rows_out.append(("FN", cid, str(tid), "", truth[tid]))
    n_txn = T._q1("SELECT count(*) AS n FROM vb.transactions WHERE txn_time >= %s AND txn_time <= %s",
                  (START, T.now()))["n"]
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    print(f"Giai đoạn {START} -> {end}, {n_txn} giao dịch, {tp + fn} ca bất thường cài sẵn")
    print(f"TP={tp} FP={fp} FN={fn}  precision={prec:.1%}  recall={rec:.1%}")
    for r in sorted(rows_out, key=lambda x: (x[0], x[2])):
        print(" ", " | ".join(r))


if __name__ == "__main__":
    main()
