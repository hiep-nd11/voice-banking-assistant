import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import base from "../../public/app-config.json";
import { configureApp } from "../lib/config.js";
import App from "../App.jsx";

afterEach(() => {
  vi.unstubAllGlobals();
  configureApp(structuredClone(base));
  sessionStorage.clear();
});
it("completes a backend-backed account transfer locally without warnings or a transfer API", async () => {
  configureApp({ ...structuredClone(base), bankingSource: "mcp", bankingAccounts: [] });
  const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({ items: [] }) }));
  vi.stubGlobal("fetch", fetcher);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Chuyển tiền", exact: true }));
  await user.type(screen.getByLabelText("Số tài khoản"), "123456789");
  await user.type(screen.getByLabelText("Tên người thụ hưởng"), "DEMO RECIPIENT");
  await user.type(screen.getByLabelText("Số tiền chuyển"), "200000");
  await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.queryByText(/Ứng dụng thật phải/)).toBeNull();
  await user.dblClick(screen.getByRole("button", { name: "Xác nhận giao dịch mô phỏng" }));
  expect(screen.getByText("Đã tạo giao dịch demo!")).toBeTruthy();
  expect(screen.getByText("DEMO-00001")).toBeTruthy();
  expect(fetcher).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Giao dịch", exact: true }));
  expect(screen.getByText("Giao dịch mô phỏng trong phiên (1)")).toBeTruthy();
  expect(screen.getByText("DEMO RECIPIENT")).toBeTruthy();
});
