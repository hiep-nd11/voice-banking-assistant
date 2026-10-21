import { useState } from "react";
import Icon from "../components/Icon.jsx";
import FinanceResult from "../components/FinanceResult.jsx";
import { config, maskedAccount } from "../lib/config.js";
import { money } from "../lib/transfer.js";
import { workflowTitle } from "../lib/workflows.js";

export default function Workflow({ flow, busy, error, onEvent }) {
  const slots = flow.slots || {};
  const transfer = flow.intent.startsWith("transfer");
  const recipient = slots.beneficiary || slots.qr || slots.destination;
  const [name, setName] = useState("");
  const [amount, setAmount] = useState(String(slots.amount || ""));
  const [term, setTerm] = useState(String(slots.term_months || ""));
  const [note, setNote] = useState(slots.note || "");
  const [qrName, setQrName] = useState(slots.qr?.recipient || "");
  const [dirty, setDirty] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const highRisk = flow.risk?.risk_level === "high";
  const minimum =
    flow.intent === "open_savings" ? 1000000 : flow.intent === "open_loan" ? 5000000 : 1000;
  const editable = flow.step !== "prepared";
  function update(callback, value) {
    callback(value);
    setDirty(true);
  }
  function save(e) {
    e.preventDefault();
    const payload = { amount: Number(amount), note };
    if (term) payload.term_months = Number(term);
    if (slots.qr) payload.recipient = qrName;
    void onEvent("form_updated", payload);
  }
  return (
    <div className="page workflow-page">
      <div className="workflow-progress">
        <span className="active">1. Thông tin</span>
        <span className={["review", "prepared"].includes(flow.step) ? "active" : ""}>
          2. Kiểm tra
        </span>
        <span className={flow.step === "prepared" ? "active" : ""}>3. Chuẩn bị</span>
      </div>
      <h2 className="section-title">{workflowTitle(flow.intent)}</h2>
      <p className="note">
        Anh có thể nói tiếp với trợ lý hoặc điền trực tiếp bên dưới. Chưa có giao dịch tiền thật.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {flow.step === "prepared" && (
        <p className="workflow-status" role="status">
          Thông tin đã được chuẩn bị. Chưa chuyển tiền, mở sổ hoặc giải ngân.
        </p>
      )}
      <div className="smallcard">
        <div>
          <span className="note">Tài khoản nguồn</span>
          <p>
            <b>
              {config.user.bank} · {maskedAccount()}
            </b>
          </p>
        </div>
        <Icon name="wallet" />
      </div>
      {recipient && (
        <section className="workflow-recipient">
          <span className="note">Người nhận</span>
          <b>{recipient.name || recipient.recipient || "Chưa xác minh tên"}</b>
          <p>
            {recipient.bank} · {recipient.account_number || recipient.account}
          </p>
          {editable && slots.beneficiary && (
            <button
              className="link"
              disabled={busy}
              onClick={() => onEvent("change_recipient", {})}
            >
              Đổi người nhận
            </button>
          )}
          {editable && slots.qr && (
            <button className="link" disabled={busy} onClick={() => onEvent("rescan", {})}>
              Quét mã QR khác
            </button>
          )}
          {slots.qr && (
            <p className="note">
              Thông tin lấy từ QR, chưa xác minh tên qua ngân hàng. Anh cần đối chiếu trước khi tiếp
              tục.
            </p>
          )}
        </section>
      )}
      {flow.step === "awaiting_recipient" && (
        <section>
          <form
            className="workflow-search"
            onSubmit={(e) => {
              e.preventDefault();
              void onEvent("recipient_search", { name: name.trim() });
            }}
          >
            <label className="label" htmlFor="workflow-recipient-search">
              Tìm người nhận
            </label>
            <input
              className="input"
              id="workflow-recipient-search"
              value={name}
              required
              maxLength={150}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              placeholder="Tên, con trai, mẹ…"
            />
            <button className="filebutton" disabled={busy || !name.trim()}>
              Tìm trong danh bạ
            </button>
          </form>
          <div className="recipient-list">
            {(flow.candidates || []).map((row) => (
              <button
                className="workflow-choice"
                key={row.beneficiary_id}
                disabled={busy}
                onClick={() =>
                  onEvent("recipient_selected", { beneficiary_id: row.beneficiary_id })
                }
              >
                <b>{row.name}</b>
                <span>
                  {row.relationship} · {row.bank} · {row.account_number}
                </span>
              </button>
            ))}
          </div>
          {!flow.candidates?.length && (
            <p className="note">
              Chưa có người nhận phù hợp. Anh tìm theo tên hoặc cách gọi khác nhé.
            </p>
          )}
        </section>
      )}
      {flow.step === "awaiting_qr" && (
        <button className="cta" disabled={busy} onClick={() => onEvent("resume", {})}>
          Mở màn quét QR
        </button>
      )}
      {!["awaiting_recipient", "awaiting_qr"].includes(flow.step) && (
        <form onSubmit={save}>
          <div className="field">
            <label className="label" htmlFor="workflow-amount">
              {transfer ? "Số tiền chuyển" : "Số tiền (VND)"}
            </label>
            <input
              id="workflow-amount"
              className="input"
              type="number"
              min={minimum}
              max={Number.MAX_SAFE_INTEGER}
              step="1"
              required
              value={amount}
              disabled={busy || !editable}
              onChange={(e) => update(setAmount, e.target.value)}
            />
            <p className="note">Tối thiểu {money(minimum)}</p>
          </div>
          {!transfer && (
            <div className="field">
              <label className="label" htmlFor="workflow-term">
                Kỳ hạn (tháng)
              </label>
              {flow.intent === "open_savings" ? (
                <select
                  id="workflow-term"
                  className="input"
                  required
                  value={term}
                  disabled={busy || !editable}
                  onChange={(e) => update(setTerm, e.target.value)}
                >
                  <option value="">Chọn kỳ hạn</option>
                  {[1, 3, 6, 9, 12, 24].map((m) => (
                    <option key={m} value={m}>
                      {m} tháng
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="workflow-term"
                  className="input"
                  type="number"
                  min="1"
                  max="300"
                  value={term}
                  disabled={busy || !editable}
                  onChange={(e) => update(setTerm, e.target.value)}
                />
              )}
            </div>
          )}
          {slots.qr && (
            <div className="field">
              <label className="label" htmlFor="workflow-qr-name">
                Tên người nhận cần đối chiếu
              </label>
              <input
                id="workflow-qr-name"
                className="input"
                required
                maxLength={150}
                value={qrName}
                disabled={busy || !editable}
                onChange={(e) => update(setQrName, e.target.value)}
              />
            </div>
          )}
          {transfer && (
            <div className="field">
              <label className="label" htmlFor="workflow-note">
                Nội dung chuyển khoản
              </label>
              <input
                id="workflow-note"
                className="input"
                maxLength={140}
                value={note}
                disabled={busy || !editable}
                onChange={(e) => update(setNote, e.target.value)}
              />
            </div>
          )}
          {editable && (
            <button className="cta secondary" type="submit" disabled={busy}>
              Lưu thông tin và kiểm tra
            </button>
          )}
        </form>
      )}
      {flow.risk && (
        <section className={`workflow-risk ${highRisk ? "high" : ""}`}>
          <b>{highRisk ? "Cảnh báo rủi ro cao" : "Kiểm tra rủi ro"}</b>
          {(flow.risk.reasons || []).map((reason, index) => (
            <p key={index}>{reason}</p>
          ))}
          {flow.risk.insufficient_balance && <p>Số dư không đủ. Anh cần đổi số tiền.</p>}
          {!flow.risk.reasons?.length && !flow.risk.insufficient_balance && (
            <p>Chưa ghi nhận cảnh báo từ bước kiểm tra hiện tại.</p>
          )}
        </section>
      )}
      {flow.step === "review" && (
        <>
          {dirty && (
            <p className="note">Anh cần lưu thay đổi để BE kiểm tra lại trước khi chuẩn bị.</p>
          )}
          {highRisk && (
            <label className="workflow-ack">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              Tôi đã đọc cảnh báo và vẫn muốn chuẩn bị yêu cầu.
            </label>
          )}
          <button
            className="cta"
            disabled={
              busy || dirty || flow.risk?.insufficient_balance || (highRisk && !acknowledged)
            }
            onClick={() => onEvent("prepare", { risk_acknowledged: acknowledged })}
          >
            Chuẩn bị yêu cầu · Chưa giao dịch
          </button>
        </>
      )}
      {flow.prepared && <FinanceResult data={flow.prepared} />}
      {busy && (
        <p className="note" role="status">
          Đang cập nhật kịch bản…
        </p>
      )}
      <button className="workflow-cancel" disabled={busy} onClick={() => onEvent("cancel", {})}>
        Hủy yêu cầu này
      </button>
    </div>
  );
}
