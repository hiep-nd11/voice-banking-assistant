import asyncio
import io

import librosa
import numpy as np
from fastapi import FastAPI, HTTPException, Request

from app.stt_base import ZipformerSTTEngine


SAMPLE_RATE = 16000

app = FastAPI(title="ASR API")


# Load STT một lần khi khởi động, dùng chung cho mọi request.
stt_engine = ZipformerSTTEngine()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(request: Request):
    """
    Body: file audio bất kỳ (WAV/FLAC/OGG/MP3..., mọi sample rate / số kênh),
    hoặc raw PCM16 mono 16 kHz.
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Body rỗng")

    try:
        # librosa tự đọc WAV/FLAC/OGG/MP3..., downmix về mono và resample về 16 kHz.
        audio, _ = await asyncio.to_thread(
            librosa.load, io.BytesIO(body), sr=SAMPLE_RATE, mono=True
        )
    except Exception:
        # Không đọc được như file audio -> coi là raw PCM16 mono 16 kHz.
        pcm_bytes = body[: len(body) - len(body) % 2]
        audio = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0

    text = await stt_engine.transcribe(audio, sample_rate=SAMPLE_RATE)
    return {"text": text}
