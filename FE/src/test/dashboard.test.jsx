import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BankingHistory from "../pages/BankingHistory.jsx";
import Analytics from "../pages/Analytics.jsx";
import More from "../pages/More.jsx";
import App from "../App.jsx";
import { dateLabel, monthOffset } from "../lib/format.js";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});
function backend(handler) {
  const fetcher = vi.fn(async (url, options) => ({
    ok: true,
    json: async () =>
      url.endsWith("/calendar")
        ? { today: "2026-10-22", this_month_start: "2026-10-01" }
        : handler(url, JSON.parse(options.body)),
  }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
it("groups history by date and sends direction, date, amount and category filters", async () => {
  const fetcher = backend(() => ({
    items: [
      {
        txn_id: 1,
        time: "2026-10-22T07:26",
        amount: 44000,
        direction: "out",
        category: "Ăn uống",
        counterparty: "Bánh mì",
      },
    ],
  }));
  const user = userEvent.setup();
  render(<BankingHistory />);
  expect(await screen.findByText("Bánh mì")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "22/10/2026" })).toBeTruthy();
  expect(screen.getByText("−44.000 ₫")).toBeTruthy();
  expect(screen.queryByLabelText("Từ ngày")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Tiền ra" }));
  await user.click(screen.getByRole("button", { name: /Bộ lọc/ }));
  await user.type(screen.getByLabelText("Số tiền tối thiểu (₫)"), "40000");
  await user.type(screen.getByLabelText("Danh mục"), "dining");
  await user.click(screen.getByRole("button", { name: "Áp dụng" }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/transactions") && JSON.parse(options.body).min_amount === 40000,
      ),
    ).toBe(true),
  );
  expect(JSON.parse(fetcher.mock.calls.at(-1)[1].body)).toEqual({
    date_from: "2026-10-01",
    date_to: "2026-10-22",
    category: "dining",
    min_amount: 40000,
    limit: 50,
    direction: "out",
  });
});
it("uses backend totals and preserves missing trend months instead of inventing zeroes", async () => {
  backend((url, args) => {
    if (args.month === "2026-08") throw new Error("Unavailable");
    return {
      month: args.month,
      total_income: 63000000,
      total_spending: 59327640,
      until: "2026-10-22",
      is_partial_month: true,
      top_categories: [{ label: "Gia đình", total: 15000000 }],
    };
  });
  render(<Analytics openFinance={vi.fn()} />);
  expect(await screen.findByText("63 tr")).toBeTruthy();
  expect(screen.getByText("59,3 tr")).toBeTruthy();
  expect(await screen.findByText(/Một số tháng chưa tải được/)).toBeTruthy();
  expect(screen.getAllByText("Chưa tải được")).toHaveLength(2);
  expect(screen.getByText(/Số liệu đến 22\/10\/2026/)).toBeTruthy();
});
it("searches services without accents and persists favorites on this browser", async () => {
  const user = userEvent.setup();
  const view = render(<More service={vi.fn()} openFinance={vi.fn()} />);
  await user.type(screen.getByLabelText("Tìm kiếm dịch vụ"), "tiet kiem");
  expect(screen.getByRole("button", { name: "Tiết kiệm", exact: true })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Yêu thích: Tiết kiệm" }));
  view.unmount();
  render(<More service={vi.fn()} openFinance={vi.fn()} />);
  expect(
    screen
      .getAllByRole("button", { name: "Yêu thích: Tiết kiệm" })
      .every((button) => button.getAttribute("aria-pressed") === "true"),
  ).toBe(true);
});
it("shows only one assistant launcher, opens a modal sheet and dismisses with Escape", async () => {
  const user = userEvent.setup();
  render(<App />);
  expect(screen.queryByRole("button", { name: "Tiếp tục với trợ lý" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Điều khiển bằng giọng nói" }));
  expect(screen.getByRole("dialog").getAttribute("aria-modal")).toBe("true");
  expect(screen.queryByRole("button", { name: "Điều khiển bằng giọng nói" })).toBeNull();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Điều khiển bằng giọng nói" })).toBeTruthy();
});
it("formats local bank timestamps without date shifts and crosses year boundaries", () => {
  expect(dateLabel("2026-10-22T00:15:00")).toBe("22/10/2026 · 00:15");
  expect(monthOffset("2026-01", -1)).toBe("2025-12");
});
