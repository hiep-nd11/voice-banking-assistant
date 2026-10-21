"""
Client test: thu micro, stream PCM16 mono 16 kHz tới /ws/voice, in event từ server.

    python test/micro.py                 # server local ws://127.0.0.1:8001/ws/voice
    python test/micro.py --cloud         # runtime trên GreenNode AgentBase
    python test/micro.py wss://.../ws/voice
    python test/micro.py --list-devices
    python test/micro.py --cloud --device 1 --save debug.wav
"""

import argparse
import asyncio
import json
import os
import sys
import time
import wave

import numpy as np
import sounddevice as sd
import websockets


LOCAL_URL = "ws://127.0.0.1:8001/ws/voice"
CLOUD_URL = (
    "wss://endpoint-9feaeccd-aa3a-4bf1-9553-e8891bb30e24"
    ".agentbase-runtime.aiplatform.vngcloud.vn/ws/voice"
)

SAMPLE_RATE = 16000
BLOCK_MS = 100

# Giới hạn queue (~5 s audio) để bộ nhớ không tăng vô hạn khi mạng chậm.
QUEUE_MAX_SIZE = 50
RECONNECT_DELAY_S = 2


def parse_args():
    parser = argparse.ArgumentParser(description="Test ASR qua micro")
    parser.add_argument("url", nargs="?", help="WebSocket URL (mặc định: server local)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--cloud", action="store_true", help="Dùng runtime GreenNode")
    target.add_argument("--local", action="store_true", help="Dùng server local :8001")
    parser.add_argument("--device", type=int, help="Index micro (xem --list-devices)")
    parser.add_argument("--list-devices", action="store_true", help="Liệt kê thiết bị âm thanh")
    parser.add_argument("--save", help="Lưu toàn bộ audio đã gửi ra file WAV")
    parser.add_argument("--no-meter", action="store_true", help="Tắt thanh mức âm")
    return parser.parse_args()


def resolve_url(args) -> str:
    if args.url:
        return args.url
    if args.cloud:
        return CLOUD_URL
    return os.getenv("SERVER_URL", LOCAL_URL)


def pick_input_rate(device) -> int:
    """Dùng 16 kHz nếu micro hỗ trợ, nếu không thì sample rate mặc định của micro."""
    try:
        sd.check_input_settings(device=device, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        return SAMPLE_RATE
    except Exception:
        return int(sd.query_devices(device, "input")["default_samplerate"])


def resample_to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == SAMPLE_RATE:
        return audio
    n_out = int(round(len(audio) * SAMPLE_RATE / rate))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio.astype(np.float32)).astype(np.int16)


class Display:
    """In event kèm thời gian; thanh mức âm ghi đè trên cùng một dòng."""

    def __init__(self, meter: bool):
        self.meter = meter
        self.t0 = time.monotonic()
        self.state = "chờ wake word"

    def _clear_line(self):
        if self.meter:
            sys.stdout.write("\r" + " " * 70 + "\r")

    def log(self, tag: str, msg: str = ""):
        self._clear_line()
        print(f"[{time.monotonic() - self.t0:7.2f}s] {tag:<10} {msg}", flush=True)

    def level(self, peak: float):
        if not self.meter:
            return
        bars = int(min(1.0, peak * 4) * 30)
        sys.stdout.write(f"\r  mic |{'#' * bars:<30}| {self.state}")
        sys.stdout.flush()


async def run_session(url, args, display, recorder) -> bool:
    """Một phiên WebSocket. Trả về True nếu nên kết nối lại."""
    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    input_rate = pick_input_rate(args.device)

    def enqueue(data: bytes):
        if audio_queue.full():
            audio_queue.get_nowait()  # bỏ block cũ nhất
        audio_queue.put_nowait(data)

    def audio_callback(indata, frames, time_info, status):
        if status:
            loop.call_soon_threadsafe(display.log, "[MIC]", str(status))
        pcm = resample_to_16k(indata[:, 0].copy(), input_rate)
        peak = float(np.abs(pcm).max()) / 32768.0 if len(pcm) else 0.0
        loop.call_soon_threadsafe(display.level, peak)
        loop.call_soon_threadsafe(enqueue, pcm.tobytes())

    async with websockets.connect(url, max_size=None, ping_interval=20, ping_timeout=20) as ws:
        display.log("[WS]", f"Đã kết nối {url}")

        async def receive_events():
            async for message in ws:
                event = json.loads(message)
                kind = event.get("type")
                if kind == "ready":
                    display.state = "chờ wake word"
                    display.log("[READY]", "Server sẵn sàng. Nói wake word rồi nói câu lệnh.")
                elif kind == "wake_up":
                    display.state = "ĐANG NGHE..."
                    display.log("[WAKE UP]", f"score={event.get('score', 0):.3f}")
                elif kind == "text":
                    display.state = "chờ wake word"
                    display.log("[TEXT]", event.get("text") or "(rỗng)")
                elif kind == "error":
                    display.log("[ERROR]", str(event.get("message")))
                else:
                    display.log("[EVENT]", json.dumps(event, ensure_ascii=False))

        receiver = asyncio.create_task(receive_events())
        try:
            with sd.InputStream(
                device=args.device,
                samplerate=input_rate,
                channels=1,
                dtype="int16",
                blocksize=input_rate * BLOCK_MS // 1000,
                callback=audio_callback,
            ):
                rate_note = "" if input_rate == SAMPLE_RATE else f" (resample {input_rate} → 16000 Hz)"
                display.log("[MIC]", f"Đang thu âm{rate_note}. Ctrl+C để dừng.")

                while not receiver.done():
                    try:
                        data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    await ws.send(data)
                    if recorder is not None:
                        recorder.writeframes(data)
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)

        # receiver kết thúc = server đóng kết nối.
        exc = receiver.exception() if not receiver.cancelled() else None
        display.log("[WS]", f"Server đóng kết nối{f': {exc}' if exc else ''}")
        return True


async def main():
    args = parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    url = resolve_url(args)
    display = Display(meter=not args.no_meter)

    recorder = None
    if args.save:
        recorder = wave.open(args.save, "wb")
        recorder.setnchannels(1)
        recorder.setsampwidth(2)
        recorder.setframerate(SAMPLE_RATE)

    try:
        while True:
            try:
                reconnect = await run_session(url, args, display, recorder)
            except (OSError, websockets.exceptions.WebSocketException) as exc:
                hint = ""
                if isinstance(exc, ConnectionRefusedError) and "127.0.0.1" in url:
                    hint = " (server local chưa chạy? `uvicorn app.main:app --port 8001` hoặc dùng --cloud)"
                display.log("[WS]", f"{type(exc).__name__}: {exc}{hint}")
                reconnect = True
            if not reconnect:
                break
            display.log("[WS]", f"Kết nối lại sau {RECONNECT_DELAY_S}s...")
            await asyncio.sleep(RECONNECT_DELAY_S)
    finally:
        if recorder is not None:
            recorder.close()
            display.log("[SAVE]", args.save)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã dừng microphone.")
