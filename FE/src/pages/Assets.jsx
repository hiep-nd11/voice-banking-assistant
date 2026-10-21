import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { bankingDate } from "../components/AccountPortfolio.jsx";
import Holdings from "./Holdings.jsx";
import { money } from "../lib/transfer.js";

export default function Assets({
  initial = "overview",
  accounts,
  asOf,
  refresh,
  refreshing,
  prepare,
}) {
  const [tab, setTab] = useState(initial);
  const [visible, setVisible] = useState(true);
  const savings = accounts.filter((a) => a.type === "savings");
  const loans = accounts.filter((a) => a.type === "loan");
  const payments = accounts.filter((a) => a.type === "payment");
  const gross = [...payments, ...savings].reduce((sum, a) => sum + a.balance, 0);
  const debt = loans.reduce((sum, a) => sum + a.outstanding, 0);
  const amount = (n) => (visible ? money(n) : "•••••••• ₫");
  const nextMaturity = savings
    .filter((a) => a.maturity_date && (a.days_to_maturity == null || a.days_to_maturity >= 0))
    .sort((a, b) => a.maturity_date.localeCompare(b.maturity_date))[0];
  const nextPayment = loans
    .filter((a) => a.next_payment_date)
    .sort((a, b) => a.next_payment_date.localeCompare(b.next_payment_date))[0];
  return (
    <div className="page assets-page">
      <div className="segmented" role="group" aria-label="Nhóm tài sản">
        {[
          ["overview", "Tổng quan"],
          ["savings", "Tiết kiệm"],
          ["loan", "Khoản vay"],
        ].map(([id, label]) => (
          <button
            key={id}
            aria-pressed={tab === id}
            className={tab === id ? "selected" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "overview" ? (
        <>
          <section className="assets-hero">
            <div className="assets-eyebrow">
              TỔNG TÀI SẢN{" "}
              <button
                className="iconbtn"
                aria-label={visible ? "Ẩn giá trị tài sản" : "Hiện giá trị tài sản"}
                onClick={() => setVisible((v) => !v)}
              >
                <Icon name="eye" size={18} />
              </button>
            </div>
            <strong>{amount(gross)}</strong>
            <p>Tài khoản thanh toán và tiền tiết kiệm</p>
          </section>
          <div className="asset-net-grid">
            <article>
              <span>Tổng dư nợ</span>
              <strong>{amount(debt)}</strong>
              <small>Khoản vay còn phải trả</small>
            </article>
            <article>
              <span>Tài sản ròng</span>
              <strong className={gross - debt < 0 ? "negative" : "positive"}>
                {amount(gross - debt)}
              </strong>
              <small>Tổng tài sản − Tổng dư nợ</small>
            </article>
          </div>
          <p className="note">
            Chỉ tính tài khoản thanh toán, tiết kiệm và khoản vay đang theo dõi tại ngân hàng; chưa
            bao gồm các tài sản khác.
          </p>
          <div className="assets-breakdown">
            <div className="asset-summary-row">
              <span className="asset-row-icon">
                <Icon name="wallet" size={21} />
              </span>
              <span>
                <b>Tài khoản thanh toán</b>
                <small>{payments.length} tài khoản</small>
              </span>
              <strong>{amount(payments.reduce((sum, a) => sum + a.balance, 0))}</strong>
            </div>
            <button className="asset-summary-row" onClick={() => setTab("savings")}>
              <span className="asset-row-icon green">
                <Icon name="save" size={21} />
              </span>
              <span>
                <b>Tiền tiết kiệm</b>
                <small>{savings.length} sổ đang theo dõi</small>
              </span>
              <strong>
                {amount(savings.reduce((sum, a) => sum + a.balance, 0))}
                <Icon name="chev" size={15} />
              </strong>
            </button>
            <button className="asset-summary-row" onClick={() => setTab("loan")}>
              <span className="asset-row-icon amber">
                <Icon name="loan" size={21} />
              </span>
              <span>
                <b>Dư nợ vay</b>
                <small>{loans.length} khoản vay · Theo dõi riêng</small>
              </span>
              <strong>
                {amount(loans.reduce((sum, a) => sum + a.outstanding, 0))}
                <Icon name="chev" size={15} />
              </strong>
            </button>
          </div>
          <h2 className="section-title assets-section-title">Lịch tài chính sắp tới</h2>
          {nextMaturity && (
            <button className="asset-event" onClick={() => setTab("savings")}>
              <span className="asset-event-dot green" />
              <span>
                <b>Đáo hạn tiết kiệm</b>
                <small>{nextMaturity.name}</small>
                <span>
                  {bankingDate(nextMaturity.maturity_date)} · {amount(nextMaturity.balance)}
                </span>
              </span>
              <Icon name="chev" size={17} />
            </button>
          )}
          {nextPayment && (
            <button className="asset-event" onClick={() => setTab("loan")}>
              <span className="asset-event-dot amber" />
              <span>
                <b>Kỳ thanh toán khoản vay</b>
                <small>{nextPayment.name}</small>
                <span>
                  {bankingDate(nextPayment.next_payment_date)} ·{" "}
                  {nextPayment.monthly_payment == null
                    ? "Chưa có số tiền"
                    : amount(nextPayment.monthly_payment)}
                </span>
              </span>
              <Icon name="chev" size={17} />
            </button>
          )}
          {!nextMaturity && !nextPayment && (
            <p className="empty">Chưa có lịch đáo hạn hoặc thanh toán.</p>
          )}
          <div className="assets-sync">
            <span>{asOf ? `Cập nhật ${bankingDate(asOf)}` : "Dữ liệu từ ngân hàng"}</span>
            <button className="link" disabled={refreshing} onClick={refresh}>
              {refreshing ? "Đang cập nhật…" : "Cập nhật"}
            </button>
          </div>
        </>
      ) : (
        <Holdings
          key={tab}
          embedded
          type={tab}
          accounts={accounts}
          asOf={asOf}
          refresh={refresh}
          refreshing={refreshing}
          visible={visible}
          onToggleVisible={() => setVisible((v) => !v)}
          prepare={() => prepare(tab === "loan" ? "prepare-loan" : "prepare-savings")}
        />
      )}
    </div>
  );
}
