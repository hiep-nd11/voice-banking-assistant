import { beforeEach, expect, it } from "vitest";
import {
  loadRecipients,
  RECIPIENTS_KEY,
  validateRecipient,
} from "../lib/recipients.js";

beforeEach(() => localStorage.clear());

it("starts empty without hardcoded recipients", () => {
  expect(loadRecipients()).toEqual([]);
});

it("loads old recipients without reusing transfer amounts or memos", () => {
  localStorage.setItem(
    RECIPIENTS_KEY,
    JSON.stringify([
      {
        bank: "MB Bank",
        account: "123456789",
        recipient: "TEST",
        amount: "500000",
        memo: "Old transfer",
      },
    ]),
  );
  expect(loadRecipients()).toEqual([
    { bank: "MB Bank", account: "123456789", recipient: "TEST", nickname: "" },
  ]);
});

it("validates recipient identity without requiring a transfer amount", () => {
  expect(validateRecipient({ account: "123456789", recipient: "TEST" })).toBe(
    "",
  );
  expect(validateRecipient({ account: "abc", recipient: "TEST" })).not.toBe("");
  expect(validateRecipient({ account: "123456789", recipient: " " })).not.toBe(
    "",
  );
});
