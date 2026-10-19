import { useState } from "react";
import { config } from "../lib/config.js";
import { validateRecipient } from "../lib/recipients.js";

export default function RecipientForm({ saveRecipient, cancel }) {
  const [recipient, setRecipient] = useState({
    bank: config.transfer.defaultBank,
    account: "",
    recipient: "",
    nickname: "",
  });
  const [error, setError] = useState("");
  function update(key, value) {
    setRecipient((previous) => ({ ...previous, [key]: value }));
  }
  function submit(event) {
    event.preventDefault();
    const message = validateRecipient(recipient);
    if (message) return setError(message);
    if (saveRecipient(recipient)) cancel();
  }
  return (
    <form onSubmit={submit} noValidate>
      <div className="section-title">Thêm người nhận</div>
      <div className="field">
        <label className="label" htmlFor="saved-bank">
          Ngân hàng thụ hưởng
        </label>
        <select
          className="input"
          id="saved-bank"
          value={recipient.bank}
          onChange={(e) => update("bank", e.target.value)}
        >
          {config.banks.map((b) => (
            <option key={b.name}>{b.name}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label className="label" htmlFor="saved-account">
          Số tài khoản
        </label>
        <input
          className="input"
          id="saved-account"
          inputMode="numeric"
          value={recipient.account}
          onChange={(e) => update("account", e.target.value)}
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="saved-recipient">
          Tên người thụ hưởng
        </label>
        <input
          className="input"
          id="saved-recipient"
          value={recipient.recipient}
          onChange={(e) => update("recipient", e.target.value)}
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="saved-nickname">
          Tên gợi nhớ (không bắt buộc)
        </label>
        <input
          className="input"
          id="saved-nickname"
          maxLength={50}
          placeholder="Ví dụ: Mẹ, Cha"
          value={recipient.nickname}
          onChange={(e) => update("nickname", e.target.value)}
        />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="cta" type="submit">
        Lưu người nhận
      </button>
      <button
        className="cta secondary"
        style={{ marginTop: 12 }}
        type="button"
        onClick={cancel}
      >
        Hủy
      </button>
    </form>
  );
}
