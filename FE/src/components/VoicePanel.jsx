import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { loadConversation, sessionKey, streamAssistant } from "../lib/api.js";
import { captureAudio } from "../lib/audio.js";

export default function VoicePanel({
  close,
  collapsed = false,
  onAssistantEvent,
  externalReply,
  quickRecipients,
}) {
  const streamRef = useRef(null);
  const recording = useRef(null);
  const requestRef = useRef(0);
  const controller = useRef(null);
  const session = useRef(sessionStorage.getItem(sessionKey));
  const timer = useRef(null);
  const [listening, setListening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const playback = useRef(null);
  const externalId = useRef(null);
  const panel = useRef(null);

  useEffect(() => {
    if (collapsed) return;
    const previous = document.activeElement;
    const siblings = [...(panel.current?.parentElement?.parentElement?.children || [])].filter(
      (element) => element !== panel.current?.parentElement,
    );
    siblings.forEach((element) => {
      element.inert = true;
    });
    panel.current?.querySelector("button")?.focus();
    return () => {
      siblings.forEach((element) => {
        element.inert = false;
      });
      if (previous?.isConnected) previous.focus();
      else document.querySelector(".voicefab")?.focus();
    };
  }, [collapsed]);

  useEffect(() => {
    if (!externalReply || externalId.current === externalReply.id) return;
    externalId.current = externalReply.id;
    if (externalReply.text)
      setMessages((rows) => [...rows, { role: "assistant", content: externalReply.text }]);
    if (externalReply.sessionId) session.current = externalReply.sessionId;
    if (externalReply.audio) playReply(externalReply.audio);
  }, [externalReply]);

  useEffect(() => {
    if (!collapsed) return;
    releaseMicrophone();
    recording.current?.();
    recording.current = null;
    setListening(false);
    setStarting(false);
  }, [collapsed]);

  function releaseMicrophone() {
    requestRef.current += 1;
    clearTimeout(timer.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }
  useEffect(() => {
    const history = new AbortController();
    if (session.current)
      loadConversation(session.current, history.signal)
        .then((rows) =>
          setMessages((current) =>
            current.length
              ? current
              : rows.filter((row) => ["user", "assistant"].includes(row.role)),
          ),
        )
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    return () => {
      history.abort();
      controller.current?.abort();
      playback.current?.pause();
      releaseMicrophone();
      recording.current?.();
      recording.current = null;
    };
  }, []);

  function playReply(audio) {
    if (!/^audio\/[\w.+-]+$/.test(audio.format)) return;
    playback.current?.pause();
    const player = new Audio(`data:${audio.format};base64,${audio.data}`);
    playback.current = player;
    void player.play().catch(() => {
      if (playback.current === player)
        setError(
          "Không phát được giọng đọc. Vui lòng kiểm tra quyền phát âm thanh của trình duyệt.",
        );
    });
  }

  async function send({ text, blob }) {
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    playback.current?.pause();
    if (text) setMessages((rows) => [...rows, { role: "user", content: text }]);
    let answer = "";
    let added = false;
    let audioReceived = false;
    try {
      await streamAssistant({
        message: text,
        audio: blob,
        sessionId: session.current,
        quickRecipients,
        signal: controller.current.signal,
        onEvent: (event) => {
          if (event.type === "session" || event.type === "done") {
            session.current = event.session_id;
            sessionStorage.setItem(sessionKey, event.session_id);
          }
          onAssistantEvent?.(event);
          if (event.type === "transcript")
            setMessages((rows) => [...rows, { role: "user", content: event.text }]);
          if (event.type === "token") {
            answer += event.content;
            const content = answer;
            const replace = added;
            setMessages((rows) =>
              replace
                ? [...rows.slice(0, -1), { role: "assistant", content }]
                : [...rows, { role: "assistant", content }],
            );
            added = true;
          }
          if (event.type === "audio" && !audioReceived && /^audio\/[\w.+-]+$/.test(event.format)) {
            audioReceived = true;
            playReply(event);
          }
          if (event.type === "tts_error")
            setError("Không tạo được giọng đọc. Bạn vẫn có thể đọc câu trả lời.");
          if (event.type === "done") {
            session.current = event.session_id;
            sessionStorage.setItem(sessionKey, event.session_id);
          }
        },
      });
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      if (!controller.current.signal.aborted) setBusy(false);
    }
  }

  function stop() {
    const blob = recording.current?.();
    recording.current = null;
    releaseMicrophone();
    setListening(false);
    setStarting(false);
    if (blob) void send({ blob });
  }
  async function start() {
    setError("");
    playback.current?.pause();
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Không thể mở micro. Hãy dùng trình duyệt hỗ trợ trên HTTPS hoặc localhost.");
      return;
    }
    const request = ++requestRef.current;
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (request !== requestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const finish = await captureAudio(stream);
      if (request !== requestRef.current) {
        finish();
        return;
      }
      recording.current = finish;
      setListening(true);
      timer.current = setTimeout(stop, 30000);
    } catch (e) {
      if (request === requestRef.current) {
        releaseMicrophone();
        setStarting(false);
        setError(
          e.message || "Không mở được micro. Vui lòng kiểm tra thiết bị và quyền truy cập micro.",
        );
      }
    } finally {
      if (request === requestRef.current) setStarting(false);
    }
  }

  if (collapsed) return null;

  return (
    <div
      className="voice-overlay"
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={panel}
        className="voicebox"
        role="dialog"
        aria-modal="true"
        aria-label="Voice Banking"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            close();
          }
          if (event.key === "Tab") {
            const controls = [
              ...panel.current.querySelectorAll(
                "button:not(:disabled), input:not(:disabled), audio[controls]",
              ),
            ];
            const first = controls[0],
              last = controls.at(-1);
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <b style={{ fontSize: 14 }}>
            <Icon name="mic" size={17} /> Voice Banking
          </b>
          <button aria-label="Đóng trợ lý" onClick={close}>
            <Icon name="close" size={15} />
          </button>
        </div>
        <p>Nhập câu hỏi hoặc thu âm tối đa 30 giây, sau đó bấm Dừng nói để gửi.</p>
        <div className="assistant-messages" aria-live="polite">
          {messages.map((row, i) => (
            <p key={i}>
              <b>{row.role === "user" ? "Bạn" : "Trợ lý"}: </b>
              {row.content}
            </p>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!message.trim() || busy || listening || starting) return;
            const text = message.trim();
            setMessage("");
            void send({ text });
          }}
        >
          <input
            aria-label="Tin nhắn cho trợ lý"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Hỏi trợ lý ngân hàng..."
            disabled={busy || listening || starting}
          />
          <button type="submit" disabled={busy || listening || starting || !message.trim()}>
            Gửi
          </button>{" "}
          <button
            type="button"
            disabled={busy}
            onClick={listening || starting ? stop : start}
            aria-pressed={listening}
          >
            <Icon name="mic" size={15} />{" "}
            {listening ? "Dừng nói" : starting ? "Hủy mở micro" : "Bắt đầu nói"}
          </button>
        </form>
        <p role="status">
          {busy
            ? "Trợ lý đang xử lý..."
            : listening
              ? "Micro đang bật, bạn có thể nói..."
              : starting
                ? "Đang mở micro..."
                : "Micro đang tắt"}
        </p>
        {error && <p role="alert">{error}</p>}
      </div>
    </div>
  );
}
