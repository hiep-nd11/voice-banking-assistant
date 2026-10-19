import Icon from "./Icon.jsx";
import { services } from "../lib/data.js";

export default function Services({ service, colorful = false }) {
  return (
    <div className="actions">
      {services.map(([id, label, icon], i) => (
        <button key={id} className="action" onClick={() => service(id)}>
          <span
            className={`glyph ${colorful ? ["", "blue", "gold", "purple"][i % 4] : ""}`}
          >
            <Icon name={icon} size={25} />
          </span>
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
