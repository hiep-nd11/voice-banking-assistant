import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import Finance from "../pages/Finance.jsx";
import FinanceResult from "../components/FinanceResult.jsx";
import { initialValues, serializeFields } from "../lib/finance.js";

const calendar = {
  today: "2026-10-22",
  this_month_start: "2026-10-01",
  last_month: ["2026-09-01", "2026-09-30"],
};
const features = [
  {
    id: "month",
    title: "Tổng quan tháng",
    read_only: true,
    schema: { properties: { month: { type: "string" } } },
  },
  {
    id: "transactions",
    title: "Tra cứu giao dịch",
    read_only: true,
    schema: {
      required: ["date_from", "date_to"],
      properties: {
        date_from: { type: "string" },
        date_to: { type: "string" },
        keyword: { type: "string" },
        direction: { anyOf: [{ type: "string", enum: ["in", "out"] }, { type: "null" }] },
        limit: { type: "integer", default: 10, minimum: 1, maximum: 50 },
      },
    },
  },
  {
    id: "prepare-transfer",
    title: "Chuẩn bị chuyển tiền",
    read_only: false,
    schema: {
      required: ["amount"],
      properties: {
        amount: { type: "integer", minimum: 1000 },
        beneficiary_id: { anyOf: [{ type: "integer" }, { type: "null" }] },
        risk_acknowledged: { type: "boolean", default: false },
      },
    },
  },
];

function mockBackend(handler) {
  const mock = vi.fn(async (url, options = {}) => {
    let data;
    if (url.endsWith("/features")) data = { features };
    else if (url.endsWith("/calendar")) data = calendar;
    else if (url.endsWith("/beneficiaries"))
      data = { items: [{ beneficiary_id: 2, name: "Con trai", account_number: "****7890" }] };
    else data = await handler(url, JSON.parse(options.body || "{}"));
    return { ok: true, json: async () => data };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

it("loads monthly data and submits full transaction filters to BE", async () => {
  const fetch = mockBackend(async () => ({ total_income: 12000000, items: [] }));
  const user = userEvent.setup();
  render(<Finance />);
  expect(await screen.findByText("12.000.000 ₫")).toBeTruthy();
  await user.selectOptions(screen.getByLabelText("Chức năng tài chính"), "transactions");
  await user.type(screen.getByLabelText("Từ khóa"), "hoc phi");
  await user.selectOptions(screen.getByLabelText("Chiều giao dịch"), "out");
  await user.click(screen.getByRole("button", { name: "Xem kết quả" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url, opts]) =>
          url.endsWith("/transactions") && JSON.parse(opts.body).keyword === "hoc phi",
      ),
    ).toBe(true),
  );
  const args = JSON.parse(
    fetch.mock.calls.filter(([url]) => url.endsWith("/transactions")).at(-1)[1].body,
  );
  expect(args).toEqual({
    date_from: "2026-10-01",
    date_to: "2026-10-22",
    keyword: "hoc phi",
    direction: "out",
    limit: 10,
  });
});

it("prepares a request only after a user click and can cancel it", async () => {
  const fetch = mockBackend(async (url) =>
    url.endsWith("/cancel")
      ? { ui_action: { type: "close", action_id: "act-test" }, speech: "Đã hủy yêu cầu" }
      : {
          executed: false,
          ui_action: {
            type: "navigate",
            screen: "transfer",
            action_id: "act-test",
            prefill: { amount: 100000 },
          },
        },
  );
  const user = userEvent.setup();
  render(<Finance initial="prepare-transfer" />);
  await screen.findByLabelText("Số tiền (VND) *");
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/prepare-transfer"))).toBe(false);
  await user.type(screen.getByLabelText("Số tiền (VND) *"), "100000");
  await user.selectOptions(screen.getByLabelText("Người nhận"), "2");
  await user.click(screen.getByRole("button", { name: "Chuẩn bị yêu cầu" }));
  expect(await screen.findByText(/Chưa thực hiện giao dịch/)).toBeTruthy();
  expect(JSON.parse(sessionStorage.getItem("vtb.banking.pending"))[0].action_id).toBe("act-test");
  const request = fetch.mock.calls.find(([url]) => url.endsWith("/prepare-transfer"));
  expect(JSON.parse(request[1].body)).toEqual({
    amount: 100000,
    beneficiary_id: 2,
    risk_acknowledged: false,
  });
  await user.click(screen.getByRole("button", { name: "Hủy yêu cầu vừa chuẩn bị" }));
  expect(await screen.findByText("Đã hủy yêu cầu")).toBeTruthy();
  expect(JSON.parse(sessionStorage.getItem("vtb.banking.pending"))).toEqual([]);
});

it("shows errors with a retry action", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 502,
      json: async () => ({ detail: "MCP mất kết nối" }),
    })),
  );
  render(<Finance />);
  expect(await screen.findByText("MCP mất kết nối")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Thử lại" })).toBeTruthy();
});

it("renders zero balances, loan dates and risk reasons as readable data", () => {
  render(
    <FinanceResult
      data={{
        accounts: [{ balance: 0, outstanding: 5000000, next_payment_date: "2026-11-15" }],
        severity: "high",
        reasons: ["Người nhận lạ"],
        series: [{ month: "2026-10", total: 100000 }],
      }}
    />,
  );
  expect(screen.getByText("0 ₫")).toBeTruthy();
  expect(screen.getByText("5.000.000 ₫")).toBeTruthy();
  expect(screen.getByText("Người nhận lạ")).toBeTruthy();
  expect(screen.getByText("Cao")).toBeTruthy();
  expect(screen.getByRole("meter")).toBeTruthy();
});

it("uses source date ranges and preserves false and zero values", () => {
  const schema = {
    properties: {
      a_from: { type: "string" },
      b_to: { type: "string" },
      amount: { type: "integer" },
      risk_acknowledged: { type: "boolean" },
    },
  };
  const values = initialValues(schema, calendar);
  expect(values.a_from).toBe("2026-09-01");
  expect(
    serializeFields(schema, { ...values, amount: "0", risk_acknowledged: false }),
  ).toMatchObject({ amount: 0, risk_acknowledged: false });
});

it("keeps transaction and preparation forms out of the Analysis tab", async () => {
  mockBackend(async () => ({ total_income: 12000000 }));
  render(<Finance mode="analysis" />);
  const select = await screen.findByLabelText("Báo cáo của bạn");
  expect([...select.options].map((option) => option.value)).toEqual(["month"]);
  expect(await screen.findByText("12.000.000 ₫")).toBeTruthy();
});
