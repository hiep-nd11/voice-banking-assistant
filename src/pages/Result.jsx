import Icon from "../components/Icon.jsx";
import { money } from "../lib/transfer.js";
import { config, maskedAccount } from "../lib/config.js";

export function Confirm({ form, go, finish }) {
  return (
    <div className="page">
      <div className="note" style={{ textAlign: "center" }}>
        Số tiền chuyển
      </div>
      <div className="amount-big">{money(Number(form.amount))}</div>
      <div className="smallcard">
        <div>
          <div className="note">Từ tài khoản</div>
          <b style={{ fontSize: 12 }}>{config.user.name}</b>
          <div className="note">
            {config.user.bank} · {maskedAccount()}
          </div>
        </div>
        <Icon name="wallet" size={25} />
      </div>
      {[
        ["Ngân hàng nhận", form.bank],
        ["Số tài khoản", form.account],
        ["Người thụ hưởng", form.recipient],
        ["Nội dung", form.memo],
        ["Phí chuyển tiền", `${money(config.transfer.fee)} (demo)`],
      ].map(([label, value]) => (
        <div className="confirmrow" key={label}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
      <div style={{ marginTop: 29, display: "grid", gap: 11 }}>
        <button className="cta" onClick={finish}>
          Xác nhận giao dịch mô phỏng
        </button>
        <button className="cta secondary" onClick={() => go("transfer")}>
          Chỉnh sửa thông tin
        </button>
      </div>
      <p className="note" style={{ marginTop: 15, textAlign: "center" }}>
        Ứng dụng thật phải sử dụng xác thực an toàn và API ngân hàng trước khi
        chuyển tiền.
      </p>
    </div>
  );
}

export function Success({ form, count, go, service }) {
  return (
    <div className="success">
      <div className="successmark">
        <Icon name="check" size={53} />
      </div>
      <h2>Đã tạo giao dịch demo!</h2>
      <p>
        Lệnh chuyển {money(Number(form.amount))} cho <b>{form.recipient}</b> đã
        được ghi nhận trên giao diện mô phỏng. Không có tiền thật được chuyển.
      </p>
      <div
        className="smallcard"
        style={{ width: "100%", textAlign: "left", margin: "15px 0" }}
      >
        <div>
          <div className="note">Mã tham chiếu mock</div>
          <b>
            {config.app.referencePrefix}
            {String(count).padStart(config.app.referenceDigits, "0")}
          </b>
        </div>
        <Icon name="check" size={25} />
      </div>
      <button className="cta" onClick={() => go("home")}>
        Về trang chủ
      </button>
      <button
        className="cta secondary"
        style={{ marginTop: 12 }}
        onClick={() => service("transfer")}
      >
        Chuyển tiền khác
      </button>
    </div>
  );
}
