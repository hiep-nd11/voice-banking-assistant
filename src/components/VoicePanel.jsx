import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";

export default function VoicePanel({ close }) {
  const streamRef = useRef(null);
  const requestRef = useRef(0);
  const [listening, setListening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  function releaseMicrophone() {
    requestRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  useEffect(() => releaseMicrophone, []);

  function stop() {
    releaseMicrophone();
    setListening(false);
    setStarting(false);
  }

  async function start() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        "Không thể mở micro. Hãy dùng trình duyệt hỗ trợ trên HTTPS hoặc localhost.",
      );
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
      // Audio is available here for a future voice-to-text integration.
      setListening(true);
    } catch {
      if (request === requestRef.current) {
        setError(
          "Không mở được micro. Vui lòng kiểm tra thiết bị và quyền truy cập micro.",
        );
      }
    } finally {
      if (request === requestRef.current) setStarting(false);
    }
  }

  return (
    <div className="voicebox" role="dialog" aria-label="Voice Banking">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <b style={{ fontSize: 14 }}>
          <Icon name="mic" size={17} /> Voice Banking
        </b>
        <button aria-label="Đóng trợ lý" onClick={close}>
          <Icon name="close" size={15} />
        </button>
      </div>
      <p>
        Bật micro để nói. Nội dung giọng nói chưa được chuyển thành văn bản hoặc
        xử lý.
      </p>
      <button
        onClick={listening || starting ? stop : start}
        aria-pressed={listening}
      >
        <Icon name="mic" size={15} />{" "}
        {listening ? "Dừng nói" : starting ? "Hủy mở micro" : "Bắt đầu nói"}
      </button>
      <p role="status" style={{ margin: "8px 0 0" }}>
        {listening
          ? "Micro đang bật, bạn có thể nói..."
          : starting
            ? "Đang mở micro..."
            : "Micro đang tắt"}
      </p>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
