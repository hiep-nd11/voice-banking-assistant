import Icon from "./Icon.jsx";
import { config } from "../lib/config.js";
import { money } from "../lib/transfer.js";

export default function Transactions({ transfers, query = "", limit }) {
  const rows = [
    ...transfers.map((t) => ({
      name: t.recipient,
      date: "Vừa xong · Demo",
      amt: Number(t.amount),
    })),
    ...config.transactions,
  ].filter((t) =>
    `${t.name} ${t.date} ${money(t.amt)}`
      .toLocaleLowerCase("vi")
      .includes(query.toLocaleLowerCase("vi")),
  );
  return rows.length ? (
    rows.slice(0, limit ?? rows.length).map((t, i) => (
      <div className="tx" key={`${t.name}-${i}`}>
        <div className="txicon">
          <Icon name={t.in ? "wallet" : "transfer"} size={19} />
        </div>
        <div className="tx-info">
          <div className="tx-title">{t.name}</div>
          <div className="tx-sub">{t.date}</div>
        </div>
        <div className={`tx-money ${t.in ? "positive" : ""}`}>
          {t.in ? "+" : "−"}
          {money(t.amt)}
        </div>
      </div>
    ))
  ) : (
    <div className="empty">Không tìm thấy giao dịch.</div>
  );
}
