# ASR Voice WebSocket API

> Tài liệu tham khảo WebSocket từ artifact ngày 20/10/2026. Ứng dụng hiện dùng upload WAV qua `/api/voice`, BE gọi `${ASR_BASE_URL}/transcribe`. WebSocket/wake word dưới đây chưa được tích hợp vào FE; endpoint tham khảo không thay thế cấu hình ASR hiện tại.

Client stream audio micro (PCM16 mono 16 kHz) qua một WebSocket; server tự phát hiện wake word, cắt câu bằng VAD và trả về văn bản tiếng Việt dưới dạng JSON.

## Kết nối

Mở một WebSocket tới endpoint dưới đây; mỗi kết nối là một phiên nghe độc lập.

| Mục | Giá trị |
|---|---|
| URL | `wss://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24.agentbase-runtime.aiplatform.vngcloud.vn/ws/voice` |
| Giao thức | WebSocket (TLS), không subprotocol |
| Xác thực | Không có — endpoint public |
| Keep-alive | Server ping mỗi 20 s, timeout 20 s |
| Số kết nối | Không giới hạn cứng; mỗi kết nối tạo model wakeword + VAD riêng (~vài chục MB RAM) |

Chạy local: `ws://127.0.0.1:8001/ws/voice`.

## Luồng hoạt động

Client chỉ cần gửi audio liên tục và lắng nghe event; server tự chuyển trạng thái.

1. Client kết nối; server gửi `ready`.
2. Client stream audio micro liên tục dạng binary frame, kể cả lúc im lặng.
3. Server chờ wake word (hiện tại: "Hey Jarvis"). Khi phát hiện → gửi `wake_up`.
4. Server nghe câu lệnh bằng VAD; câu kết thúc khi im lặng 700 ms sau khi đã có tiếng nói.
5. Server chạy STT trên đoạn câu lệnh → gửi `text`.
6. Server quay lại bước 3. Mỗi lần wake word chỉ nhận một câu.

Client không cần gửi lệnh start/stop; đóng WebSocket để kết thúc phiên.

## Gửi audio (client → server)

Mọi message client gửi phải là binary frame chứa raw PCM, không header WAV.

| Thuộc tính | Giá trị |
|---|---|
| Encoding | PCM signed 16-bit little-endian (pcm_s16le) |
| Sample rate | 16000 Hz |
| Kênh | 1 (mono) |
| Kích thước frame | Tùy ý, số byte phải chẵn; khuyến nghị 100 ms = 1600 mẫu = 3200 byte |
| Nhịp gửi | Theo thời gian thực (stream từ micro) |

- Micro thu 44.1/48 kHz hoặc float32 → client phải resample về 16 kHz và chuyển sang int16 trước khi gửi.
- Không gửi text frame: server coi là lỗi và đóng phiên.

## Sự kiện server → client

Server gửi text frame JSON; phân biệt bằng trường `type`. Client nên bỏ qua type lạ để tương thích phiên bản sau.

| type | Khi nào | Trường |
|---|---|---|
| `ready` | Ngay sau khi kết nối, một lần | `sample_rate` (int), `format` (string), `channels` (int) |
| `wake_up` | Phát hiện wake word | `score` (float 0–1) |
| `text` | Xong STT một câu lệnh | `text` (string, có thể rỗng) |
| `error` | STT lỗi, hoặc lỗi phiên | `message` (string) |

```json
{"type": "ready", "sample_rate": 16000, "format": "pcm_s16le", "channels": 1}
{"type": "wake_up", "score": 0.93}
{"type": "text", "text": "chuyển khoản cho mẹ năm trăm nghìn"}
{"type": "error", "message": "STT failed: ..."}
```

- `text` do model Zipformer trả về, thường là CHỮ HOA, không dấu câu.
- Luôn có `wake_up` trước mỗi `text`.

## Thông số hành vi

Các giá trị đang chạy trên runtime; chỉnh được phía server qua biến môi trường.

