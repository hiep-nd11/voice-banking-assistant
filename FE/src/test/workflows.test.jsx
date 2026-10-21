import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "../App.jsx";
import Workflow from "../pages/Workflow.jsx";
import { allowedNavigation } from "../lib/workflows.js";
import { configureApp } from "../lib/config.js";
import base from "../../public/app-config.json";

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  configureApp(structuredClone(base));
});

const flow = {
  id: "flow-1",
  intent: "transfer_recipient",
  step: "review",
  version: 2,
  slots: {
    amount: 500000,
    beneficiary: {
      beneficiary_id: 2,
      name: "Trần Minh Khoa",
      bank: "Vietcombank",
      account_number: "****7890",
    },
  },
  risk: { risk_level: "low", reasons: [] },
  candidates: [],
};

it("prefills beneficiary identity and requires server revalidation after editing amounts", async () => {
  const onEvent = vi.fn();
  const user = userEvent.setup();
  render(<Workflow flow={flow} onEvent={onEvent} />);
  expect(screen.getByText("Trần Minh Khoa")).toBeTruthy();
  expect(screen.getByText(/Vietcombank · \*\*\*\*7890/)).toBeTruthy();
  expect(screen.getByLabelText("Số tiền chuyển").value).toBe("500000");
  const prepare = screen.getByRole("button", { name: /Chuẩn bị yêu cầu/ });
  expect(prepare.disabled).toBe(false);
  await user.clear(screen.getByLabelText("Số tiền chuyển"));
  await user.type(screen.getByLabelText("Số tiền chuyển"), "1000000");
  expect(prepare.disabled).toBe(true);
  await user.click(screen.getByRole("button", { name: "Lưu thông tin và kiểm tra" }));
  expect(onEvent).toHaveBeenCalledWith("form_updated", { amount: 1000000, note: "" });
});

it("blocks high risk without explicit screen acknowledgement and never sends an execute action", async () => {
  const onEvent = vi.fn();
  const user = userEvent.setup();
  render(
    <Workflow
      flow={{ ...flow, risk: { risk_level: "high", reasons: ["Người nhận lạ"] } }}
      onEvent={onEvent}
    />,
  );
  const prepare = screen.getByRole("button", { name: /Chuẩn bị yêu cầu/ });
  expect(prepare.disabled).toBe(true);
  await user.click(screen.getByRole("checkbox"));
  await user.click(prepare);
  expect(onEvent).toHaveBeenCalledWith("prepare", { risk_acknowledged: true });
});

it("only allows known navigation destinations and report features", () => {
  expect(allowedNavigation({ type: "ui_action", action: "navigate", screen: "qr" })).toBe(true);
  expect(
    allowedNavigation({
      type: "ui_action",
      action: "navigate",
      screen: "finance",
      feature: "budget",
    }),
  ).toBe(true);
  for (const event of [
    { screen: "https://evil.example" },
    { screen: "finance", feature: "execute_transfer" },
    { screen: "qr", action: "execute" },
  ]) {
    expect(allowedNavigation({ type: "ui_action", action: "navigate", ...event })).toBe(false);
  }
});

