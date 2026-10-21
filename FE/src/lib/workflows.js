export const workflowScreens = new Set([
  "home",
  "transfer",
  "recipients",
  "qr",
  "workflow",
  "assets",
  "savings",
  "loans",
  "history",
  "analytics",
  "finance",
]);
export const workflowFeatures = new Set([
  "budget",
  "month",
  "spending",
  "income",
  "trend",
  "transactions",
  "recent",
  "alerts",
  "products",
]);

export function allowedNavigation(event) {
  return (
    event.type === "ui_action" &&
    event.action === "navigate" &&
    workflowScreens.has(event.screen) &&
    (event.screen !== "finance" || workflowFeatures.has(event.feature))
  );
}

export const workflowTitle = (intent) =>
  ({
    transfer_account: "Chuyển tiền",
    transfer_qr: "Chuyển tiền bằng QR",
    transfer_recipient: "Chuyển tiền",
    open_savings: "Chuẩn bị gửi tiết kiệm",
    open_loan: "Chuẩn bị đăng ký vay",
  })[intent] || "Yêu cầu đang thực hiện";
