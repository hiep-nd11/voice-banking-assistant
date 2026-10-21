"""TTS client — Gemini TTS (gemini-3.1-flash-tts-preview).

Text tiếng Việt → audio WAV/PCM 24kHz mono (base64) để phát qua SSE event "audio".

Gemini TTS có 2 schema REST, tùy thế hệ model:
1. generateContent (kinh điển): POST /v1beta/models/{model}:generateContent
   với generationConfig.responseModalities=["AUDIO"] + speechConfig.voiceConfig.
2. interactions (mới): POST /v1beta/interactions với response_format={"type": "audio"}.

Module thử lần lượt và cache lại endpoint hoạt động cho các lần gọi sau.

Chi tiết: https://ai.google.dev/gemini-api/docs/speech-generation
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from app.core.config import settings


class TTSError(RuntimeError):
    """Lỗi khi gọi TTS."""


# --------------------------------------------------------------- chuẩn hóa text cho đọc

_MD_PATTERNS = [
    (re.compile(r"```.*?```", re.S), " "),   # code block
    (re.compile(r"`([^`]*)`"), r"\1"),       # inline code
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"),  # link -> text
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.M), ""),     # heading
    (re.compile(r"(\*\*|__|\*|_)"), ""),     # bold/italic
    (re.compile(r"^\s*[-*+]\s+", re.M), ""),  # bullet
    (re.compile(r"^\s*>\s?", re.M), ""),      # blockquote
]

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U00002190-\U000021FF\U00002B00-\U00002BFF]+"
)

MAX_TTS_CHARS = 1200  # tránh đọc lại bảng biểu/đoạn quá dài


def clean_for_speech(text: str) -> str:
    """Bỏ markdown/emoji, gộp khoảng trắng — giữ lại con số và nội dung chính."""
    out = text
    for pat, repl in _MD_PATTERNS:
        out = pat.sub(repl, out)
    out = _EMOJI_RE.sub("", out)
    out = re.sub(r"\n{2,}", ". ", out)
    out = re.sub(r"[ \t]+", " ", out).strip()
    return out[:MAX_TTS_CHARS]


# --------------------------------------------------------------- các schema REST

def _headers() -> dict:
    return {
        "x-goog-api-key": settings.tts_api_key,
        "Content-Type": "application/json",
    }


async def _tts_generate_content(client: httpx.AsyncClient, text: str) -> tuple[str, str]:
    """Schema kinh điển: models/{model}:generateContent."""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": settings.tts_voice}}},
        },
    }
    url = f"{settings.tts_base_url.rstrip('/')}/v1beta/models/{settings.tts_model}:generateContent"
    resp = await client.post(url, json=payload, headers=_headers())
    if resp.status_code != 200:
        raise TTSError(f"generateContent trả {resp.status_code}: {resp.text[:200]}")
    try:
        part = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        return part["data"], part.get("mimeType", "audio/L16;rate=24000")
    except (KeyError, IndexError, TypeError) as e:
        raise TTSError(f"generateContent response lạ: {e}") from e


async def _tts_interactions(client: httpx.AsyncClient, text: str) -> tuple[str, str]:
    """Schema mới: /v1beta/interactions."""
    payload = {
        "model": settings.tts_model,
        "input": [{
            "type": "user_input",
            "content": [{"type": "text", "text": text}],
        }],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": settings.tts_voice}]},
    }
    url = f"{settings.tts_base_url.rstrip('/')}/v1beta/interactions"
    resp = await client.post(url, json=payload, headers=_headers())
    if resp.status_code != 200:
        raise TTSError(f"interactions trả {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        for step in data.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for c in step.get("content", []):
                if c.get("type") == "audio" and c.get("data"):
                    mime = c.get("mimeType") or "audio/wav"
                    return c["data"], mime
        raise TTSError("interactions không có audio trong response")
    except TTSError:
        raise
    except (KeyError, TypeError) as e:
        raise TTSError(f"interactions response lạ: {e}") from e


# endpoint đã xác định hoạt động (cache giữa các lần gọi)
_working_impl: str | None = None


async def synthesize(text: str) -> tuple[str, str]:
    """Text → (audio_base64, mime_type). Ném TTSError nếu cả 2 schema đều lỗi."""
    cleaned = clean_for_speech(text)
    if not cleaned:
        raise TTSError("Không có nội dung để đọc (text rỗng sau khi làm sạch)")

    impls = {
        "generateContent": _tts_generate_content,
        "interactions": _tts_interactions,
    }
    global _working_impl
    order = [_working_impl] if _working_impl else list(impls)
    order = [i for i in order if i]  # type: ignore[list-item]

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=120) as client:
        for name in order:
            try:
                b64, mime = await impls[name](client, cleaned)
                _working_impl = name
                return b64, mime
            except Exception as e:  # thử schema kế tiếp
                last_err = e
    raise TTSError(f"Cả 2 schema TTS đều lỗi (lần cuối: {last_err})")


def to_wav_bytes(pcm_b64: str, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Bọc raw PCM thành WAV có header RIFF (client phát trực tiếp được)."""
    pcm = base64.b64decode(pcm_b64)
    import struct

    n = len(pcm)
    header = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate,
                                    sample_rate * channels * sample_width, channels * sample_width, sample_width * 8)
    header += b"data" + struct.pack("<I", n)
    return header + pcm
