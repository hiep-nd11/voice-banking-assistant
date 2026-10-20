"""STT client — ASR Voice API (VNG Cloud agentbase-runtime).

File mode: POST /transcribe với WAV PCM16 mono 16kHz (sau khi chuẩn hóa).
Bỏ qua wake word/VAD, STT thẳng cả file — dùng cho /api/voice.

Streaming mode (browser ↔ /ws/voice, wake word "Hey Jarvis" + VAD): client giữ
WebSocket trực tiếp với ASR service rồi forward text qua /api/chat — xem
docs/voice-streaming-client.md.

Chi tiết API: docs/asr-voice-websocket-api.md
"""
from __future__ import annotations

import io
import wave
from math import gcd

import httpx
import numpy as np
from scipy.signal import resample_poly

from app.core.config import settings

TARGET_RATE = 16000


class STTError(RuntimeError):
    """Lỗi khi gọi ASR service."""


def to_wav16k(audio: bytes) -> bytes:
    """Chuẩn hóa WAV (bất kỳ sample rate / số kênh, 16-bit) → PCM16 mono 16kHz.

    Non-WAV (raw PCM16 16kHz mono) gửi nguyên bản.
    """
    if not audio[:4] == b"RIFF":
        return audio  # raw PCM — coi như đã đúng định dạng

    try:
        with wave.open(io.BytesIO(audio)) as w:
            ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
            assert sw == 2, "chỉ hỗ trợ WAV 16-bit"
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, ch).mean(axis=1)
    except (wave.Error, AssertionError) as e:
        raise STTError(f"Định dạng WAV không hợp lệ: {e}") from e

    if sr != TARGET_RATE:
        g = gcd(TARGET_RATE, sr)
        a = resample_poly(a, TARGET_RATE // g, sr // g)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes(np.clip(a, -32768, 32767).astype("<i2").tobytes())
    return buf.getvalue()


async def transcribe_file(audio: bytes) -> str:
    """STT một file audio (WAV 16-bit bất kỳ sample rate/kênh, hoặc raw PCM16).

    Trả về text tiếng Việt (thường CHỮ HOA, không dấu câu).
    """
    payload = to_wav16k(audio)
    url = f"{settings.asr_base_url}/transcribe"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, content=payload)
    if resp.status_code != 200:
        raise STTError(f"ASR /transcribe trả {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    text = (data.get("text") or "").strip()
    if not text:
        raise STTError("ASR trả text rỗng (không nhận được lời nói)")
    return text
