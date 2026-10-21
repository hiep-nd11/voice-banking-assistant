import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import base from "../../public/app-config.json";
import { configureApp, config, maskedAccount } from "../lib/config.js";
import { loadBankingData } from "../lib/banking.js";
import App from "../App.jsx";

afterEach(() => {
  vi.unstubAllGlobals();
  configureApp(structuredClone(base));
});
const overview = {
  source: "mcp",
  profile: { full_name: "Khách hàng từ MCP" },
  accounts: [{ account_id: "TK1", type: "payment", account_number: "****5601", balance: 28201022 }],
  transactions: [
    {
      txn_id: 1,
      time: "2026-10-21T09:00",
      amount: 100000,
      direction: "in",
      counterparty: "Lương MCP",
    },
  ],
};

it("hydrates profile, payment account and transaction direction from backend", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => overview })),
  );
  await loadBankingData(structuredClone(base));
  expect(fetch).toHaveBeenCalledWith("/api/banking/overview", { cache: "no-store" });
  expect(config.user).toMatchObject({
    name: "Khách hàng từ MCP",
    balance: 28201022,
    id: "mcp:TK1",
  });
  expect(maskedAccount()).toBe("****5601");
  expect(config.transactions[0]).toMatchObject({ name: "Lương MCP", amt: 100000, in: true });
});

it("rejects missing payment accounts and malformed amounts instead of showing demo", async () => {
  for (const data of [
    { ...overview, accounts: [] },
    { ...overview, transactions: [{ ...overview.transactions[0], amount: "100000" }] },
  ]) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => data })),
    );
    await expect(loadBankingData(structuredClone(base))).rejects.toThrow("không hợp lệ");
  }
});

it("reports backend outages and supports explicit demo mode", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status: 502 })),
  );
  await expect(loadBankingData(structuredClone(base))).rejects.toThrow("HTTP 502");
  const demo = structuredClone(base);
  demo.api.dataSource = "demo";
  expect(await loadBankingData(demo)).toBe(demo);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("shows the backend profile and prevents demo bills from changing its balance", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => overview })),
  );
  await loadBankingData(structuredClone(base));
  const user = userEvent.setup();
  render(<App />);
  expect(screen.getByText(/Khách hàng từ MCP/)).toBeTruthy();
  expect(screen.getByText("28.201.022 ₫")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Thanh toán HĐ", exact: true }));
  await user.click(screen.getByRole("button", { name: base.mockServices.bill.action }));
  expect(screen.getByRole("alert").textContent).toContain("Backend chưa hỗ trợ");
  await user.click(screen.getByRole("button", { name: "Trang chủ", exact: true }));
  expect(screen.getByText("28.201.022 ₫")).toBeTruthy();
});

const portfolio = {
  ...overview,
  as_of: "2026-10-22T09:00",
  accounts: [
    ...overview.accounts,
    {
      account_id: "TK2",
      type: "savings",
      name: "Sổ tiết kiệm 12 tháng",
      account_number: "****5602",
      balance: 180000000,
      interest_rate: 5,
      term_months: 12,
      maturity_date: "2026-10-28",
      days_to_maturity: 6,
    },
    {
      account_id: "TK3",
      type: "savings",
      name: "Tiết kiệm online 6 tháng",
      account_number: "****5603",
      balance: 50000000,
      interest_rate: 4.4,
      term_months: 6,
      maturity_date: "2026-12-15",
      days_to_maturity: 54,
    },
    {
      account_id: "TK4",
      type: "loan",
      name: "Khoản vay mua ô tô",
      account_number: "****5605",
      outstanding: 263658000,
      interest_rate: 8.9,
      monthly_payment: 9350000,
      next_payment_date: "2026-11-15",
      maturity_date: "2029-06-15",
      parent_account_id: "TK1",
    },
  ],
};

