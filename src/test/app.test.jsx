import {
  act,
  render,
  screen,
  waitFor,
  within,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../App.jsx";

describe("banking flows", () => {
  it("allows retrying camera access after permission is denied", async () => {
    const user = userEvent.setup();
    const getUserMedia = vi
      .fn()
      .mockRejectedValue(new Error("Permission denied"));
    const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    vi.stubGlobal("BarcodeDetector", class {});
    try {
      render(<App />);
      await user.click(
        screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
      );
      await user.click(
        within(
          screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }),
        ).getByRole("button", { name: "Quét QR", exact: true }),
      );
      await user.click(screen.getByRole("button", { name: /Mở camera/ }));
      await waitFor(() =>
        expect(screen.getByRole("status").textContent).toContain(
          "Permission denied",
        ),
      );
      await user.click(screen.getByRole("button", { name: /Mở camera/ }));
      expect(getUserMedia).toHaveBeenCalledTimes(2);
    } finally {
      vi.unstubAllGlobals();
      if (original) Object.defineProperty(navigator, "mediaDevices", original);
      else delete navigator.mediaDevices;
    }
  });

  it("validates a transfer, allows editing, confirms once, and searches history", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
    );
    await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
    expect(screen.getByRole("status").textContent).toContain(
      "Nhập số tài khoản hợp lệ",
    );
    await user.type(screen.getByLabelText("Số tài khoản"), "123456789");
    await user.type(
      screen.getByLabelText("Tên người thụ hưởng"),
      "TEST RECIPIENT",
    );
    await user.type(screen.getByLabelText("Số tiền chuyển"), "200000");
    await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
    expect(screen.getByRole("heading").textContent).toBe(
      "Xác nhận chuyển tiền",
    );
    await user.click(
      screen.getByRole("button", { name: "Chỉnh sửa thông tin" }),
    );
    expect(screen.getByLabelText("Số tài khoản").value).toBe("123456789");
    await user.click(screen.getByRole("button", { name: /Tiếp tục/ }));
    await user.dblClick(
      screen.getByRole("button", { name: "Xác nhận giao dịch mô phỏng" }),
    );
    expect(screen.getByText("DEMO-00001")).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Giao dịch", exact: true }),
    );
    await user.type(screen.getByLabelText("Tìm giao dịch"), "test recipient");
    expect(screen.getAllByText("TEST RECIPIENT")).toHaveLength(1);
    expect(screen.queryByText("WinMart Times City")).toBeNull();
  });

  it("parses a pasted QR and handles invalid pasted QR", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
    );
    await user.click(
      within(
        screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }),
      ).getByRole("button", { name: "Quét QR", exact: true }),
    );
    await user.type(screen.getByLabelText("Nội dung QR"), "invalid");
    await user.click(screen.getByRole("button", { name: "Đọc thông tin QR" }));
    expect(screen.getByRole("status").textContent).toContain(
      "QR chưa đúng định dạng",
    );
    await user.clear(screen.getByLabelText("Nội dung QR"));
    fireEvent.change(screen.getByLabelText("Nội dung QR"), {
      target: {
        value: JSON.stringify({
          bank: "VietinBank",
          account: "106888123456",
          recipient: "NGUYEN VAN MINH",
          amount: "200000",
        }),
      },
    });
    await user.click(screen.getByRole("button", { name: "Đọc thông tin QR" }));
    expect(screen.getByLabelText("Số tài khoản").value).toBe("106888123456");
    expect(screen.getByLabelText("Tên người thụ hưởng").value).toBe(
      "NGUYEN VAN MINH",
    );
    expect(screen.getByLabelText("Số tiền chuyển").value).toBe("200000");
  });

  it("stops a camera stream granted after leaving the QR page", async () => {
    const user = userEvent.setup();
    let grant;
    const stop = vi.fn();
    const original = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(
          () =>
            new Promise((resolve) => {
              grant = resolve;
            }),
        ),
      },
    });
    vi.stubGlobal("BarcodeDetector", class {});
    try {
      render(<App />);
      await user.click(
        screen.getByRole("button", { name: "Chuyển tiền", exact: true }),
      );
      await user.click(
        within(
          screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }),
        ).getByRole("button", { name: "Quét QR", exact: true }),
      );
      await user.click(screen.getByRole("button", { name: /Mở camera/ }));
      await user.click(
        screen.getByRole("button", { name: "Trang chủ", exact: true }),
      );
      await act(async () => grant({ getTracks: () => [{ stop }] }));
      await waitFor(() => expect(stop).toHaveBeenCalledOnce());
    } finally {
      vi.unstubAllGlobals();
      if (original) Object.defineProperty(navigator, "mediaDevices", original);
      else delete navigator.mediaDevices;
    }
  });
});
