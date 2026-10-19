import { config } from "../lib/config.js";
import Icon from "./Icon.jsx";

export function Header({ title, go, toast }) {
  return (
    <div className="pagehead">
      <button
        className="iconbtn"
        onClick={() => go("home")}
        aria-label="Quay lại"
      >
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
  return (
    <nav className="bottom">
      {config.navigation.map(([id, title]) => (
        <button
          key={id}
          className={`navbtn ${screen === id ? "active" : ""}`}
          onClick={() => go(id)}
        >
          <Icon name={id} size={22} />
          {title}
        </button>
      ))}
    </nav>
  );
}