it("keeps the assistant stream alive across QR navigation and submits the scan with flow version", async () => {
  configureApp({ ...structuredClone(base), bankingSource: "mcp", bankingAccounts: [] });
  let backendFlow = {
    id: "qr-flow",
    intent: "transfer_qr",
    step: "awaiting_qr",
    version: 1,
    slots: {},
    candidates: [],
  };
  let streamController;
  const fetch = vi.fn(async (url, opts = {}) => {
    if (url === "/api/chat")
      return {
        ok: true,
        body: new ReadableStream({
          start(controller) {
            streamController = controller;
            const events = [
              { type: "session", session_id: "qr-session" },
              { type: "flow_state", session_id: "qr-session", flow: backendFlow },
              { type: "ui_action", action: "navigate", screen: "qr", flow_id: "qr-flow" },
              { type: "token", content: "Anh quét QR giúp em." },
            ];
            controller.enqueue(
              new TextEncoder().encode(
                events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
              ),
            );
          },
        }),
      };
    if (url === "/api/workflows/qr-session/events") {
      const body = JSON.parse(opts.body);
      if (body.event === "qr_scanned")
        backendFlow = {
          ...backendFlow,
          version: 2,
          step: "awaiting_amount",
          slots: { qr: body.payload },
        };
      return {
        ok: true,
        json: async () => ({
          events: [
            { type: "flow_state", session_id: "qr-session", flow: backendFlow },
            { type: "ui_action", action: "navigate", screen: "workflow" },
            { type: "token", content: "Anh muốn chuyển bao nhiêu?" },
            { type: "done", session_id: "qr-session" },
          ],
        }),
      };
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByTitle("Điều khiển bằng giọng nói"));
  await user.type(screen.getByLabelText("Tin nhắn cho trợ lý"), "chuyển tiền bằng QR");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  expect(await screen.findByText("Quét QR chuyển khoản")).toBeTruthy();
  expect(sessionStorage.getItem("vtb.assistant.session")).toBe("qr-session");
  // Finish the original stream after the UI has already navigated.
  streamController.enqueue(
    new TextEncoder().encode('data: {"type":"done","session_id":"qr-session"}\n\n'),
  );
  streamController.close();
  fireEvent.change(screen.getByLabelText("Nội dung QR"), {
    target: { value: '{"bank":"MB Bank","account":"123456789","name":"NGUYEN VAN A"}' },
  });
  await user.click(screen.getByRole("button", { name: "Đọc thông tin QR" }));
  expect(await screen.findByLabelText("Số tiền chuyển")).toBeTruthy();
  expect(screen.getByText("NGUYEN VAN A")).toBeTruthy();
  const callback = fetch.mock.calls.find(([url]) => url === "/api/workflows/qr-session/events");
  expect(JSON.parse(callback[1].body)).toMatchObject({
    flow_id: "qr-flow",
    version: 1,
    event: "qr_scanned",
    payload: { bank: "MB Bank", account: "123456789" },
  });
  await user.click(await screen.findByRole("button", { name: "Tiếp tục với trợ lý" }));
  expect(screen.getByText("Anh quét QR giúp em.")).toBeTruthy();
  expect(screen.getByText("Anh muốn chuyển bao nhiêu?")).toBeTruthy();
});

it("fills the original normal-transfer form from an account command and cancels that journey when switching to quick transfer", async () => {
  configureApp({ ...structuredClone(base), bankingSource: "mcp", bankingAccounts: [] });
  let current = {
    id: "account-flow",
    intent: "transfer_account",
    step: "review",
    version: 1,
    slots: { destination: { bank: "Vietcombank", account: "22212132" }, amount: 5000000 },
    candidates: [],
    risk: { risk_level: "low", reasons: [] },
  };
  const fetch = vi.fn(async (url, opts = {}) => {
    if (url === "/api/chat") {
      const rows = [
        { type: "session", session_id: "account-session" },
        { type: "flow_state", flow: current },
        { type: "ui_action", action: "navigate", screen: "transfer" },
        { type: "token", content: "Em đã điền thông tin chuyển khoản." },
        { type: "done", session_id: "account-session" },
      ];
      return {
        ok: true,
        body: new ReadableStream({
          start(c) {
            c.enqueue(
              new TextEncoder().encode(rows.map((r) => `data: ${JSON.stringify(r)}\n\n`).join("")),
            );
            c.close();
          },
        }),
      };
    }
    if (url === "/api/workflows/account-session/events") {
      const req = JSON.parse(opts.body);
      if (req.event === "cancel") current = null;
      else
        current = {
          ...current,
          version: current.version + 1,
          slots: {
            ...current.slots,
            destination: {
              bank: req.payload.bank,
              account: req.payload.account,
              recipient: req.payload.recipient,
            },
            amount: req.payload.amount,
          },
        };
      return {
        ok: true,
        json: async () => ({
          events: [
            { type: "flow_state", flow: current },
            { type: "ui_action", action: "navigate", screen: current ? "transfer" : "home" },
            { type: "done", session_id: "account-session" },
          ],
        }),
      };
    }
    throw new Error(`Unexpected ${url}`);
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByTitle("Điều khiển bằng giọng nói"));
  await user.type(
    screen.getByLabelText("Tin nhắn cho trợ lý"),
    "chuyển cho tài khoản 22212132 vietcombank 5 triệu",
  );
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  expect(await screen.findByLabelText("Số tài khoản")).toBeTruthy();
  expect(screen.getByLabelText("Số tài khoản").value).toBe("22212132");
  expect(screen.getByLabelText("Ngân hàng thụ hưởng").value).toBe("Vietcombank");
  expect(screen.getByLabelText("Số tiền chuyển").value).toBe("5000000");
  await user.type(screen.getByLabelText("Tên người thụ hưởng"), "NGUYEN VAN A");
  await user.click(screen.getByRole("button", { name: "Tiếp tục", exact: true }));
  expect(await screen.findByRole("heading", { name: "Xác nhận chuyển tiền" })).toBeTruthy();
  expect(screen.getByText("5.000.000 ₫")).toBeTruthy();
  expect(screen.getByText("22212132")).toBeTruthy();
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/events"))).toBe(false);
  await user.click(screen.getByRole("button", { name: "Chỉnh sửa thông tin" }));
  await user.click(screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }));
  expect(await screen.findByRole("button", { name: "Thêm người nhận" })).toBeTruthy();
  expect(
    fetch.mock.calls.some(
      ([url, opts]) => url.endsWith("/events") && JSON.parse(opts.body).event === "cancel",
    ),
  ).toBe(true);
  await user.click(screen.getByRole("button", { name: "Chuyển tiền thường", exact: true }));
  expect(screen.getByLabelText("Số tài khoản").value).toBe("");
});
