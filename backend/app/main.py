"""FastAPI entry point — Agent runtime (chưa gắn DB/scheduler)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.chat import router as chat_router
from app.api.voice import router as voice_router

app = FastAPI(title="VTB FinBot — Agent Runtime", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allow_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)


@app.get("/health")
async def runtime_health():
    """Health check cho AgentBase Runtime (bắt buộc GET /health trả 200)."""
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,
        "model": settings.llm_model if settings.llm_enabled else "fallback",
        "stt": "asr-voice-api",
        "tts_enabled": settings.tts_enabled,
        "tts_model": settings.tts_model if settings.tts_enabled else None,
    }
