import { config } from "../lib/config.js";
import Icon from "./Icon.jsx";

export default function TransferMethods({ screen, go, service }) {
  return (
    <nav className="transfer-methods" aria-label="Hình thức chuyển tiền">
      {config.transferMethods.map(([id, label, icon]) => (
        <button
          key={id}
          className={`transfer-method ${screen === id ? "active" : ""}`}
          aria-current={screen === id ? "page" : undefined}
          onClick={() => (id === "transfer" ? service("transfer") : go(id))}
        >
          <Icon name={icon} size={20} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
