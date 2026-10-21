export function dateLabel(value) {
  if (!value) return "Chưa có thông tin";
  return String(value).replace(
    /^(\d{4})-(\d{2})-(\d{2})(?:T| · )?(\d{2}:\d{2})?.*$/,
    (_, y, m, d, time) => `${d}/${m}/${y}${time ? ` · ${time}` : ""}`,
  );
}
export const searchText = (value) =>
  String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
export const compactMoney = (value) =>
  `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(value / 1000000)} tr`;
export function monthOffset(month, offset) {
  const [y, m] = month.split("-").map(Number);
  const date = new Date(y, m - 1 + offset, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}
