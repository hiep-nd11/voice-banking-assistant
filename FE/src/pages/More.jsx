import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { config } from "../lib/config.js";
import { searchText } from "../lib/format.js";

export default function More({ service, openFinance }) {
  const utilities =
    config.bankingSource === "mcp"
      ? [
          ["beneficiaries", "Danh bạ ngân hàng", "user"],
          ["products", "Sản phẩm & lãi suất", "save"],
          ["risk", "Kiểm tra rủi ro", "shield"],
          ["profile", "Hồ sơ của tôi", "user"],
        ]
      : [];
  const items = [...config.services.filter(([id]) => id !== "more"), ...utilities];
  const storageKey = `vtb.favorite-services.v1:${config.user.id}`;
  const [query, setQuery] = useState("");
  const [storageError, setStorageError] = useState(false);
  const [favorites, setFavorites] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
      return Array.isArray(saved) ? saved.filter((id) => items.some(([key]) => key === id)) : [];
    } catch {
      return [];
    }
  });
  function toggle(id) {
    const next = favorites.includes(id)
      ? favorites.filter((key) => key !== id)
      : [...favorites, id];
    setFavorites(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }
  const matches = items.filter(([, label]) => searchText(label).includes(searchText(query)));
  function cards(rows) {
    return (
      <div className="service-catalog">
        {rows.map(([id, label, icon]) => (
          <article key={id}>
            <button
              className="service-open"
              onClick={() =>
                utilities.some(([key]) => key === id) ? openFinance(id) : service(id)
              }
            >
              <Icon name={icon} size={23} />
              <span>{label}</span>
            </button>
            <button
              className="favorite-toggle"
              aria-label={`Yêu thích: ${label}`}
              aria-pressed={favorites.includes(id)}
              onClick={() => toggle(id)}
            >
              {favorites.includes(id) ? "★" : "☆"}
            </button>
          </article>
        ))}
      </div>
    );
  }
  return (
    <div className="page services-page">
      <label className="label" htmlFor="service-search">
        Tìm kiếm dịch vụ
      </label>
      <input
        id="service-search"
        className="input"
        placeholder="Chuyển tiền, tiết kiệm, thẻ…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {!query && (
        <section>
          <h2 className="section-title">Dịch vụ yêu thích</h2>
          {favorites.length ? (
            cards(items.filter(([id]) => favorites.includes(id)))
          ) : (
            <p className="favorite-empty">Nhấn ☆ cạnh dịch vụ để thêm vào đây.</p>
          )}
          <p className="note">
            Lưu trên trình duyệt này.
            {storageError
              ? " Không thể lưu lâu dài; thay đổi chỉ có hiệu lực trong lần mở hiện tại."
              : ""}
          </p>
        </section>
      )}
      <h2 className="section-title">
        {query ? `Kết quả tìm kiếm (${matches.length})` : "Tất cả dịch vụ"}
      </h2>
      {matches.length ? cards(matches) : <p className="empty">Không tìm thấy dịch vụ phù hợp.</p>}
      <div className="insight">
        <Icon name="shield" size={25} />
        <div>
          <b>Môi trường mô phỏng</b>
          <p>Không kết nối Core Banking, không phát sinh giao dịch tiền thật.</p>
        </div>
      </div>
    </div>
  );
}
