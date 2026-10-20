# Tích hợp voice streaming (browser → ASR → backend)

Hai cách dùng ASR Voice API với backend — tùy độ realtime cần cho demo:

## Cách 1: File mode qua backend (đã tích hợp) — đơn giản, có record button

```
Browser (MediaRecorder) ──POST /api/voice (audio blob)──► Backend
                                                            │ POST /transcribe (ASR service)
                                                            ◄─ {"text": "..."}
                                                            │ run_agent (LLM + MCP)
Browser ◄────────SSE: transcript / token / tool_* / done────┘
```

- UI: bấm nút → nói → thả nút → nhận transcript + câu trả lời stream.
- Ghi âm phải xuất được WAV PCM16 mono 16kHz (MediaRecorder mặc định ra webm/opus — **không** đọc được bởi `/transcribe`; cần encoder WAV phía client, VD RecordRTC với `SampleRate: 16000, numberOfChannels: 1` hoặc tự gói WAV từ AudioWorklet).

```javascript
// Gọi /api/voice
const form = new FormData();
form.append("audio", wavBlob, "audio.wav");
form.append("session_id", sessionId);
form.append("customer_id", "2");

const resp = await fetch("/api/voice", { method: "POST", body: form });
const reader = resp.body.getReader();
// đọc SSE stream: event transcript -> token -> tool_call -> tool_result -> done
```

## Cách 2: Streaming mode — realtime, wake word "Hey Jarvis", hands-free

```
Browser ──ws wss://.../ws/voice (PCM16 16kHz frames)──► ASR service
Browser ◄──events: ready / wake_up / text─────────────── ASR service
   │
   └─ khi nhận {"type": "text"} ──POST /api/chat {"message": text}──► Backend
        Browser ◄────────SSE: token / tool_* / done──────────────────┘
```

- Không cần nút bấm: nói "Hey Jarvis" rồi nói câu lệnh, im 700ms là server trả transcript.
- Backend **không cần thay đổi gì** — client tự giữ WebSocket với ASR service và forward text qua `/api/chat`.
- Lưu ý: trang phải chạy HTTPS (hoặc localhost) để được dùng micro.

```javascript
const ASR_WS = "wss://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24.agentbase-runtime.aiplatform.vngcloud.vn/ws/voice";
const API = "http://localhost:8000"; // backend

const ws = new WebSocket(ASR_WS);
ws.binaryType = "arraybuffer";
ws.onmessage = (m) => {
  const ev = JSON.parse(m.data);
  if (ev.type === "wake_up") {
    showListeningIndicator(); // score = ev.score
  } else if (ev.type === "text" && ev.text) {
    sendToAgent(ev.text); // transcript từ giọng nói
  } else if (ev.type === "error") {
    console.error(ev.message);
  }
};

async function sendToAgent(text) {
  const resp = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, session_id: sessionId, customer_id: 2 }),
  });
  readSSE(resp.body); // token / tool_call / tool_result / done events
}

// --- stream micro: thu → resample 16kHz → int16 → gửi binary frame ---
const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
const ctx = new AudioContext();
const src = ctx.createMediaStreamSource(stream);
const node = ctx.createScriptProcessor(4096, 1, 1);
node.onaudioprocess = (e) => {
  const input = e.inputBuffer.getChannelData(0);
  const ratio = ctx.sampleRate / 16000;
  const out = new Int16Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const s = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  if (ws.readyState === WebSocket.OPEN) ws.send(out.buffer);
};
src.connect(node);
node.connect(ctx.destination);
```

## So sánh

| | Cách 1 — file mode | Cách 2 — streaming |
|---|---|---|
| Wake word | Không | "Hey Jarvis" |
| Độ trễ | Sau khi dừng nói: upload + STT cả file | ~700ms sau im lặng |
| UI | Nút bấm/giữ | Hands-free |
| Thay đổi backend | Có (`/api/voice` đã có sẵn) | Không |
| Yêu cầu client | Encoder WAV PCM16 16kHz | Chỉ WebSocket + resample |

Khuyến nghị demo: dùng **cách 2** cho trải nghiệm voice agent (nói "Hey Jarvis" rồi ra lệnh), giữ **cách 1** làm fallback khi mạng WebSocket không ổn định.
