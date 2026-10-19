import { config, validAccount } from "./config.js";
export const RECIPIENTS_KEY = `${config.storage.recipientsKey}:${config.user.id}`;
export function normalizeRecipient(r) {
  return {
    bank: r.bank,
    account: r.account,
    recipient: r.recipient,
    nickname: typeof r.nickname === "string" ? r.nickname : "",
  };
}
export function validateRecipient(r) {
  if (!validAccount(r.account.trim()))
    return `Nhập số tài khoản hợp lệ (${config.transfer.accountMinLength}–${config.transfer.accountMaxLength} chữ số)`;
  if (!r.recipient.trim()) return "Vui lòng nhập tên người thụ hưởng";
  return "";
}
export function loadRecipients() {
  try {
    const stored = localStorage.getItem(RECIPIENTS_KEY);
    if (stored !== null) {
      const rows = JSON.parse(stored);
      if (Array.isArray(rows))
        return rows
          .filter(
            (r) =>
              r &&
              ["bank", "account", "recipient"].every(
                (k) => typeof r[k] === "string",
              ) &&
              validAccount(r.account) &&
              r.recipient.trim(),
          )
          .map(normalizeRecipient);
    }
  } catch {
    /* Start with an empty address book when storage is unavailable. */
  }
  return config.recipients.map(normalizeRecipient);
}

export function persistRecipients(rows) {
  try {
    localStorage.setItem(
      RECIPIENTS_KEY,
      JSON.stringify(rows.map(normalizeRecipient)),
    );
    return true;
  } catch {
    return false;
  }
}
