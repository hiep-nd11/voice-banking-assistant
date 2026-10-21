import { config } from "../lib/config.js";
import Icon from "./Icon.jsx";

export function Header({ title, go, toast }) {
  return (
    <div className="pagehead">
      <button className="iconbtn" onClick={() => go("home")} aria-label="Quay lại">
        <Icon name="back" />
      </button>
      <h1>{title}</h1>
      <button
        className="iconbtn"
        aria-label="Thông tin"
        onClick={() => toast("Đây là ứng dụng demo")}
      >
        <Icon name="info" />
      </button>
    </div>
  );
}

export function Navbar({ screen, go }) {
  const backend = config.bankingSource === "mcp";
  const navigation = backend
    ? [
        ["home", "Trang chủ", "home"],
        ["assets", "Tài sản", "wallet"],
        ["history", "Giao dịch", "history"],
        ["analytics", "Phân tích", "fund"],
        ["more", "Dịch vụ", "more"],
      ]
    : config.navigation.map(([id, title]) => [id, title, id]);
  const active = ["savings", "loans"].includes(screen)
    ? "assets"
    : screen === "finance" || screen === "recipients"
      ? "more"
      : screen;
  return (
    <nav className="bottom" aria-label="Điều hướng chính">
      {navigation.map(([id, title, icon]) => (
        <button
          key={id}
          className={`navbtn ${active === id ? "active" : ""}`}
          aria-current={active === id ? "page" : undefined}
          onClick={() => go(id)}
        >
          <Icon name={icon} size={22} />
          {title}
        </button>
      ))}
    </nav>
  );
}
