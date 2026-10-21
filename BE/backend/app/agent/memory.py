"""Bộ nhớ hội thoại in-memory (hackathon).

Mỗi session: danh sách messages OpenAI-format + customer_id gắn sẵn.
Sau này thay bằng Postgres (chat_sessions/chat_messages) — interface giữ nguyên.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

MAX_HISTORY = 20  # số message giữ lại trong context (10 lượt)


@dataclass
class Session:
    session_id: str
    customer_id: int
    created_at: float = field(default_factory=time.time)
    messages: list[dict] = field(
        default_factory=list
    )  # {role, content, tool_calls?, tool_call_id?, name?}
    workflow: dict | None = None
    workflow_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    workflow_requests: dict = field(default_factory=dict)
    quick_recipients: list[dict] = field(default_factory=list)


class SessionStore:
    """In-memory session store for the single-process demo runtime."""

    def __init__(self, max_history: int = MAX_HISTORY):
        self._sessions: dict[str, Session] = {}
        self._max_history = max_history

    def create(self, customer_id: int) -> Session:
        sid = str(uuid.uuid4())
        s = Session(session_id=sid, customer_id=customer_id)
        self._sessions[sid] = s
        return s

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str | None, customer_id: int) -> Session:
        if (
            session_id
            and session_id in self._sessions
            and self._sessions[session_id].customer_id == customer_id
        ):
            return self._sessions[session_id]
        return self.create(customer_id)

    def append(self, session_id: str, message: dict) -> None:
        s = self._sessions.get(session_id)
        if s is None:
            return
        s.messages.append(message)
        # giữ history trong giới hạn: loại tool_calls/tool pairs trước
        if len(s.messages) > self._max_history * 4:  # thô: mỗi lượt có thể gồm nhiều message
            s.messages = s.messages[-self._max_history * 2 :]

    def history(self, session_id: str) -> list[dict]:
        s = self._sessions.get(session_id)
        return list(s.messages) if s else []


# singleton dùng chung
store = SessionStore()
