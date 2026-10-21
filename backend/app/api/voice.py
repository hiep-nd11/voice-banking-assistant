"""POST /api/voice — SSE stream, đầu vào là audio (multipart/form-data).

Pipeline: audio → STT (/transcribe của ASR service) → agent → SSE events.
Khác /api/chat ở chỗ: user_message đến từ giọng nói, và client nhận thêm
event "transcript" ngay sau khi STT xong để xác nhận đúng ý.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.agent.orchestrator import run_agent
from app.api.recipient_context import RecipientContext
from app.core.stt import STTError, transcribe_file

router = APIRouter(prefix="/api", tags=["voice"])

# Giới hạn file audio (~1 phút PCM16 16kHz mono ≈ 2MB; WAV/thu nén nhỏ hơn)
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    customer_id: int = Form(default=2),  # demo: KH2
    quick_recipients: str = Form(default="[]"),
):
    try:
        recipients = RecipientContext.model_validate(
            {"quick_recipients": json.loads(quick_recipients)}
        ).quick_recipients
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="Danh sách chuyển tiền nhanh không hợp lệ.")
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="File audio rỗng")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="File audio quá lớn (>10MB)")

    try:
        transcript = await transcribe_file(data)
    except STTError as e:
        raise HTTPException(status_code=502, detail=f"Lỗi STT: {e}")

    async def event_gen():
        yield {
            "event": "transcript",
            "data": json.dumps({"type": "transcript", "text": transcript}, ensure_ascii=False),
        }
        async for event in run_agent(
            transcript, session_id, customer_id, [row.model_dump() for row in recipients]
        ):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }

    return EventSourceResponse(event_gen())
