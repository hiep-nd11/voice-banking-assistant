import Icon from "../components/Icon.jsx";
import { BALANCE, money } from "../lib/transfer.js";
import { config, maskedAccount } from "../lib/config.js";

export default function Transfer({
  form,
  update,
  go,
  onContinue,
  saveRecipient,
}) {
  return (
    <form
      className="page"
      onSubmit={(e) => {
        e.preventDefault();
        onContinue();
      }}
      noValidate
    >
      <div className="smallcard">
        <div>
          <div className="note">Tài khoản nguồn</div>
          <b style={{ fontSize: 13 }}>
            {config.user.bank} · {maskedAccount()}
          </b>
          <div style={{ fontSize: 12, color: "#088e84", marginTop: 4 }}>
            Khả dụng: {money(BALANCE)}
          </div>
        </div>
        <Icon name="wallet" size={26} />
      </div>
      {form.qrLocked && (
        <div
          className="pill"
          style={{ marginBottom: 19, display: "inline-flex" }}
        >
          <Icon name="check" size={14} /> &nbsp;Thông tin từ QR · Có thể chỉnh
          sửa
        </div>
      )}
      <div className="field">
        <label className="label" htmlFor="bank">
          Ngân hàng thụ hưởng
        </label>
        <select
          id="bank"
          className="input"
          value={form.bank}
          onChange={(e) => update("bank", e.target.value)}
        >
          {[...new Set([...config.banks.map((b) => b.name), form.bank])].map(
            (b) => (
              <option key={b}>{b}</option>
            ),
          )}
        </select>
      </div>
      <div className="field">
        <label className="label" htmlFor="account">
          Số tài khoản
        </label>
        <div style={{ display: "flex", gap: 9 }}>
          <input
            id="account"
            className="input"
            inputMode="numeric"
            placeholder="Nhập số tài khoản"
            value={form.account}
            onChange={(e) => update("account", e.target.value)}
          />
          <button
            type="button"
            className="filebutton"
            onClick={() => go("qr")}
            title="Quét QR"
          >
            <Icon name="qr" />
          </button>
        </div>
      </div>
      <div className="field">
        <label className="label" htmlFor="recipient">
          Tên người thụ hưởng
        </label>
        <input
          id="recipient"
          className="input"
          placeholder="Tên người nhận"
          value={form.recipient}
          onChange={(e) => update("recipient", e.target.value)}
        />
        <div className="note" style={{ marginTop: 7 }}>
          Demo: tên người nhận nhập tay, chưa có xác minh liên ngân hàng.
        </div>
      </div>
      <div className="field">
        <label className="label" htmlFor="nickname">
          Tên gợi nhớ (không bắt buộc)
        </label>
        <input
          id="nickname"
          className="input"
          maxLength={50}
          placeholder="Ví dụ: Mẹ, Cha, Bạn thân"
          value={form.nickname || ""}
          onChange={(e) => update("nickname", e.target.value)}
        />
        <div className="note" style={{ marginTop: 7 }}>
          Dùng trong danh bạ, không thay thế tên chủ tài khoản. Chọn “Lưu người
          nhận” để lưu hoặc cập nhật.
        </div>
      </div>
      <div className="field">
        <label className="label" htmlFor="amount">
          Số tiền chuyển
        </label>
        <div className="amountwrap">
          <input
            id="amount"
            className="input"
            inputMode="numeric"
            placeholder="0"
            value={form.amount}
            onChange={(e) =>
              update("amount", e.target.value.replace(/[^0-9]/g, ""))
            }
          />
          <span className="unit">VND</span>
        </div>
      </div>
      <div className="field">
        <label className="label" htmlFor="memo">
          Nội dung chuyển khoản
        </label>
        <input
          id="memo"
          className="input"
          maxLength={120}
          placeholder="Nhập nội dung"
          value={form.memo}
          onChange={(e) => update("memo", e.target.value)}
        />
      </div>
      <div className="note" style={{ marginBottom: 20 }}>
        Mọi giao dịch trên giao diện này chỉ là mô phỏng, không có tiền thật
        được chuyển.
      </div>
      <button className="cta" type="submit">
        Tiếp tục <Icon name="chev" size={17} />
      </button>
      <button
        className="cta secondary"
        style={{ marginTop: 12 }}
        type="button"
        onClick={() => saveRecipient()}
      >
        Lưu người nhận
      </button>
    </form>
  );
}
