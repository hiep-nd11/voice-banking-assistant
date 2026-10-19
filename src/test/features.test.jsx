import { render, screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";
import App from "../App.jsx";
import { RECIPIENTS_KEY } from "../lib/recipients.js";
import { services } from "../lib/data.js";
import { mockServices } from "../lib/mockServices.js";

beforeEach(() => localStorage.clear());

it("adds a recipient without transfer fields or a JSON import button", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  );
  expect(screen.queryByLabelText("Nhập người nhận từ JSON")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Thêm người nhận" }));
  expect(screen.queryByLabelText("Số tiền chuyển")).toBeNull();
  expect(screen.queryByLabelText("Nội dung chuyển khoản")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Lưu người nhận" }));
  expect(screen.getByRole("alert").textContent).toContain(
    "Nhập số tài khoản hợp lệ",
  );
  await user.type(screen.getByLabelText("Số tài khoản"), "0123456789");
  await user.type(
    screen.getByLabelText("Tên người thụ hưởng"),
    "TEST RECIPIENT",
  );
  await user.type(screen.getByLabelText("Tên gợi nhớ (không bắt buộc)"), "Mẹ");
  await user.click(screen.getByRole("button", { name: "Lưu người nhận" }));
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh cho Mẹ" }),
  );
  expect(screen.getByLabelText("Số tài khoản").value).toBe("0123456789");
  expect(screen.getByLabelText("Số tiền chuyển").value).toBe("");
});

it("groups normal, QR and quick transfers inside the transfer screen", async () => {
  const user = userEvent.setup();
  render(<App />);
  expect(
    screen.queryByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  ).toBeNull();
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  expect(
    screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }),
  ).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  );
  expect(screen.getByRole("button", { name: "Thêm người nhận" })).toBeTruthy();
  await user.click(
    within(
      screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }),
    ).getByRole("button", { name: "Quét QR", exact: true }),
  );
  expect(screen.getByRole("button", { name: /Mở camera/ })).toBeTruthy();
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền thường", exact: true }),
  );
  expect(screen.getByLabelText("Số tài khoản").value).toBe("");
});

it("saves, updates, restores, autofills and deletes a familiar recipient", async () => {
  const user = userEvent.setup();
  const view = render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  await user.type(screen.getByLabelText("Số tài khoản"), "123456789");
  await user.type(screen.getByLabelText("Tên người thụ hưởng"), "BAN THAN");
  await user.type(screen.getByLabelText("Tên gợi nhớ (không bắt buộc)"), "Mẹ");
  await user.click(screen.getByRole("button", { name: "Lưu người nhận" }));
  expect(JSON.parse(localStorage.getItem(RECIPIENTS_KEY))[0].nickname).toBe(
    "Mẹ",
  );
  await user.clear(screen.getByLabelText("Tên gợi nhớ (không bắt buộc)"));
  await user.type(screen.getByLabelText("Tên gợi nhớ (không bắt buộc)"), "Cha");
  await user.type(screen.getByLabelText("Số tiền chuyển"), "300000");
  await user.click(screen.getByRole("button", { name: "Lưu người nhận" }));
  expect(
    JSON.parse(localStorage.getItem(RECIPIENTS_KEY)).filter(
      (r) => r.account === "123456789",
    ),
  ).toHaveLength(1);
  view.unmount();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh cho Cha" }),
  );
  expect(screen.getByLabelText("Ngân hàng thụ hưởng").value).toBe("VietinBank");
  expect(screen.getByLabelText("Số tài khoản").value).toBe("123456789");
  expect(screen.getByLabelText("Tên người thụ hưởng").value).toBe("BAN THAN");
  expect(screen.getByLabelText("Tên gợi nhớ (không bắt buộc)").value).toBe(
    "Cha",
  );
  expect(screen.getByLabelText("Số tiền chuyển").value).toBe("");
  expect(screen.getByLabelText("Nội dung chuyển khoản").value).toBe("");
  expect(
    JSON.parse(localStorage.getItem(RECIPIENTS_KEY))[0].amount,
  ).toBeUndefined();
  await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
  expect(screen.getByRole("heading").textContent).toBe("Chuyển tiền");
  await user.type(screen.getByLabelText("Số tiền chuyển"), "200000");
  await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
  expect(screen.getByRole("heading").textContent).toBe("Xác nhận chuyển tiền");
  await user.click(screen.getByRole("button", { name: "Quay lại" }));
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  );
  await user.click(screen.getByRole("button", { name: "Xóa Cha" }));
  expect(
    screen.queryByRole("button", { name: "Chuyển tiền nhanh cho Cha" }),
  ).toBeNull();
  expect(
    JSON.parse(localStorage.getItem(RECIPIENTS_KEY)).some(
      (r) => r.account === "123456789",
    ),
  ).toBe(false);
});

it("handles an empty saved-recipient list and allows adding a recipient", async () => {
  localStorage.setItem(RECIPIENTS_KEY, "[]");
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Chuyển tiền nhanh", exact: true }),
  );
  expect(screen.getByText(/Chưa có người nhận đã lưu/)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Thêm người nhận" }));
  expect(screen.getByLabelText("Số tài khoản").value).toBe("");
});

it.each(Object.entries(mockServices))(
  "opens service %s and completes a demo action",
  async (id, config) => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", {
        name: services.find((s) => s[0] === id)[1],
        exact: true,
      }),
    );
    expect(screen.getByText("DỊCH VỤ DEMO")).toBeTruthy();
    if (id === "plane")
      fireEvent.change(screen.getByLabelText("Ngày khởi hành"), {
        target: { value: "2027-01-01" },
      });
    await user.click(screen.getByRole("button", { name: config.action }));
    expect(screen.getByRole("status").textContent).toContain(config.result);
    await user.click(screen.getByRole("button", { name: "Thực hiện lại" }));
    expect(screen.getByRole("button", { name: config.action })).toBeTruthy();
  },
);
