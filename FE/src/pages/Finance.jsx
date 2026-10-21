import { useEffect, useRef, useState } from "react";
import {
  fieldLabels,
  financeRequest,
  initialValues,
  serializeFields,
  valueLabels,
} from "../lib/finance.js";
import FinanceResult from "../components/FinanceResult.jsx";
import { dateLabel } from "../lib/format.js";

const pendingKey = "vtb.banking.pending";
function readPending() {
  try {
    const rows = JSON.parse(sessionStorage.getItem(pendingKey) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function Feature({ feature, calendar, beneficiaries, onPending, pending }) {
  const schema = feature.schema;
  const [values, setValues] = useState(() => initialValues(schema, calendar));
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  async function run(args) {
    if (inFlight.current) return;
    inFlight.current = true;
    const current = new AbortController();
    request.current = current;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const data = await financeRequest(
        `features/${feature.id}`,
        args,
        feature.read_only ? current.signal : undefined,
      );
      onPending(data.ui_action);
      if (!mounted.current) return;
      setResult(data);
    } catch (e) {
      if (e.name !== "AbortError" && mounted.current) setError(e.message);
    } finally {
      if (request.current === current) {
        inFlight.current = false;
        if (mounted.current) setBusy(false);
      }
    }
  }
  useEffect(() => {
    mounted.current = true;
    const defaults = initialValues(schema, calendar);
    if (
      feature.read_only &&
      (schema.required || []).every((key) => defaults[key] !== "" && defaults[key] != null)
    ) {
      void run(serializeFields(schema, defaults));
    }
    return () => {
      mounted.current = false;
      request.current?.abort();
      inFlight.current = false;
    };
  }, []);
  async function cancelAction() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const data = await financeRequest("features/cancel", {
        action_id: result.ui_action.action_id,
      });
      onPending(data.ui_action);
      if (mounted.current) setResult(data);
    } catch (e) {
      if (mounted.current) setError(e.message);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <div>
      <h2 className="section-title">{feature.title}</h2>
      {!feature.read_only && (
        <p className="finance-notice">
          Chuẩn bị hoặc hủy yêu cầu; không tự chuyển tiền, mở sổ hay giải ngân.
        </p>
      )}
      {feature.id === "products" && (
        <p className="note">Lãi suất và điều kiện là dữ liệu tham khảo phục vụ demo.</p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run(serializeFields(schema, values));
        }}
      >
        {Object.entries(schema.properties || {}).map(([key, raw]) => {
          const prop = raw.anyOf?.find((s) => s.type !== "null") || raw;
          const required = schema.required?.includes(key) || false;
          const id = `finance-${key}`;
          const update = (value) => setValues((old) => ({ ...old, [key]: value }));
          return (
            <div className="field" key={key}>
              <label className="label" htmlFor={id}>
                {fieldLabels[key] || key}
                {required ? " *" : ""}
              </label>
              {prop.type === "boolean" ? (
                <input
                  id={id}
                  type="checkbox"
                  checked={Boolean(values[key])}
                  disabled={busy}
                  onChange={(e) => update(e.target.checked)}
                />
              ) : prop.enum || key === "beneficiary_id" ? (
                <select
                  id={id}
                  className="input"
                  value={values[key]}
                  disabled={busy}
                  required={required}
                  onChange={(e) => update(e.target.value)}
                >
                  <option value="">
                    {key === "beneficiary_id" ? "Chưa chọn người nhận" : "Tất cả / mặc định"}
                  </option>
                  {key === "beneficiary_id"
                    ? beneficiaries.map((row) => (
                        <option value={row.beneficiary_id} key={row.beneficiary_id}>
                          {row.name} · {row.relationship} · {row.account_number}
                        </option>
                      ))
                    : prop.enum.map((value) => (
                        <option key={value} value={value}>
                          {valueLabels[value] || value}
                        </option>
                      ))}
                </select>
              ) : (
                <input
                  id={id}
                  className="input"
                  value={values[key]}
                  disabled={busy}
                  required={required}
                  type={
                    key === "month"
                      ? "month"
                      : /^(date_|[ab]_)(from|to)$/.test(key)
                        ? "date"
                        : ["integer", "number"].includes(prop.type)
                          ? "number"
                          : "text"
                  }
                  min={prop.minimum ?? (key === "monthly_income" ? 1 : undefined)}
                  max={prop.maximum}
                  maxLength={prop.maxLength}
                  step={prop.type === "integer" ? 1 : prop.type === "number" ? "any" : undefined}
                  list={key === "action_id" ? "pending-actions" : undefined}
                  onChange={(e) => update(e.target.value)}
                />
              )}
            </div>
          );
        })}
        <datalist id="pending-actions">
          {pending.map((row) => (
            <option key={row.action_id} value={row.action_id}>
              {valueLabels[row.screen] || row.screen}
            </option>
          ))}
        </datalist>
        <button className="cta" disabled={busy} type="submit">
          {busy
            ? "Đang xử lý…"
            : feature.read_only
              ? "Xem kết quả"
              : feature.id === "cancel"
                ? "Hủy yêu cầu"
                : "Chuẩn bị yêu cầu"}
        </button>
      </form>
      {busy && (
        <p role="status" className="note">
          Đang lấy dữ liệu…
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && <FinanceResult data={result} />}
      {result?.ui_action?.type === "navigate" && (
        <button className="cta secondary" disabled={busy} onClick={cancelAction}>
          Hủy yêu cầu vừa chuẩn bị
        </button>
      )}
    </div>
  );
}

export default function Finance({ initial = "month", mode = "all" }) {
  const [features, setFeatures] = useState([]);
  const [calendar, setCalendar] = useState(null);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [selected, setSelected] = useState(initial);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [pending, setPending] = useState(readPending);
  useEffect(() => {
    const abort = new AbortController();
    setError("");
    Promise.all([
      financeRequest("features", undefined, abort.signal),
      financeRequest("features/calendar", {}, abort.signal),
      financeRequest("features/beneficiaries", {}, abort.signal),
    ])
      .then(([catalog, dates, people]) => {
        if (abort.signal.aborted) return;
        setFeatures(catalog.features);
        setCalendar(dates);
        setBeneficiaries(people.items || []);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [retry]);
  function onPending(action) {
    if (!action?.action_id) return;
    const next = readPending().filter((row) => row.action_id !== action.action_id);
    if (action.type === "navigate") next.push(action);
    try {
      sessionStorage.setItem(pendingKey, JSON.stringify(next));
    } catch {
      /* In-memory state remains usable. */
    }
    setPending(next);
  }
  const feature = features.find((row) => row.id === selected);
  const visibleFeatures = features.filter((row) =>
    mode === "analysis"
      ? ["month", "spending", "income", "compare", "trend", "alerts", "budget"].includes(row.id)
      : mode === "transactions"
        ? ["transactions", "recent"].includes(row.id)
        : true,
  );
  return (
    <div className="page finance-page">
      <p className="note">
        Dữ liệu ngân hàng ·{" "}
        {calendar ? `Mốc dữ liệu: ${dateLabel(calendar.today)}` : "Đang kết nối…"}
      </p>
      {error && (
        <div role="alert">
          <p className="error">{error}</p>
          <button className="filebutton" onClick={() => setRetry((n) => n + 1)}>
            Thử lại
          </button>
        </div>
      )}
      {!error && !calendar && <p role="status">Đang tải các tính năng…</p>}
      {calendar && (
        <>
          <label className="label" htmlFor="finance-feature">
            {mode === "analysis"
              ? "Báo cáo của bạn"
              : mode === "transactions"
                ? "Lịch sử và tra cứu"
                : "Chức năng tài chính"}
          </label>
          <select
            className="input finance-select"
            id="finance-feature"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {visibleFeatures.map((row) => (
              <option key={row.id} value={row.id}>
                {row.title}
              </option>
            ))}
          </select>
          {pending.length > 0 && (
            <details className="finance-pending">
              <summary>Yêu cầu đã chuẩn bị trong phiên ({pending.length})</summary>
              {pending.map((row) => (
                <p className="note" key={row.action_id}>
                  {valueLabels[row.screen] || row.screen} · {row.action_id} · Hết hạn:{" "}
                  {row.expires_at}
                </p>
              ))}
            </details>
          )}
          {feature && (
            <Feature
              key={selected}
              feature={feature}
              calendar={calendar}
              beneficiaries={beneficiaries}
              onPending={onPending}
              pending={pending}
            />
          )}
        </>
      )}
    </div>
  );
}
