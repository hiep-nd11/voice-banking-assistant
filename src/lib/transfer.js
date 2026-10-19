import { config, validAccount } from "./config.js";
export const BALANCE = config.user.balance;
export const emptyTransfer = () => ({
  bank: config.transfer.defaultBank,
  account: "",
  recipient: "",
  amount: "",
  memo: "",
  qrLocked: false,
});
export const money = (n) =>
  new Intl.NumberFormat(config.app.locale).format(n || 0) +
  " " +
  config.app.currencySymbol;
export function validateTransfer(form) {
  if (!validAccount(form.account.trim()))
    return `Nhập số tài khoản hợp lệ (${config.transfer.accountMinLength}–${config.transfer.accountMaxLength} chữ số)`;
  if (!form.recipient.trim()) return "Vui lòng nhập tên người thụ hưởng";
  const amount = Number(form.amount);
  if (
    !Number.isSafeInteger(amount) ||
    amount < config.transfer.minAmount ||
    amount > BALANCE
  )
    return `Số tiền từ ${money(config.transfer.minAmount)} đến số dư khả dụng`;
  return "";
}
