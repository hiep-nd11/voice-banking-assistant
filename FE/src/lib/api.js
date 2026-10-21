import { config } from "./config.js";
import { loadRecipients } from "./recipients.js";

const endpoint = (path) => `${(config?.api?.baseUrl || "").replace(/\/$/, "")}/api${path}`;
export const sessionKey = "vtb.assistant.session";

export async function streamAssistant({
  message,
  audio,
  sessionId,
  signal,
  onEvent,
  quickRecipients = loadRecipients(),
}) {
  const customerId = config?.api?.customerId ?? 2;
  let body;
  if (audio) {
    body = new FormData();
    body.append("audio", audio, "recording.wav");
    body.append("customer_id", String(customerId));
    body.append("quick_recipients", JSON.stringify(quickRecipients));
    if (sessionId) body.append("session_id", sessionId);
  } else
    body = JSON.stringify({
      message,
      session_id: sessionId || null,
      customer_id: customerId,
      quick_recipients: quickRecipients,
    });
  const response = await fetch(endpoint(audio ? "/voice" : "/chat"), {
    method: "POST",
    body,
    signal,
    headers: audio ? undefined : { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const reason =
      typeof detail.detail === "string"
        ? detail.detail
        : Array.isArray(detail.detail)
          ? detail.detail.map((issue) => issue.msg).join("; ")
          : null;
    throw new Error(reason || `Không kết nối được backend (HTTP ${response.status}).`);
  }
  if (!response.body) throw new Error("Trình duyệt không hỗ trợ nhận phản hồi trực tiếp.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  const dispatch = (frame) => {
    const data = frame
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "error") throw new Error(event.message || "Backend xử lý thất bại.");
    if (event.type === "done") completed = true;
    onEvent(event);
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        dispatch(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (!completed) throw new Error("Kết nối bị ngắt trước khi hoàn tất. Vui lòng thử lại.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function loadConversation(sessionId, signal) {
  const response = await fetch(endpoint(`/sessions/${encodeURIComponent(sessionId)}/messages`), {
    signal,
  });
  if (!response.ok) throw new Error("Không tải được lịch sử hội thoại.");
  return (await response.json()).messages;
}

export async function loadWorkflow(sessionId, signal) {
  const response = await fetch(endpoint(`/workflows/${encodeURIComponent(sessionId)}`), {
    signal,
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Không khôi phục được kịch bản đang thực hiện.");
  return (await response.json()).flow;
}

export async function sendWorkflowEvent(sessionId, request) {
  const response = await fetch(endpoint(`/workflows/${encodeURIComponent(sessionId)}/events`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(
      typeof data.detail === "string" ? data.detail : "Không cập nhật được yêu cầu.",
    );
    error.status = response.status;
    throw error;
  }
  return data.events;
}
