import { describe, expect, it } from "vitest";
import { parseQR } from "../lib/qr.js";
import { BALANCE, emptyTransfer, validateTransfer } from "../lib/transfer.js";

describe("transfer validation", () => {
  const valid = {
    ...emptyTransfer(),
    account: "123456789",
    recipient: "TEST",
    amount: "1000",
  };
  it("accepts the minimum and full available balance", () => {
    expect(validateTransfer(valid)).toBe("");
    expect(validateTransfer({ ...valid, amount: String(BALANCE) })).toBe("");
  });
  it.each(["999", String(BALANCE + 1), "1000.5", "NaN"])(
    "rejects invalid amount %s",
    (amount) => {
      expect(validateTransfer({ ...valid, amount })).not.toBe("");
    },
  );
});

describe("QR formats", () => {
  it("reads JSON and URLs", () => {
    expect(
      parseQR(
        JSON.stringify({
          bank: "MB Bank",
          account: "123456789",
          name: "TEST",
          amount: 200000,
        }),
      ).recipient,
    ).toBe("TEST");
    expect(
      parseQR(
        "https://example.com/?accountNo=123456789&amount=200000&addInfo=Demo",
      ).memo,
    ).toBe("Demo");
  });
  it("reads nested VietQR/EMV fields", () => {
    const tlv = (tag, value) =>
      tag + String(value.length).padStart(2, "0") + value;
    const payload =
      "000201" +
      tlv(
        "38",
        tlv("00", "A000000727") +
          tlv("01", tlv("00", "970422") + tlv("01", "123456789")),
      ) +
      tlv("54", "200000") +
      tlv("62", tlv("08", "Demo"));
    expect(parseQR(payload)).toEqual({
      bank: "MB Bank",
      account: "123456789",
      recipient: "",
      amount: "200000",
      memo: "Demo",
    });
  });
  it.each(["", "{}", "{broken", "unsupported"])(
    "rejects invalid QR %s",
    (value) => expect(() => parseQR(value)).toThrow(),
  );
});
