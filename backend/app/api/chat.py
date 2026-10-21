"""POST /api/chat — SSE stream câu trả lời của agent.

Body: {"message": "...", "session_id": "...?", "customer_id": 2?}
Mặc định customer_id=2 (KH2 — chi tiêu vượt kiểm soát) cho demo.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.agent.memory import store
from app.agent.orchestrator import run_agent
from app.api.recipient_context import RecipientContext

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(RecipientContext):
    message: str
    session_id: str | None = None
    customer_id: int = 2  # demo: KH2


@router.post("/chat")
async def chat(req: ChatRequest):
    async def event_gen():
        async for event in run_agent(
            req.message,
            req.session_id,
            req.customer_id,
            [row.model_dump() for row in req.quick_recipients],
        ):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }

    return EventSourceResponse(event_gen())


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    msgs = store.history(session_id)
    return {"session_id": session_id, "messages": msgs}
