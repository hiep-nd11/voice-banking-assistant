import { useState } from "react";
import Icon from "../components/Icon.jsx";
import Services from "../components/Services.jsx";
import Transactions from "../components/Transactions.jsx";
import { money } from "../lib/transfer.js";
import { config, maskedAccount } from "../lib/config.js";

export default function Home({ go, toast, service, transfers, balance }) {
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
            {visible ? money(balance) : `•••••••• ${config.app.currencySymbol}`}
          </div>
          <div className="muted-white">
            {config.user.bank} · {maskedAccount()}
          </div>
          {config.bankingSource === "mcp" && (
            <button className="balance-assets-link" onClick={() => go("assets")}>
              Quản lý tài sản <Icon name="chev" size={16} />
            </button>
          )}
        </div>
      </div>
      <div className="main">
        <div className="section-title">
          Dịch vụ nổi bật{" "}
          <button className="link" onClick={() => go("more")}>
            Xem tất cả ›
          </button>
        </div>
        <Services
          service={service}
          colorful
          only={config.bankingSource === "mcp" ? ["transfer", "save", "loan", "bill"] : undefined}
        />
        {config.bankingSource === "mcp" && (
          <button className="home-analysis-link" onClick={() => go("analytics")}>
            <span className="glyph">
              <Icon name="fund" size={23} />
            </span>
            <span>
              <b>Hiểu rõ dòng tiền của bạn</b>
              <small>Theo dõi thu chi và kế hoạch tháng này</small>
            </span>
            <Icon name="chev" size={18} />
          </button>
        )}
        <div className="section-title" style={{ marginTop: 28 }}>
          Giao dịch gần đây{" "}
          <button className="link" onClick={() => go("history")}>
            Xem tất cả ›
          </button>
        </div>
        <Transactions
          transfers={transfers}
          limit={config.bankingSource === "mcp" ? 5 : undefined}
        />
      </div>
    </>
  );
}
