import { config } from "./config.js";

export async function financeRequest(path, args, signal) {
  const response = await fetch(
    `${(config.api?.baseUrl || "").replace(/\/$/, "")}/api/banking/${path}`,
    {
      signal,
      cache: "no-store",
      ...(args === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(args),
          }),
    },
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Không tải được dữ liệu (HTTP ${response.status}).`,
    );
  return data;
}

export const fieldLabels = {
  date_from: "Từ ngày",
  date_to: "Đến ngày",
  a_from: "Kỳ trước: từ ngày",
  a_to: "Kỳ trước: đến ngày",
  b_from: "Kỳ sau: từ ngày",
  b_to: "Kỳ sau: đến ngày",
  month: "Tháng",
  category: "Danh mục",
  keyword: "Từ khóa",
  direction: "Chiều giao dịch",
  min_amount: "Số tiền tối thiểu (VND)",
  limit: "Số kết quả tối đa",
  top: "Số nhóm hiển thị",
  group_by: "Nhóm theo",
  months: "Số tháng",
  product_type: "Loại sản phẩm",
  term_months: "Kỳ hạn (tháng)",
  monthly_income: "Thu nhập hàng tháng (VND)",
  goal: "Mục tiêu",
  name: "Tên hoặc cách gọi người nhận",
  text: "Số tiền bằng lời (ví dụ: 500k)",
  amount: "Số tiền (VND)",
  beneficiary_id: "Người nhận",
  note: "Nội dung",
  loan_type: "Loại khoản vay",
  risk_acknowledged: "Tôi đã đọc cảnh báo và vẫn muốn chuẩn bị yêu cầu",
  action_id: "Mã yêu cầu",
};
export const valueLabels = {
  in: "Tiền vào",
  out: "Tiền ra",
  category: "Danh mục",
  month: "Tháng",
  merchant: "Nơi chi tiêu",
  group: "Nhóm nhu cầu",
  savings: "Tiết kiệm",
  loan: "Khoản vay",
  payment: "Thanh toán",
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  app: "Trên ứng dụng",
  branch: "Tại chi nhánh",
  navigate: "Yêu cầu đã chuẩn bị",
  close: "Đã hủy",
  transfer: "Chuyển tiền",
  savings_open: "Gửi tiết kiệm",
  loan_apply: "Đăng ký vay",
};

export function initialValues(schema, calendar) {
  const values = {};
  for (const [key, prop] of Object.entries(schema.properties || {}))
    values[key] = prop.default ?? "";
  for (const key of ["date_from", "b_from"])
    if (key in values) values[key] = calendar.this_month_start || "";
  for (const key of ["date_to", "b_to"]) if (key in values) values[key] = calendar.today || "";
  if ("a_from" in values) values.a_from = calendar.last_month?.[0] || "";
  if ("a_to" in values) values.a_to = calendar.last_month?.[1] || "";
  if ("month" in values) values.month = calendar.today?.slice(0, 7) || "";
  return values;
}

export function serializeFields(schema, values) {
  return Object.fromEntries(
    Object.entries(schema.properties || {}).flatMap(([key, prop]) => {
      const value = values[key];
      if (value === "" || value === undefined || value === null) return [];
      const type = prop.type || prop.anyOf?.find((s) => s.type !== "null")?.type;
      return [[key, ["integer", "number"].includes(type) ? Number(value) : value]];
    }),
  );
}
