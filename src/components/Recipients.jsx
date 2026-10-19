import Icon from "./Icon.jsx";

export default function Recipients({
  recipients,
  quickTransfer,
  removeRecipient,
}) {
  if (!recipients.length)
    return (
      <p className="empty">
        Chưa có người nhận đã lưu. Thêm người nhận để chuyển tiền nhanh.
      </p>
    );
  return (
    <div className="recipient-list">
      {recipients.map((r) => (
        <div className="recipient-card" key={`${r.bank}-${r.account}`}>
          <div className="recipient-details">
            <span className="avatar recipient-avatar">
              <Icon name="user" />
            </span>
            <div>
              <b>{r.nickname || r.recipient}</b>
              {r.nickname && <div className="note">{r.recipient}</div>}
              <div className="note">
                {r.bank} · {r.account}
              </div>
            </div>
          </div>
          <div className="recipient-actions">
            <button
              className="filebutton"
              onClick={() => quickTransfer(r)}
              aria-label={`Chuyển tiền nhanh cho ${r.nickname || r.recipient}`}
            >
              Chuyển tiền nhanh
            </button>
            <button
              className="link"
              onClick={() => removeRecipient(r)}
              aria-label={`Xóa ${r.nickname || r.recipient}`}
            >
              Xóa
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
