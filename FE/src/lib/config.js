export let config;

export function configureApp(value) {
  const fail = (field) => {
    throw new Error(`Cấu hình không hợp lệ: ${field}`);
  };
  const string = (v, key) => {
    if (typeof v !== "string" || !v.trim()) fail(key);
  };
  if (!value || typeof value !== "object") fail("app-config.json");
  for (const key of ["id", "name", "bank", "account"]) string(value.user?.[key], `user.${key}`);
  if (!Number.isSafeInteger(value.user.balance) || value.user.balance < 0) fail("user.balance");
  for (const key of ["title", "locale", "currencySymbol", "referencePrefix"])
    string(value.app?.[key], `app.${key}`);
  try {
    new Intl.NumberFormat(value.app.locale);
  } catch {
    fail("app.locale");
  }
  if (
    !Number.isInteger(value.app.referenceDigits) ||
    value.app.referenceDigits < 1 ||
    value.app.referenceDigits > 20
  )
    fail("app.referenceDigits");
  for (const key of [
    "banks",
    "recipients",
    "transactions",
    "services",
    "navigation",
    "transferMethods",
  ]) {
    if (!Array.isArray(value[key])) fail(key);
  }
  if (!value.banks.length) fail("banks");
  value.banks.forEach((b) => {
    string(b.name, "banks.name");
    string(b.bin, "banks.bin");
  });
  const t = value.transfer;
  if (!t) fail("transfer");
  for (const key of ["defaultBank", "defaultMemo", "qrDefaultMemo"])
    string(t[key], `transfer.${key}`);
  for (const key of ["minAmount", "accountMinLength", "accountMaxLength"])
    if (!Number.isSafeInteger(t[key]) || t[key] < 1) fail(`transfer.${key}`);
  if (t.accountMaxLength < t.accountMinLength || t.accountMaxLength > 100)
    fail("transfer.accountMaxLength");
  if (!Number.isFinite(t.fee) || t.fee < 0) fail("transfer.fee");
  if (!value.banks.some((b) => b.name === t.defaultBank)) fail("transfer.defaultBank");
  string(value.storage?.recipientsKey, "storage.recipientsKey");
  if (!value.screenTitles || !value.mockServices) fail("screenTitles/mockServices");
  value.recipients.forEach((r) => {
    for (const key of ["bank", "account", "recipient"]) string(r?.[key], `recipients.${key}`);
    if (r.nickname !== undefined && typeof r.nickname !== "string") fail("recipients.nickname");
    if (!new RegExp(`^\\d{${t.accountMinLength},${t.accountMaxLength}}$`).test(r.account))
      fail("recipients.account");
  });
  value.transactions.forEach((row) => {
    string(row.name, "transactions.name");
    string(row.date, "transactions.date");
    if (!Number.isFinite(row.amt) || row.amt < 0) fail("transactions.amt");
  });
  for (const [key, service] of Object.entries(value.mockServices)) {
    for (const field of ["description", "action", "result"])
      string(service?.[field], `mockServices.${key}.${field}`);
    if (!Array.isArray(service.fields)) fail(`mockServices.${key}.fields`);
    service.fields.forEach((f) => {
      string(f.key, "mockServices.fields.key");
      string(f.label, "mockServices.fields.label");
      if (
        f.options !== undefined &&
        (!Array.isArray(f.options) ||
          !f.options.length ||
          f.options.some((o) => typeof o !== "string"))
      )
        fail("mockServices.fields.options");
    });
  }
  for (const field of ["services", "navigation", "transferMethods"]) {
    value[field].forEach((row) => {
      if (!Array.isArray(row) || row.length < 2 || row.some((v) => typeof v !== "string" || !v))
        fail(field);
    });
  }
  config = value;
  return config;
}

export async function loadAppConfig() {
  const response = await fetch(`${import.meta.env.BASE_URL}app-config.json`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Không tải được app-config.json (HTTP ${response.status}).`);
  return configureApp(await response.json());
}

export const maskedAccount = () =>
  /[*•]/.test(config.user.account)
    ? config.user.account
    : `${config.user.account.slice(0, 4)} •••• ${config.user.account.slice(-4)}`;
export const validAccount = (account) =>
  new RegExp(`^\\d{${config.transfer.accountMinLength},${config.transfer.accountMaxLength}}$`).test(
    account,
  );
