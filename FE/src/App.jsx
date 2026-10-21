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
import BankingHistory from "./pages/BankingHistory.jsx";
import Analytics from "./pages/Analytics.jsx";
import More from "./pages/More.jsx";
import Recipients from "./pages/Recipients.jsx";
import MockService from "./pages/MockService.jsx";
import Finance from "./pages/Finance.jsx";
import Assets from "./pages/Assets.jsx";
import Workflow from "./pages/Workflow.jsx";
import { loadWorkflow, sendWorkflowEvent, sessionKey } from "./lib/api.js";
import { allowedNavigation, workflowTitle } from "./lib/workflows.js";
import { loadBankingData } from "./lib/banking.js";
import { loadRecipients, persistRecipients, validateRecipient } from "./lib/recipients.js";
import { mockServices } from "./lib/mockServices.js";
import { services } from "./lib/data.js";
import { emptyTransfer, validateTransfer } from "./lib/transfer.js";

const titles = config.screenTitles;

const DISPLAY_ONLY_SERVICES = new Set(["card", "card_open", "card_lock"]);

export default function App() {
  const [screen, setScreen] = useState("home");
  const [financeInitial, setFinanceInitial] = useState("month");
  const [form, setForm] = useState(emptyTransfer);
  const [transfers, setTransfers] = useState([]);
  const [balance, setBalance] = useState(() => config.user.balance);
  const [accounts, setAccounts] = useState(() => config.bankingAccounts || []);
  const [asOf, setAsOf] = useState(config.bankingAsOf);
  const [refreshing, setRefreshing] = useState(false);
  const refreshInFlight = useRef(false);
  const [recipients, setRecipients] = useState(loadRecipients);
  const [voice, setVoice] = useState(false);
  const [assistantMounted, setAssistantMounted] = useState(false);
  const [workflow, setWorkflow] = useState(null);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState("");
  const [externalReply, setExternalReply] = useState(null);
  const workflowInFlight = useRef(false);
  const workflowRetry = useRef(null);
  const [notification, setNotification] = useState(null);
  const submitted = useRef(false);

  useEffect(() => {
    const sessionId = sessionStorage.getItem(sessionKey);
    if (!sessionId || config.bankingSource !== "mcp") return;
    const controller = new AbortController();
    loadWorkflow(sessionId, controller.signal)
      .then((flow) => {
        if (!controller.signal.aborted && flow) {
          setWorkflow(flow);
          setAssistantMounted(true);
        }
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  function assistantEvent(event) {
    if ((event.type === "session" || event.type === "done") && event.session_id)
      sessionStorage.setItem(sessionKey, event.session_id);
    if (event.type === "flow_state") {
      setWorkflow((previous) =>
        previous && event.flow?.id === previous.id && event.flow.version < previous.version
          ? previous
          : event.flow,
      );
      setWorkflowError("");
      const flow = event.flow;
      if (flow?.intent.startsWith("transfer")) {
        const slots = flow.slots || {};
        const destination = slots.destination || slots.qr || slots.beneficiary || {};
        setForm({
          ...emptyTransfer(),
          bank: destination.bank || "",
          account: destination.account || destination.account_number || "",
          recipient: destination.recipient || destination.name || "",
          amount: slots.amount ? String(slots.amount) : "",
          memo: slots.note || "",
          qrLocked: Boolean(slots.qr),
          beneficiaryId: slots.beneficiary?.beneficiary_id,
          workflowId: flow.id,
        });
      }
    }
    if (allowedNavigation(event)) {
      if (event.screen === "finance") setFinanceInitial(event.feature);
      setScreen(event.screen);
      setVoice(false);
    }
  }

  async function workflowEvent(event, payload = {}) {
    if (!workflow || workflowInFlight.current) return;
    const sessionId = sessionStorage.getItem(sessionKey);
    if (!sessionId) return toast("Anh mở trợ lý để bắt đầu lại phiên hội thoại.");
    workflowInFlight.current = true;
    setWorkflowBusy(true);
    setWorkflowError("");
    const fingerprint = JSON.stringify({
      flow: workflow.id,
      version: workflow.version,
      event,
      payload,
    });
    const request =
      workflowRetry.current?.fingerprint === fingerprint
        ? workflowRetry.current.request
        : {
            flow_id: workflow.id,
            version: workflow.version,
            request_id: crypto.randomUUID(),
            event,
            payload,
          };
    workflowRetry.current = { fingerprint, request };
    try {
      const rows = await sendWorkflowEvent(sessionId, request);
      rows.forEach(assistantEvent);
      const text = rows
        .filter((row) => row.type === "token")
        .map((row) => row.content)
        .join("");
      setAssistantMounted(true);
      setExternalReply({
        id: request.request_id,
        sessionId,
        text,
        audio: rows.find((row) => row.type === "audio"),
      });
      workflowRetry.current = null;
      return rows.find((row) => row.type === "flow_state")?.flow;
    } catch (error) {
      setWorkflowError(error.message);
      toast(error.message);
      if (error.status) workflowRetry.current = null;
      if ([404, 409, 410].includes(error.status)) {
        try {
          setWorkflow(await loadWorkflow(sessionId));
        } catch {
          /* Keep visible error. */
        }
      }
    } finally {
      workflowInFlight.current = false;
      setWorkflowBusy(false);
    }
  }

  useEffect(() => {
    if (!notification) return;
    const timer = setTimeout(() => setNotification(null), 3300);
    return () => clearTimeout(timer);
  }, [notification]);

  function toast(message) {
    setNotification({ message });
  }
  async function refreshBanking() {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      const data = await loadBankingData(config);
      setAccounts(data.bankingAccounts || []);
      setBalance(data.user.balance);
      setAsOf(data.bankingAsOf);
    } catch (error) {
      toast(error.message);
    } finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  }
  function go(page) {
    if (["transfer", "qr", "recipients"].includes(page))
      setForm((old) => ({ ...old, workflowId: undefined }));
    setScreen(page);
    setVoice(false);
  }
  function update(key, value) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }
  async function changeTransferMethod(page) {
    if (workflow?.intent.startsWith("transfer")) {
      const result = await workflowEvent("cancel", {});
      if (result !== null) return;
    }
    if (page === "transfer") {
      setForm(emptyTransfer());
      submitted.current = false;
    }
    go(page);
  }
  function service(id) {
    if (["transfer", "qr", "recipients"].includes(id) && workflow?.intent.startsWith("transfer")) {
      void changeTransferMethod(id);
      return;
    }
    if (config.bankingSource === "mcp") {
      if (id === "save" || id === "loan") {
        go(id === "save" ? "savings" : "loans");
        return;
      }
    }
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
      ...recipients.filter((r) => r.bank !== saved.bank || r.account !== saved.account),
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
    if (workflow?.intent === "transfer_qr" && form.workflowId === workflow.id) {
      void workflowEvent("qr_scanned", parsed);
      return;
    }
    setForm({ ...emptyTransfer(), ...parsed, qrLocked: true });
    submitted.current = false;
    go("transfer");
    if (!parsed.recipient)
      toast("Đã đọc tài khoản QR. Vui lòng nhập và kiểm tra tên người nhận trước khi tiếp tục.");
  }
  async function onContinue() {
    const error = validateTransfer(form, balance);
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
    const error = validateTransfer(form, balance);
    if (error) return toast(error);
    submitted.current = true;
    if (workflow && form.workflowId === workflow.id) {
      const sessionId = sessionStorage.getItem(sessionKey);
      if (sessionId)
        void sendWorkflowEvent(sessionId, {
          flow_id: workflow.id,
          version: workflow.version,
          request_id: crypto.randomUUID(),
          event: "cancel",
          payload: {},
        }).catch(() => {});
      setWorkflow(null);
    }
    setBalance((previous) => previous - Number(form.amount) - config.transfer.fee);
    const now = new Date();
    const time = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}T${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    setTransfers((previous) => [{ ...form, time }, ...previous]);
    go("success");
  }
  function payService(id, values) {
    // Màn hình thẻ chỉ hiển thị giao diện mô phỏng, không cần backend thực hiện.
    if (DISPLAY_ONLY_SERVICES.has(id)) return "";
    if (config.bankingSource === "mcp") return "Backend chưa hỗ trợ thực hiện dịch vụ này.";
    if (!["phone", "save", "fund", "bill"].includes(id)) return "";
    const amount = Number(String(values.amount).replace(/[^0-9]/g, ""));
    if (!Number.isSafeInteger(amount) || amount <= 0) return "Số tiền không hợp lệ.";
    if (amount > balance) return "Số dư khả dụng không đủ để thực hiện giao dịch.";
    setBalance((previous) => previous - amount);
    setTransfers((previous) => [
      {
        recipient: mockServices[id].description,
        amount,
      },
      ...previous,
    ]);
    return "";
  }
  return (
    <div className="shell">
      <div className="device">
        {screen !== "home" && (
          <Header
            title={
              screen === "workflow"
                ? workflowTitle(workflow?.intent)
                : ["assets", "savings", "loans"].includes(screen)
                  ? "Tài sản của tôi"
                  : screen === "analytics"
                    ? "Phân tích thu chi"
                    : screen === "finance"
                      ? "Tiện ích tài chính"
                      : titles[screen] || services.find((s) => s[0] === screen)?.[1]
            }
            go={go}
            toast={toast}
          />
        )}
        {screen === "workflow" &&
          (workflow ? (
            <Workflow
              key={`${workflow.id}:${workflow.version}`}
              flow={workflow}
              busy={workflowBusy}
              error={workflowError}
              onEvent={workflowEvent}
            />
          ) : (
            <div className="page">
              <p className="note">Yêu cầu đã kết thúc hoặc hết hạn.</p>
              <button className="cta" onClick={() => go("home")}>
                Về trang chủ
              </button>
            </div>
          ))}
        {screen === "home" && (
          <Home go={go} toast={toast} service={service} transfers={transfers} balance={balance} />
        )}
        {(["transfer", "qr", "recipients"].includes(screen) ||
          (screen === "workflow" && workflow?.intent?.startsWith("transfer"))) && (
          <TransferMethods
            screen={
              screen === "workflow"
                ? workflow.intent === "transfer_qr"
                  ? "qr"
                  : "transfer"
                : screen
            }
            go={go}
            service={service}
            onSelect={changeTransferMethod}
          />
        )}
        {screen === "transfer" && (
          <Transfer
            form={form}
            update={update}
            go={changeTransferMethod}
            onContinue={onContinue}
            saveRecipient={saveRecipient}
            balance={balance}
            busy={workflowBusy}
            error={form.workflowId === workflow?.id ? workflowError : ""}
          />
        )}
        {screen === "qr" && <Qr acceptQR={acceptQR} toast={toast} />}
        {screen === "confirm" && (
          <Confirm form={form} go={go} finish={finish} edit={() => setScreen("transfer")} />
        )}
        {screen === "success" && (
          <Success form={form} count={transfers.length} go={go} service={service} />
        )}
        {screen === "history" &&
          (config.bankingSource === "mcp" ? (
            <BankingHistory transfers={transfers} />
          ) : (
            <History transfers={transfers} />
          ))}
        {screen === "analytics" && (
          <Analytics
            openFinance={(feature) => {
              setFinanceInitial(feature);
              go("finance");
            }}
          />
        )}
        {screen === "finance" && <Finance key={financeInitial} initial={financeInitial} />}
        {["assets", "savings", "loans"].includes(screen) && (
          <Assets
            key={screen}
            initial={screen === "loans" ? "loan" : screen === "savings" ? "savings" : "overview"}
            accounts={accounts}
            asOf={asOf}
            prepare={(feature) => {
              setFinanceInitial(feature);
              go("finance");
            }}
            refresh={refreshBanking}
            refreshing={refreshing}
          />
        )}
        {screen === "more" && (
          <More
            service={service}
            go={go}
            openFinance={(feature) => {
              setFinanceInitial(feature);
              go("finance");
            }}
          />
        )}
        {screen === "recipients" && (
          <Recipients
            recipients={recipients}
            quickTransfer={quickTransfer}
            removeRecipient={removeRecipient}
            saveRecipient={saveRecipient}
          />
        )}
        {mockServices[screen] && (
          <MockService key={screen} id={screen} go={go} payService={payService} />
        )}
        <Navbar screen={screen} go={go} />
        {!voice && (
          <button
            className="voicefab"
            title="Điều khiển bằng giọng nói"
            aria-label={workflow ? "Tiếp tục với trợ lý" : "Điều khiển bằng giọng nói"}
            aria-haspopup="dialog"
            onClick={() => {
              setAssistantMounted(true);
              setVoice((v) => !v);
            }}
          >
            <Icon name="mic" size={23} />
          </button>
        )}
        {assistantMounted && (
          <VoicePanel
            collapsed={!voice}
            close={() => setVoice(false)}
            onAssistantEvent={assistantEvent}
            externalReply={externalReply}
            quickRecipients={recipients}
          />
        )}
        {notification && (
          <div className="toast" role="status">
            {notification.message}
          </div>
        )}
      </div>
    </div>
  );
}
