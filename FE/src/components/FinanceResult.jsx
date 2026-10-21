import { money } from "../lib/transfer.js";
import { dateLabel } from "../lib/format.js";
import { fieldLabels, valueLabels } from "../lib/finance.js";

const labels = {
  ...fieldLabels,
  full_name: "Họ và tên",
  salutation: "Cách xưng hô",
  age: "Tuổi",
  city: "Thành phố",
  occupation: "Nghề nghiệp",
  accessibility_needs: "Nhu cầu hỗ trợ",
  accounts: "Các tài khoản",
  account_id: "Mã tài khoản",
  type: "Loại",
  account_number: "Số tài khoản",
  parent_account_id: "Tài khoản liên kết",
  balance: "Số dư",
  outstanding: "Dư nợ",
  monthly_payment: "Số tiền trả mỗi kỳ",
  next_payment_date: "Ngày trả tiếp theo",
  interest_rate: "Lãi suất (%/năm)",
  maturity_date: "Ngày đến hạn",
  days_to_maturity: "Số ngày đến hạn",
  total_payment: "Tổng tiền thanh toán",
  total_savings: "Tổng tiết kiệm",
  as_of: "Cập nhật tại",
  items: "Chi tiết",
  matches: "Người nhận phù hợp",
  relationship: "Quan hệ",
  bank: "Ngân hàng",
  time: "Thời gian",
  txn_id: "Mã giao dịch",
  category_code: "Mã danh mục",
  description: "Nội dung",
  counterparty: "Đối tác",
  account: "Tài khoản",
  total_income: "Tổng thu",
  total_spending: "Tổng chi",
  net: "Chênh lệch thu chi",
  top_categories: "Nhóm chi nhiều nhất",
  label: "Tên",
  code: "Mã",
  total: "Tổng tiền",
  count: "Số lượng",
  share_pct: "Tỷ trọng (%)",
  until: "Tính đến ngày",
  is_partial_month: "Tháng chưa kết thúc",
  prev_month_spending_same_period: "Chi cùng kỳ tháng trước",
  spending_change_pct: "Thay đổi chi tiêu (%)",
  transaction_count: "Số giao dịch",
  period_a: "Kỳ trước",
  period_b: "Kỳ sau",
  total_a: "Tổng chi kỳ trước",
  total_b: "Tổng chi kỳ sau",
  a: "Kỳ trước",
  b: "Kỳ sau",
  diff: "Chênh lệch",
  change_pct: "Thay đổi (%)",
  series: "Theo tháng",
  avg_previous: "Trung bình trước đây",
  current: "Tháng hiện tại",
  reasons: "Lý do cần chú ý",
  severity: "Mức độ",
  disclaimer: "Lưu ý",
  product_code: "Mã sản phẩm",
  interest_rate_mock: "Lãi suất tham khảo (%/năm)",
  max_amount: "Số tiền tối đa",
  max_term_months: "Kỳ hạn tối đa (tháng)",
  channel: "Kênh đăng ký",
  plan: "Phân bổ",
  needs: "Thiết yếu · 50%",
  wants: "Mong muốn · 30%",
  savings: "Tích lũy · 20%",
  target: "Mục tiêu",
  current_avg: "Trung bình hiện tại",
  includes: "Bao gồm",
  adjustments: "Gợi ý điều chỉnh",
  window: "Khoảng dữ liệu",
  rule: "Nguyên tắc",
  ok: "Đọc số tiền thành công",
  reason: "Lý do",
  amount_words: "Số tiền bằng lời",
  risk_level: "Mức rủi ro",
  matched_scam_keywords: "Từ khóa cần chú ý",
  insufficient_balance: "Không đủ số dư",
  ui_action: "Yêu cầu",
  screen: "Dịch vụ",
  expires_at: "Hết hạn lúc",
  prefill: "Thông tin đã điền",
  required_user_inputs: "Thông tin cần hoàn tất",
  risk: "Kết quả kiểm tra rủi ro",
  source_account: "Tài khoản nguồn",
  estimated_interest: "Lãi dự kiến",
  beneficiary: "Người nhận",
  today: "Ngày dữ liệu",
  weekday: "Thứ",
  this_week_start: "Đầu tuần dữ liệu",
  last_week: "Tuần trước",
  this_month_start: "Đầu tháng dữ liệu",
  last_month: "Tháng trước",
  this_year_start: "Đầu năm dữ liệu",
};
const amounts = new Set([
  "amount",
  "min_amount",
  "max_amount",
  "balance",
  "outstanding",
  "monthly_payment",
  "total_payment",
  "total_savings",
  "total_income",
  "total_spending",
  "net",
  "total",
  "prev_month_spending_same_period",
  "total_a",
  "total_b",
  "a",
  "b",
  "diff",
  "avg_previous",
  "current",
  "monthly_income",
  "target",
  "current_avg",
  "estimated_interest",
]);

function Value({ value, name = "" }) {
  if (value === null || value === undefined) return <span>Chưa có thông tin</span>;
  if (typeof value === "boolean") return <span>{value ? "Có" : "Không"}</span>;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value))
    return <span>{dateLabel(value)}</span>;
  if (typeof value !== "object")
    return (
      <span>
        {typeof value === "number" && amounts.has(name)
          ? money(value)
          : valueLabels[value] || String(value)}
      </span>
    );
  if (Array.isArray(value))
    return value.length ? (
      <div className="finance-list">
        {value.map((row, i) => (
          <div className="finance-item" key={i}>
            <Value value={row} name={name} />
          </div>
        ))}
      </div>
    ) : (
      <p className="note">Không có kết quả.</p>
    );
  return (
    <dl className="finance-details">
      {Object.entries(value)
        .filter(
          ([key]) => !["speech", "speech_hint", "executed"].includes(key) && !key.endsWith("_text"),
        )
        .map(([key, row]) => (
          <div
            key={key}
            className={typeof row === "object" && row !== null ? "finance-nested" : "finance-pair"}
          >
            <dt>{labels[key] || key.replaceAll("_", " ")}</dt>
            <dd>
              <Value value={row} name={key} />
            </dd>
          </div>
        ))}
    </dl>
  );
}

export default function FinanceResult({ data }) {
  return (
    <section className="finance-result" aria-label="Kết quả tra cứu">
      {data.executed === false && (
        <p className="finance-notice" role="status">
          Đã chuẩn bị yêu cầu. Chưa thực hiện giao dịch.
        </p>
      )}
      {data.speech && <p className="finance-summary">{data.speech}</p>}
      {data.series?.length > 0 && (
        <div className="finance-bars" aria-label="Biểu đồ theo tháng">
          {data.series.map((row) => (
            <div key={row.month}>
              <span>
                {row.month} · {money(row.total)}
              </span>
              <meter
                min="0"
                max={Math.max(1, ...data.series.map((r) => r.total))}
                value={row.total}
              />
            </div>
          ))}
        </div>
      )}
      <Value value={data} />
    </section>
  );
}
