import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { mockServices } from "../lib/mockServices.js";

export default function MockService({ id, go }) {
  const config = mockServices[id];
  const [values, setValues] = useState(() =>
    Object.fromEntries(
      config.fields.map((f) => [f.key, f.value ?? f.options?.[0] ?? ""]),
    ),
  );
  const [result, setResult] = useState(false);
  const [error, setError] = useState("");
  function submit(e) {
    e.preventDefault();
    if (id === "plane" && values.from === values.to)
      return setError("Điểm đi và điểm đến phải khác nhau.");
    setError("");
    setResult(true);
  }
  return (
    <div className="page">
      <div
        className="pill"
        style={{ display: "inline-block", marginBottom: 16 }}
      >
        DỊCH VỤ DEMO
      </div>
      <div className="section-title">{config.description}</div>
      <p className="note">
        Dữ liệu mô phỏng, không phát sinh thanh toán hoặc đăng ký thực tế.
      </p>
      {result ? (
        <div className="mock-result" role="status">
          <div className="successmark">
            <Icon name="check" size={36} />
          </div>
          <h2>{config.result}</h2>
          {config.fields.map((f) => (
            <div className="confirmrow" key={f.key}>
              <span>{f.label}</span>
              <b>{values[f.key]}</b>
            </div>
          ))}
          <button className="cta secondary" onClick={() => setResult(false)}>
            Thực hiện lại
          </button>
          <button
            className="cta"
            style={{ marginTop: 12 }}
            onClick={() => go("home")}
          >
            Về trang chủ
          </button>
        </div>
      ) : (
        <form onSubmit={submit}>
          {config.fields.map((f) => (
            <div className="field" key={f.key}>
              <label className="label" htmlFor={`mock-${f.key}`}>
                {f.label}
              </label>
              {f.options ? (
                <select
                  className="input"
                  id={`mock-${f.key}`}
                  value={values[f.key]}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.key]: e.target.value }))
                  }
                >
                  {f.options.map((option) => (
                    <option key={option}>{option}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  id={`mock-${f.key}`}
                  type={f.type || "text"}
                  inputMode={f.inputMode}
                  min={f.min}
                  pattern={f.pattern}
                  required
                  value={values[f.key]}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [f.key]: e.target.value }))
                  }
                />
              )}
            </div>
          ))}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="cta" type="submit">
            {config.action}
          </button>
        </form>
      )}
    </div>
  );
}
