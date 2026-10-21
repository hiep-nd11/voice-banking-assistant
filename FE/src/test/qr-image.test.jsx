import { resolve } from "node:path";
import { readFileSync } from "node:fs";
import { PNG } from "pngjs";
import { afterEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { decodeQrPixels } from "../lib/qrImage.js";
import { parseQR } from "../lib/qr.js";
import App from "../App.jsx";

function fixture(name) {
  return PNG.sync.read(readFileSync(resolve("docs/mock-qr", `${name}.png`)));
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it.each([
  ["01-vietinbank-200k", "106888123456", "NGUYEN VAN MINH", "200000"],
  ["02-vietcombank-350k", "0123456789", "TRAN THI LAN", "350000"],
  ["03-mb-custom-amount", "0987654321", "LE QUANG HUY", ""],
  ["04-missing-recipient", "106888123456", "", "100000"],
])("decodes real PNG %s into transfer information", (name, account, recipient, amount) => {
  const result = parseQR(decodeQrPixels(fixture(name)));
  expect(result).toMatchObject({ account, recipient, amount });
});

it("returns no payload for an image without a QR", () => {
  expect(
    decodeQrPixels({
      width: 100,
      height: 100,
      data: new Uint8ClampedArray(40000).fill(255),
    }),
  ).toBe("");
});

it("uploads an image and fills the transfer form without BarcodeDetector", async () => {
  const pixels = fixture("01-vietinbank-200k");
  const close = vi.fn();
  vi.stubGlobal("BarcodeDetector", undefined);
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn().mockResolvedValue({ width: pixels.width, height: pixels.height, close }),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    fillRect: vi.fn(),
    drawImage: vi.fn(),
    getImageData: () => pixels,
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Chuyển tiền", exact: true }));
  await user.click(
    screen.getByRole("navigation", { name: "Hình thức chuyển tiền" }).querySelectorAll("button")[1],
  );
  expect(screen.queryByText("QR mẫu để demo")).toBeNull();
  await user.upload(
    screen.getByLabelText("Tải ảnh QR"),
    new File([readFileSync(resolve("docs/mock-qr/01-vietinbank-200k.png"))], "qr.png", {
      type: "image/png",
    }),
  );
  expect(await screen.findByLabelText("Số tài khoản")).toBeTruthy();
  expect(screen.getByLabelText("Số tài khoản").value).toBe("106888123456");
  expect(screen.getByLabelText("Tên người thụ hưởng").value).toBe("NGUYEN VAN MINH");
  expect(screen.getByLabelText("Số tiền chuyển").value).toBe("200000");
  expect(close).toHaveBeenCalledOnce();
});
