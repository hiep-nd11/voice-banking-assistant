import { useState } from "react";
import { AccountCard, bankingDate } from "../components/AccountPortfolio.jsx";
import { money } from "../lib/transfer.js";

export default function Holdings({
  type,
  accounts,
  asOf,
  prepare,
  refresh,
  refreshing,
  embedded = false,
  visible: controlledVisible,
  onToggleVisible,
}) {
  const [localVisible, setLocalVisible] = useState(true);
  const visible = controlledVisible ?? localVisible;
  const loans = type === "loan";
  const rows = accounts.filter((row) => row.type === type);
  const total = rows.reduce((sum, row) => sum + (loans ? row.outstanding : row.balance), 0);
  return (
    <div className={embedded ? "holdings-content" : "page"}>
      <section className="holdings-summary">
        <div className="section-title">
          {loans ? "Tổng dư nợ vay" : "Tổng tiền tiết kiệm"}
          <button className="link" onClick={onToggleVisible || (() => setLocalVisible((v) => !v))}>
            {visible ? "Ẩn số tiền" : "Hiện số tiền"}
          </button>
        </div>
        <strong>{visible ? money(total) : "•••••••• ₫"}</strong>
        <p>
          {rows.length} {loans ? "khoản vay" : "sổ tiết kiệm"}
        </p>
      </section>
      <div className="section-title">
        {loans ? "Chi tiết khoản vay" : "Danh sách sổ tiết kiệm"}
        <button className="link" disabled={refreshing} onClick={refresh}>
          {refreshing ? "Đang cập nhật…" : "Cập nhật"}
        </button>
      </div>
      {rows.map((account) => (
        <AccountCard key={account.account_id} account={account} visible={visible} detailed />
      ))}
      {!rows.length && (
        <p className="empty">{loans ? "Bạn chưa có khoản vay." : "Bạn chưa có sổ tiết kiệm."}</p>
      )}
      {asOf && <p className="note">Dữ liệu cập nhật: {bankingDate(asOf)}</p>}
      <button className="cta" onClick={prepare}>
        {loans ? "Chuẩn bị đăng ký vay" : "Chuẩn bị gửi tiết kiệm mới"}
      </button>
    </div>
  );
}
