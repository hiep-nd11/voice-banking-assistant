import { useState } from "react";
import Transactions from "../components/Transactions.jsx";

export default function History({ transfers }) {
  const [query, setQuery] = useState("");
  return (
    <div className="page">
      <div className="field">
        <label className="label" htmlFor="searchtx">
          Tìm giao dịch
        </label>
        <input
          id="searchtx"
          className="input"
          placeholder="Nhập người nhận, tên cửa hàng..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <Transactions transfers={transfers} query={query} />
    </div>
  );
}
