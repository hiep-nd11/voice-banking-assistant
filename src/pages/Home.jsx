import { useState } from "react";
import Icon from "../components/Icon.jsx";
import Services from "../components/Services.jsx";
import Transactions from "../components/Transactions.jsx";
import { BALANCE, money } from "../lib/transfer.js";
import { config, maskedAccount } from "../lib/config.js";

export default function Home({ go, toast, service, transfers }) {
  const [visible, setVisible] = useState(true);
  return (
    <>
      <div className="top">
        <div className="topline">
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div className="avatar">
              <Icon name="user" size={23} />
            </div>
            <div>
              <div className="muted-white">Xin chào,</div>
              <div style={{ fontWeight: 800, fontSize: 15, marginTop: 3 }}>
                {config.user.name} 👋
              </div>
            </div>
          </div>
          <button
            className="iconbtn"
            aria-label="Thông báo"
            onClick={() => toast("Không có thông báo mới")}
          >
            <Icon name="bell" />
          </button>
        </div>
        <div className="balance-card">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span className="muted-white">Số dư tài khoản thanh toán</span>
            <button
              className="iconbtn"
              aria-label={visible ? "Ẩn số dư" : "Hiện số dư"}
              onClick={() => setVisible((v) => !v)}
            >
              <Icon name="eye" size={19} />
            </button>
          </div>
          <div className="balance">
            {visible ? money(BALANCE) : `•••••••• ${config.app.currencySymbol}`}
          </div>
          <div className="muted-white">
            {config.user.bank} · {maskedAccount()}
          </div>
        </div>
      </div>
      <div className="main">
        <div className="section-title">
          Dịch vụ nổi bật{" "}
          <button className="link" onClick={() => go("more")}>
            Xem tất cả ›
          </button>
        </div>
        <Services service={service} colorful />
        <div className="section-title" style={{ marginTop: 28 }}>
          Giao dịch gần đây{" "}
          <button className="link" onClick={() => go("history")}>
            Xem tất cả ›
          </button>
        </div>
        <Transactions transfers={transfers} />
      </div>
    </>
  );
}
