import { config, validAccount } from "./config.js";
export function parseQR(text) {
  text = (text || "").trim();
  if (!text) throw Error("QR không có nội dung");
  let s = {
    bank: config.transfer.defaultBank,
    account: "",
    recipient: "",
    amount: "",
    memo: config.transfer.qrDefaultMemo,
  };
  try {
    if (text.startsWith("{")) {
      let j = JSON.parse(text);
      s = {
        bank: String(j.bank || s.bank),
        account: String(j.account || ""),
        recipient: String(j.name || j.recipient || ""),
        amount: String(j.amount || ""),
        memo: String(j.memo || config.transfer.qrDefaultMemo),
      };
    } else if (/^(https?:\/\/)/i.test(text)) {
      let u = new URL(text);
      s.account =
        u.searchParams.get("accountNo") || u.searchParams.get("account") || "";
      s.recipient = u.searchParams.get("accountName") || "";
      s.amount = u.searchParams.get("amount") || "";
      s.memo = u.searchParams.get("addInfo") || config.transfer.qrDefaultMemo;
      s.bank = u.searchParams.get("bank") || config.transfer.defaultBank;
    } else if (/^000201/.test(text)) {
      const tlv = (str) => {
        let out = [],
          i = 0;
        while (i + 4 <= str.length) {
          let tag = str.slice(i, i + 2),
            len = Number(str.slice(i + 2, i + 4));
          if (!Number.isFinite(len) || len < 0 || i + 4 + len > str.length)
            break;
          out.push({ tag, value: str.slice(i + 4, i + 4 + len) });
          i += 4 + len;
        }
        return out;
      };
      let fields = tlv(text);
      let detail = fields.find((f) => f.tag === "38");
      if (detail) {
        let children = tlv(detail.value);
        let ac = children.find((f) => f.tag === "01");
        if (ac) {
          let pairs = tlv(ac.value);
          s.account = pairs.find((p) => p.tag === "01")?.value || "";
          let bin = pairs.find((p) => p.tag === "00")?.value || "";
          const bm = Object.fromEntries(
            config.banks.map((b) => [b.bin, b.name]),
          );
          s.bank = bm[bin] || config.transfer.defaultBank;
        }
      }
      s.amount = fields.find((f) => f.tag === "54")?.value || "";
      let extra = fields.find((f) => f.tag === "62");
      if (extra)
        s.memo =
          tlv(extra.value).find((f) => f.tag === "08")?.value ||
          config.transfer.qrDefaultMemo;
      s.recipient = "";
    } else throw Error("QR chưa đúng định dạng hỗ trợ");
    if (!s.account || !validAccount(s.account))
      throw Error("Không đọc được số tài khoản từ QR");
    return s;
  } catch (e) {
    throw Error(e.message || "Không đọc được QR");
  }
}
