import { useEffect, useState } from "react";
import { financeRequest } from "../lib/finance.js";
import { compactMoney, dateLabel, monthOffset } from "../lib/format.js";
import { money } from "../lib/transfer.js";

async function loadMonth(month, signal) {
  const data = await financeRequest("features/month", { month }, signal);
  if (![data.total_income, data.total_spending].every(Number.isFinite))
    throw new Error("Dữ liệu thu chi chưa hợp lệ. Vui lòng thử lại.");
  return data;
}

export default function Analytics({ openFinance }) {
  const [month, setMonth] = useState("");
  const [data, setData] = useState(null);
  const [series, setSeries] = useState([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    if (month) return;
    const abort = new AbortController();
    financeRequest("features/calendar", {}, abort.signal)
      .then((dates) => {
        if (!abort.signal.aborted) setMonth(dates.today.slice(0, 7));
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(e.message);
          setBusy(false);
        }
      });
    return () => abort.abort();
  }, [retry]);
  useEffect(() => {
    if (!month) return;
    const abort = new AbortController();
    setBusy(true);
    setError("");
    setData(null);
    setSeries([]);
    loadMonth(month, abort.signal)
      .then((current) => {
        if (abort.signal.aborted) return;
        setData(current);
        setBusy(false);
        Promise.all(
          Array.from({ length: 5 }, (_, i) => monthOffset(month, i - 5)).map(async (period) => {
            try {
              return { ...(await loadMonth(period, abort.signal)), month: period };
            } catch {
              return { month: period, missing: true };
            }
          }),
        ).then((previous) => {
          if (!abort.signal.aborted) setSeries([...previous, { ...current, month }]);
        });
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(e.message);
          setBusy(false);
        }
      });
    return () => abort.abort();
  }, [month, retry]);
  const max = Math.max(
    1,
    ...series.flatMap((row) => [row.total_income || 0, row.total_spending || 0]),
  );
  return (
    <div className="page analytics-page">
      <div className="dashboard-heading">
        <div>
          <p className="section-kicker">DÒNG TIỀN CỦA BẠN</p>
          <h2>Tổng quan trong kỳ</h2>
        </div>
        <input
          className="month-picker"
          aria-label="Tháng phân tích"
          type="month"
          value={month}
          onChange={(e) => {
            if (e.target.value) setMonth(e.target.value);
          }}
        />
      </div>
      {busy && <p role="status">Đang tải phân tích…</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button className="filebutton" onClick={() => setRetry(retry + 1)}>
            Thử lại
          </button>
        </div>
      )}
      {data && (
        <>
          <div className="cashflow-kpis">
            <article>
              <span>Tổng thu nhập</span>
              <strong>{compactMoney(data.total_income)}</strong>
              <small>{money(data.total_income)}</small>
            </article>
            <article>
              <span>Tổng chi tiêu</span>
              <strong>{compactMoney(data.total_spending)}</strong>
              <small>{money(data.total_spending)}</small>
            </article>
          </div>
          <p className="list-caption">
            {data.is_partial_month
              ? `Kỳ chưa kết thúc · Số liệu đến ${dateLabel(data.until)}`
              : "Số liệu trong tháng đã chọn"}
          </p>
          <section className="dashboard-card">
            <h2>Xu hướng thu chi</h2>
            <div className="chart-legend">
              <span>● Thu nhập</span>
              <span>● Chi tiêu</span>
            </div>
            {series.length > 0 && (
              <p className="chart-scale">Thang biểu đồ: 0 – {compactMoney(max)} đồng · 6 tháng</p>
            )}
            {!series.length ? (
              <p role="status">Đang tải xu hướng 6 tháng…</p>
            ) : (
              <>
                <div className="cashflow-chart" aria-hidden="true">
                  {series.map((row) => (
                    <div className="chart-column" key={row.month}>
                      <div className="chart-bars">
                        {row.missing ? (
                          <span className="chart-missing">—</span>
                        ) : (
                          <>
                            <i style={{ height: `${(row.total_income / max) * 100}%` }} />
                            <i style={{ height: `${(row.total_spending / max) * 100}%` }} />
                          </>
                        )}
                      </div>
                      <small>T{Number(row.month.slice(5))}</small>
                    </div>
                  ))}
                </div>
                <details className="chart-table">
                  <summary>Xem số liệu biểu đồ (₫)</summary>
                  <table>
                    <thead>
                      <tr>
                        <th>Tháng</th>
                        <th>Thu nhập</th>
                        <th>Chi tiêu</th>
                      </tr>
                    </thead>
                    <tbody>
                      {series.map((row) => (
                        <tr key={row.month}>
                          <th>{row.month.split("-").reverse().join("/")}</th>
                          <td>{row.missing ? "Chưa tải được" : money(row.total_income)}</td>
                          <td>{row.missing ? "Chưa tải được" : money(row.total_spending)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
                {series.some((row) => row.missing) && (
                  <p className="note">
                    Một số tháng chưa tải được dữ liệu; dấu — biểu thị dữ liệu thiếu.
                  </p>
                )}
              </>
            )}
          </section>
          <section className="dashboard-card">
            <h2>Nhận xét</h2>
            <p>
              Thu nhập {data.total_income >= data.total_spending ? "cao hơn" : "thấp hơn"} chi tiêu{" "}
              {money(Math.abs(data.total_income - data.total_spending))} trong kỳ.
            </p>
            {data.spending_change_pct != null && (
              <p className="note">
                Chi tiêu {data.spending_change_pct >= 0 ? "tăng" : "giảm"}{" "}
                {Math.abs(data.spending_change_pct)}% so với cùng kỳ tháng trước.
              </p>
            )}
          </section>
          <section className="dashboard-card">
            <h2>Danh mục chi tiêu lớn nhất</h2>
            {(data.top_categories || []).map((row) => (
              <div className="category-summary" key={row.code || row.label}>
                <div>
                  <span>{row.label}</span>
                  <b>{money(row.total)}</b>
                </div>
                <progress
                  max={Math.max(data.total_spending, 1)}
                  value={row.total}
                  aria-label={row.label}
                />
              </div>
            ))}
            {!data.top_categories?.length && (
              <p className="note">Chưa có dữ liệu danh mục trong kỳ.</p>
            )}
          </section>
        </>
      )}
      <details className="advanced-reports">
        <summary>Báo cáo và công cụ nâng cao</summary>
        <div>
          {[
            ["spending", "Chi tiêu theo danh mục"],
            ["income", "Nguồn thu nhập"],
            ["compare", "So sánh hai kỳ"],
            ["trend", "Xu hướng danh mục"],
            ["alerts", "Giao dịch bất thường"],
            ["budget", "Lập ngân sách"],
          ].map(([id, title]) => (
            <button key={id} onClick={() => openFinance(id)}>
              {title} →
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}
