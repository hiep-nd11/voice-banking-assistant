import { config } from "./lib/config.js";
import { useEffect, useRef, useState } from "react";
import Icon from "./components/Icon.jsx";
import { Header, Navbar } from "./components/Layout.jsx";
import VoicePanel from "./components/VoicePanel.jsx";
import TransferMethods from "./components/TransferMethods.jsx";
import Home from "./pages/Home.jsx";
import Transfer from "./pages/Transfer.jsx";
import Qr from "./pages/Qr.jsx";
import { Confirm, Success } from "./pages/Result.jsx";
import History from "./pages/History.jsx";
import More from "./pages/More.jsx";
import Recipients from "./pages/Recipients.jsx";
import MockService from "./pages/MockService.jsx";
import {
  loadRecipients,
  persistRecipients,
  validateRecipient,
} from "./lib/recipients.js";
import { mockServices } from "./lib/mockServices.js";
import { services } from "./lib/data.js";
import { emptyTransfer, validateTransfer } from "./lib/transfer.js";

const titles = config.screenTitles;

export default function App() {
  const [screen, setScreen] = useState("home");
  const [form, setForm] = useState(emptyTransfer);
  const [transfers, setTransfers] = useState([]);
  const [recipients, setRecipients] = useState(loadRecipients);
  const [voice, setVoice] = useState(false);
  const [notification, setNotification] = useState(null);
  const submitted = useRef(false);

  useEffect(() => {
    if (!notification) return;
    const timer = setTimeout(() => setNotification(null), 3300);
    return () => clearTimeout(timer);
  }, [notification]);

  function toast(message) {
    setNotification({ message });
  }
  function go(page) {
    setScreen(page);
    setVoice(false);
  }
  function update(key, value) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }
  function service(id) {
    if (["transfer", "qr", "history", "more", "recipients"].includes(id)) {
      if (id === "transfer") {
        setForm(emptyTransfer());
        submitted.current = false;
      }
      go(id);
    } else if (mockServices[id]) go(id);
  }
  function quickTransfer(recipient) {
    setForm({
      ...emptyTransfer(),
      bank: recipient.bank,
      account: recipient.account,
      recipient: recipient.recipient,
      nickname: recipient.nickname || "",
    });
    submitted.current = false;
    go("transfer");
  }
  function saveRecipient(input = form) {
    const error = validateRecipient(input);
    if (error) {
      toast(error);
      return false;
    }
    const saved = {
      bank: input.bank,
      account: input.account.trim(),
      recipient: input.recipient.trim(),
      nickname: (input.nickname || "").trim(),
    };
    const next = [
      saved,
      ...recipients.filter(
        (r) => r.bank !== saved.bank || r.account !== saved.account,
      ),
    ];
    setRecipients(next);
    toast(
      persistRecipients(next)
        ? "Đã lưu người nhận và thông tin chuyển tiền nhanh."
        : "Đã lưu tạm. Trình duyệt không cho phép lưu sau khi tải lại trang.",
    );
    return true;
  }
  function removeRecipient(recipient) {
    const next = recipients.filter(
      (r) => r.bank !== recipient.bank || r.account !== recipient.account,
    );
    setRecipients(next);
    toast(
      persistRecipients(next)
        ? "Đã xóa người nhận."
        : "Đã xóa tạm. Trình duyệt không cho phép lưu thay đổi.",
    );
  }
  function acceptQR(parsed) {
    setForm({ ...emptyTransfer(), ...parsed, qrLocked: true });
    submitted.current = false;
    go("transfer");
    if (!parsed.recipient)
      toast(
        "Đã đọc tài khoản QR. Vui lòng nhập và kiểm tra tên người nhận trước khi tiếp tục.",
      );
  }
  function onContinue() {
    const error = validateTransfer(form);
    if (error) return toast(error);
    setForm((previous) => ({
      ...previous,
      account: previous.account.trim(),
      memo: previous.memo.trim() || config.transfer.defaultMemo,
    }));
    submitted.current = false;
    go("confirm");
  }
  function finish() {
    if (submitted.current) return;
    submitted.current = true;
    setTransfers((previous) => [{ ...form }, ...previous]);
    go("success");
  }
  return (
    <div className="shell">
      <div className="device">
        {screen !== "home" && (
          <Header
            title={titles[screen] || services.find((s) => s[0] === screen)?.[1]}
            go={go}
            toast={toast}
          />
        )}
        {screen === "home" && (
          <Home go={go} toast={toast} service={service} transfers={transfers} />
        )}
        {["transfer", "qr", "recipients"].includes(screen) && (
          <TransferMethods screen={screen} go={go} service={service} />
        )}
        {screen === "transfer" && (
          <Transfer
            form={form}
            update={update}
            go={go}
            onContinue={onContinue}
            saveRecipient={saveRecipient}
          />
        )}
        {screen === "qr" && <Qr acceptQR={acceptQR} toast={toast} />}
        {screen === "confirm" && (
          <Confirm form={form} go={go} finish={finish} />
        )}
        {screen === "success" && (
          <Success
            form={form}
            count={transfers.length}
            go={go}
            service={service}
          />
        )}
        {screen === "history" && <History transfers={transfers} />}
        {screen === "more" && <More service={service} />}
        {screen === "recipients" && (
          <Recipients
            recipients={recipients}
            quickTransfer={quickTransfer}
            removeRecipient={removeRecipient}
            saveRecipient={saveRecipient}
          />
        )}
        {mockServices[screen] && (
          <MockService key={screen} id={screen} go={go} />
        )}
        <Navbar screen={screen} go={go} />
        <button
          className="voicefab"
          title="Điều khiển bằng giọng nói"
          onClick={() => setVoice((v) => !v)}
        >
          <Icon name="mic" size={23} />
        </button>
        {voice && <VoicePanel close={() => setVoice(false)} />}
        {notification && (
          <div className="toast" role="status">
            {notification.message}
          </div>
        )}
      </div>
    </div>
  );
}