it("keeps home compact and groups savings and loans under the Assets tab", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => portfolio })),
  );
  await loadBankingData(structuredClone(base));
  expect(config.bankingAccounts).toHaveLength(4);
  const user = userEvent.setup();
  render(<App />);
  expect(screen.queryByText("Sổ tiết kiệm 12 tháng")).toBeNull();
  expect(screen.queryByText("Khoản vay mua ô tô")).toBeNull();
  for (const label of ["Trang chủ", "Tài sản", "Giao dịch", "Phân tích", "Dịch vụ"])
    expect(screen.getByRole("navigation", { name: "Điều hướng chính" }).textContent).toContain(
      label,
    );
  await user.click(screen.getByRole("button", { name: "Tài sản", exact: true }));
  expect(
    screen.getByRole("button", { name: "Tài sản", exact: true }).getAttribute("aria-current"),
  ).toBe("page");
  expect(screen.getByText("258.201.022 ₫")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Sổ tiết kiệm 12 tháng" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Tiết kiệm", exact: true }));
  expect(screen.getByText("230.000.000 ₫")).toBeTruthy();
  expect(screen.getByText("180.000.000 ₫")).toBeTruthy();
  expect(screen.getByText("50.000.000 ₫")).toBeTruthy();
  expect(screen.getByText("28/10/2026")).toBeTruthy();
  expect(screen.getByText("Còn 6 ngày đến hạn")).toBeTruthy();
  expect(screen.getByText("4,4%/năm")).toBeTruthy();
  expect(screen.queryByText("Khoản vay mua ô tô")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Ẩn số tiền" }));
  for (const amount of [
    "230.000.000 ₫",
    "180.000.000 ₫",
    "50.000.000 ₫",
    "263.658.000 ₫",
    "9.350.000 ₫",
  ])
    expect(screen.queryByText(amount)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Hiện số tiền" }));
  await user.click(screen.getByRole("button", { name: "Khoản vay", exact: true }));
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Tài sản của tôi");
  expect(screen.getByText("Khoản vay mua ô tô")).toBeTruthy();
  expect(screen.getByText("15/11/2026")).toBeTruthy();
  expect(screen.getByText("9.350.000 ₫")).toBeTruthy();
  expect(screen.getByText("15/06/2029")).toBeTruthy();
  expect(screen.getByText("TK1")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Tiết kiệm", exact: true }));
  expect(screen.getByText("Sổ tiết kiệm 12 tháng")).toBeTruthy();
  expect(screen.queryByText("Khoản vay mua ô tô")).toBeNull();
});

it("refreshes payment, savings, loan and transaction data together", async () => {
  const fetch = vi.fn(async () => ({ ok: true, json: async () => portfolio }));
  vi.stubGlobal("fetch", fetch);
  await loadBankingData(structuredClone(base));
  render(<App />);
  const updated = structuredClone(portfolio);
  updated.accounts[0].balance = 12345000;
  updated.accounts[1].balance = 190000000;
  updated.accounts[3].outstanding = 250000000;
  updated.transactions[0].counterparty = "Giao dịch mới từ BE";
  fetch.mockResolvedValue({ ok: true, json: async () => updated });
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Tài sản", exact: true }));
  await user.click(screen.getByRole("button", { name: "Cập nhật", exact: true }));
  expect(await screen.findByText("12.345.000 ₫")).toBeTruthy();
  expect(screen.getByText("240.000.000 ₫")).toBeTruthy();
  expect(screen.getAllByText("250.000.000 ₫")).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "Trang chủ", exact: true }));
  expect(screen.getByText("Giao dịch mới từ BE")).toBeTruthy();
});

it("does not accept malformed savings or loan amounts", async () => {
  for (const index of [1, 3]) {
    const broken = structuredClone(portfolio);
    broken.accounts[index][index === 3 ? "outstanding" : "balance"] = "unknown";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => broken })),
    );
    await expect(loadBankingData(structuredClone(base))).rejects.toThrow("không hợp lệ");
  }
});

it("preserves normal, quick and QR transfer screens in backend mode", async () => {
  configureApp({ ...structuredClone(base), bankingSource: "mcp", bankingAccounts: [] });
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Chuyển tiền", exact: true }));
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Chuyển tiền");
  expect(screen.getByLabelText("Số tài khoản")).toBeTruthy();
  expect(screen.getByRole("navigation", { name: "Hình thức chuyển tiền" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }));
  expect(screen.getByRole("button", { name: "Thêm người nhận" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Quét QR", exact: true }));
  expect(screen.getByText("Quét QR chuyển khoản")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Chuyển tiền thường", exact: true }));
  expect(screen.getByLabelText("Số tài khoản").value).toBe("");
  expect(screen.queryByLabelText("Chức năng tài chính")).toBeNull();
});
