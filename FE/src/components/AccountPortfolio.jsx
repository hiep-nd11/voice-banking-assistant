import { money } from "../lib/transfer.js";
import Icon from "./Icon.jsx";
import { dateLabel } from "../lib/format.js";

export const bankingDate = dateLabel;

export function AccountCard({ account, visible = true, detailed = false }) {
  const loan = account.type === "loan";
  const amount = (n) => (visible ? money(n) : "•••••••• ₫");
  const rate =
    account.interest_rate == null
      ? "Chưa có thông tin"
      : `${account.interest_rate.toLocaleString("vi-VN")}%/năm`;
  return (
    <article className={`holding-card ${loan ? "holding-loan" : "holding-savings"}`}>
      <div className="holding-title">
        <span className="holding-icon">
          <Icon name={loan ? "loan" : "save"} size={21} />
        </span>
        <div>
          <h3>{account.name || (loan ? "Khoản vay" : "Sổ tiết kiệm")}</h3>
          <p>{account.account_number}</p>
        </div>
      </div>
      <p className="holding-caption">{loan ? "Dư nợ hiện tại" : "Số tiền gửi"}</p>
      <p className="holding-amount">{amount(loan ? account.outstanding : account.balance)}</p>
      <dl className="holding-facts">
        <div>
          <dt>Lãi suất</dt>
          <dd>{rate}</dd>
        </div>
        {account.term_months != null && (
          <div>
            <dt>Kỳ hạn</dt>
            <dd>{account.term_months} tháng</dd>
          </div>
        )}
        <div>
          <dt>{loan ? "Kỳ trả tiếp theo" : "Ngày đáo hạn"}</dt>
          <dd>{bankingDate(loan ? account.next_payment_date : account.maturity_date)}</dd>
        </div>
        {loan && (
          <div>
            <dt>Số tiền trả kỳ tới</dt>
            <dd>
              {account.monthly_payment == null
                ? "Chưa có thông tin"
                : amount(account.monthly_payment)}
            </dd>
          </div>
        )}
        {detailed && loan && (
          <div>
            <dt>Ngày kết thúc khoản vay</dt>
            <dd>{bankingDate(account.maturity_date)}</dd>
          </div>
        )}
        {detailed && account.parent_account_id && (
          <div>
            <dt>Tài khoản liên kết</dt>
            <dd>{account.parent_account_id}</dd>
          </div>
        )}
      </dl>
      {!loan && Number.isInteger(account.days_to_maturity) && (
        <p
          className={`holding-deadline ${account.days_to_maturity >= 0 && account.days_to_maturity <= 7 ? "soon" : ""}`}
        >
          {account.days_to_maturity > 0
            ? `Còn ${account.days_to_maturity} ngày đến hạn`
            : account.days_to_maturity === 0
              ? "Đến hạn trong ngày dữ liệu"
              : "Đã đến hạn"}
        </p>
      )}
    </article>
  );
}