| Thông số | Giá trị | Ý nghĩa |
|---|---|---|
| Wake word | "Hey Jarvis" | Model openWakeWord hey_jarvis |
| Ngưỡng wake word | 0.2 | `WAKEWORD_THRESHOLD`; thấp → dễ bị kích hoạt nhầm |
| Ngưỡng VAD | 0.5 | `VAD_THRESHOLD` (Silero VAD) |
| Im lặng kết thúc câu | 700 ms | Sau khi đã có tiếng nói |
| Cooldown sau text | ~1.3 s | Không nhận wake word trong khoảng này |
| Độ dài câu tối đa | Không giới hạn | Nên giữ dưới ~15 s |

Độ trễ từ lúc người dùng dừng nói tới text ≈ 700 ms + thời gian STT trên CPU. Trong lúc STT chạy, client cứ tiếp tục gửi audio; server xử lý bù sau.

## Lỗi và đóng kết nối

Lỗi STT không làm mất phiên; lỗi giao thức thì server gửi `error` rồi đóng kết nối.

| Tình huống | Server phản hồi | Phiên |
|---|---|---|
| STT lỗi một câu | `error` với `STT failed: ...` | Tiếp tục, quay về chờ wake word |
| Frame có số byte lẻ | `error` | Đóng |
| Gửi text frame | `error` | Đóng |
| Lỗi nạp model phía server | `error` | Đóng |
| Runtime đang restart/deploy | Kết nối bị ngắt hoặc HTTP 502/503 | — |

Client nên tự kết nối lại sau 2–5 s khi bị đóng; trạng thái không được giữ giữa các kết nối.

## Endpoint HTTP phụ

Cùng host với WebSocket.

| Method + path | Request | Response |
|---|---|---|
| GET `/` | — | Trang demo: thu micro trên trình duyệt, stream qua /ws/voice |
| GET `/health` | — | `200 {"status": "ok"}` khi sẵn sàng |
| POST `/transcribe` | Body = file WAV PCM16 mono 16 kHz, hoặc raw PCM16 | `200 {"text": "..."}`; 400 nếu sai định dạng |

`/transcribe` chạy STT thẳng trên cả file, không qua wake word/VAD:

```bash
curl -X POST --data-binary @cau_lenh.wav https://endpoint-5c01bb45-f992-4e76-86a8-30b2de404506.agentbase-runtime.aiplatform.vngcloud.vn/transcribe
```

## Code mẫu

Python (pip install websockets sounddevice numpy) — bản đầy đủ có resample và tự kết nối lại nằm ở `asr-system/test/micro.py` trong repo.

```python
import asyncio, json
import sounddevice as sd, websockets

URL = "wss://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24.agentbase-runtime.aiplatform.vngcloud.vn/ws/voice"

async def main():
    loop = asyncio.get_running_loop()
    q = asyncio.Queue(maxsize=50)

    def on_audio(indata, frames, t, status):
        loop.call_soon_threadsafe(q.put_nowait, indata[:, 0].tobytes())

    async with websockets.connect(URL, max_size=None) as ws:
        async def receive():
            async for msg in ws:
                ev = json.loads(msg)
                if ev["type"] == "wake_up":
                    print("wake up", ev["score"])
                elif ev["type"] == "text":
                    print("text:", ev["text"])
                elif ev["type"] == "error":
                    print("error:", ev["message"])
        rx = asyncio.create_task(receive())
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                            blocksize=1600, callback=on_audio):
            while not rx.done():
                await ws.send(await q.get())

asyncio.run(main())
```

JavaScript trình duyệt — cần trang chạy HTTPS để được dùng micro; trình duyệt thu 44.1/48 kHz nên phải downsample.

```javascript
const ws = new WebSocket("wss://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24.agentbase-runtime.aiplatform.vngcloud.vn/ws/voice");
ws.binaryType = "arraybuffer";
ws.onmessage = (m) => {
  const ev = JSON.parse(m.data);
  if (ev.type === "wake_up") console.log("wake up", ev.score);
  if (ev.type === "text") console.log("text:", ev.text);
  if (ev.type === "error") console.error(ev.message);
};

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
