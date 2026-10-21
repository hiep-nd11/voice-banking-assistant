import { useState } from "react";
import RecipientsList from "../components/Recipients.jsx";
import RecipientForm from "../components/RecipientForm.jsx";

export default function Recipients(props) {
  const [adding, setAdding] = useState(false);
  return (
    <div className="page">
      {adding ? (
        <RecipientForm saveRecipient={props.saveRecipient} cancel={() => setAdding(false)} />
      ) : (
        <>
          <div className="section-title">Người quen đã lưu</div>
          <p className="note">
            Chọn người nhận để điền sẵn ngân hàng, số tài khoản và tên chủ tài khoản. Số tiền và nội
            dung được nhập riêng cho mỗi lần chuyển.
          </p>
          <RecipientsList {...props} />
          <button
            className="cta secondary"
            style={{ marginTop: 20 }}
            onClick={() => setAdding(true)}
          >
            Thêm người nhận
          </button>
          <p className="note">
            Lưu lại cùng ngân hàng và số tài khoản sẽ cập nhật thông tin đã có. Danh sách được lưu
            trên trình duyệt này.
          </p>
        </>
      )}
    </div>
  );
}
