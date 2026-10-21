import { configureApp } from "./config.js";
import { dateLabel } from "./format.js";

export async function loadBankingData(config) {
  if (config.api?.dataSource !== "backend") return config;
  const base = (config.api.baseUrl || "").replace(/\/$/, "");
  const response = await fetch(`${base}/api/banking/overview`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Không tải được dữ liệu ngân hàng (HTTP ${response.status}).`);
  const data = await response.json();
  const account = data.accounts?.find((a) => a.type === "payment");
  if (
    !data.profile?.full_name ||
    !account?.account_id ||
    !account.account_number ||
    !Number.isSafeInteger(account.balance) ||
    !Array.isArray(data.transactions)
  ) {
    throw new Error("Dữ liệu tài khoản từ backend không hợp lệ.");
  }
  const transactions = data.transactions.map((row) => {
    if (
      !Number.isSafeInteger(row.amount) ||
      row.amount < 0 ||
      !["in", "out"].includes(row.direction) ||
      !row.time ||
      !(row.counterparty || row.description || row.category)
    ) {
      throw new Error("Dữ liệu giao dịch từ backend không hợp lệ.");
    }
    return {
      id: row.txn_id,
      name: row.counterparty || row.description || row.category,
      date: dateLabel(row.time),
      time: row.time,
      category: row.category,
      amt: row.amount,
      in: row.direction === "in",
    };
  });
  for (const row of data.accounts) {
    const amount = row.type === "loan" ? row.outstanding : row.balance;
    if (["payment", "savings", "loan"].includes(row.type) && !Number.isSafeInteger(amount)) {
      throw new Error("Dữ liệu số dư hoặc dư nợ từ backend không hợp lệ.");
    }
  }
  return configureApp({
    ...config,
    bankingSource: "mcp",
    bankingAsOf: data.as_of,
    bankingAccounts: data.accounts,
    user: {
      ...config.user,
      id: `mcp:${account.account_id}`,
      name: data.profile.full_name,
      account: account.account_number,
      balance: account.balance,
    },
    transactions,
  });
}
