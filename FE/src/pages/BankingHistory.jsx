import { useEffect, useState } from "react";
import { financeRequest } from "../lib/finance.js";
import { dateLabel, searchText } from "../lib/format.js";
import { money } from "../lib/transfer.js";

export default function BankingHistory({ transfers = [] }) {
  const [rows, setRows] = useState([]);
  const [direction, setDirection] = useState("");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState(false);
  const [draft, setDraft] = useState({ date_from: "", date_to: "", min_amount: "", category: "" });
  const [applied, setApplied] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    financeRequest("features/calendar", {}, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted)
          setDraft((old) => ({
            ...old,
            date_from: old.date_from || data.this_month_start,
            date_to: old.date_to || data.today,
          }));
      })
      .catch(() => {});
    return () => abort.abort();
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    setBusy(true);
    setError("");
    setRows([]);
    const args = applied ? { ...applied, limit: 50 } : { limit: 20 };
    if (direction) args.direction = direction;
    financeRequest(`features/${applied ? "transactions" : "recent"}`, args, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted)
          setRows([...(data.items || [])].sort((a, b) => b.time.localeCompare(a.time)));
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [applied, direction, retry]);
  const visible = rows.filter((row) =>
    searchText(`${row.counterparty} ${row.description} ${row.category} ${row.amount}`).includes(
      searchText(query),
    ),
  );
  const groups = visible.reduce((days, row) => {
    (days[row.time.slice(0, 10)] ||= []).push(row);
    return days;
  }, {});
  return (
    <div className="page history-page">
      {transfers.length > 0 && (
        <section className="transaction-day">
          <h2>Giao dịch mô phỏng trong phiên ({transfers.length})</h2>
          {transfers.map((row, i) => (
            <article className="history-row" key={i}>
              <div>
                <b>{row.recipient}</b>
                <small>{dateLabel(row.time)} · Mô phỏng</small>
              </div>
              <strong>−{money(Number(row.amount))}</strong>
            </article>
          ))}
        </section>
      )}
      <div className="search-toolbar">
        <input
          className="input"
          aria-label="Tìm giao dịch"
          placeholder="Tìm tên, nội dung giao dịch…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          className="filter-button"
          aria-expanded={filters}
          onClick={() => setFilters(!filters)}
        >
          ☷ Bộ lọc{applied ? " •" : ""}
        </button>
      </div>
      <div className="segmented" role="group" aria-label="Chiều giao dịch">
        {[
          ["", "Tất cả"],
          ["out", "Tiền ra"],
          ["in", "Tiền vào"],
        ].map(([id, label]) => (
          <button
            key={id}
            aria-pressed={direction === id}
            className={direction === id ? "selected" : ""}
            onClick={() => setDirection(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {filters && (
        <form
          className="filter-panel"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(
              Object.fromEntries(
                Object.entries(draft)
                  .filter(([, v]) => v !== "")
                  .map(([k, v]) => [k, k === "min_amount" ? Number(v) : v]),
              ),
            );
            setFilters(false);
          }}
        >
          <h2>Bộ lọc nâng cao</h2>
          {[
            ["date_from", "Từ ngày", "date"],
            ["date_to", "Đến ngày", "date"],
            ["min_amount", "Số tiền tối thiểu (₫)", "number"],
            ["category", "Danh mục", "text"],
          ].map(([id, label, type]) => (
            <label className="field" key={id}>
              {label}
              <input
                className="input"
                type={type}
                required={type === "date"}
                min={type === "number" ? 0 : id === "date_to" ? draft.date_from : undefined}
                max={id === "date_from" ? draft.date_to : undefined}
                value={draft[id]}
                onChange={(e) => setDraft({ ...draft, [id]: e.target.value })}
              />
            </label>
          ))}
          <button className="cta">Áp dụng</button>
        </form>
      )}
      <div className="list-caption">
        <span>
          {applied
            ? `${dateLabel(applied.date_from)} – ${dateLabel(applied.date_to)}`
            : "20 giao dịch gần nhất"}
        </span>
        {applied && (
          <button className="link" onClick={() => setApplied(null)}>
            Xóa bộ lọc
          </button>
        )}
      </div>
      {busy && <p role="status">Đang tải giao dịch…</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button className="filebutton" onClick={() => setRetry(retry + 1)}>
            Thử lại
          </button>
        </div>
      )}
      {!busy && !error && !visible.length && (
        <p className="empty">Không tìm thấy giao dịch phù hợp.</p>
      )}
      {Object.entries(groups).map(([day, items]) => (
        <section className="transaction-day" key={day}>
          <h2>{dateLabel(day)}</h2>
          {items.map((row) => (
            <article className="history-row" key={row.txn_id}>
              <span className={`direction-icon ${row.direction}`}>
                {row.direction === "in" ? "↙" : "↗"}
              </span>
              <div>
                <b>{row.counterparty || row.description || row.category}</b>
                <small>
                  {row.time.slice(11, 16)} · {row.category}
                </small>
              </div>
              <strong className={row.direction === "in" ? "positive" : ""}>
                {row.direction === "in" ? "+" : "−"}
                {money(row.amount)}
              </strong>
            </article>
          ))}
        </section>
      ))}
      {!busy && !error && (
        <p className="note">
          {applied
            ? "Hiển thị tối đa 50 giao dịch. Thu hẹp khoảng ngày để xem chi tiết hơn."
            : "Dùng bộ lọc để tìm giao dịch trong khoảng thời gian khác."}{" "}
          Tìm kiếm áp dụng trên các giao dịch đã tải.
        </p>
      )}
    </div>
  );
}
