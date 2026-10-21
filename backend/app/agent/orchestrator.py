"""Agent Orchestrator -- ReAct loop + function calling (streaming).

Flow:
1. User message + session -> build messages (system + history).
2. Call LLM stream. If LLM returns tool_calls -> execute tool -> feed result back to LLM (loop, max_steps).
3. Stream tokens to SSE with tool-call trace for UI.

Stream events (JSON, one per line):
  {"type": "token", "content": "..."}
  {"type": "tool_call", "name": "...", "args": {...}}
  {"type": "tool_result", "name": "...", "result": {...}
  {"type": "audio", "format": "audio/wav", "data": "<base64>"}   # TTS câu trả lời cuối
  {"type": "tts_error", "message": "..."}                        # TTS lỗi, text vẫn trả bình thường
  {"type": "done", "session_id": "..."}
  {"type": "error", "message": "..."}
"""
from __future__ import annotations

import base64
import json
from typing import AsyncGenerator

from app.core.config import settings
from app.core.tts import TTSError, synthesize, to_wav_bytes
from app.agent.llm_client import chat_completion_stream
from app.agent.memory import store
from app.agent.prompts import build_system_prompt

# Gọi tool qua MCP server (voice-banking-assistant, cùng máy/URL theo settings.mcp_base_url)
from app.tools.mcp_client import dispatch_tool

from app.tools.registry import TOOL_SCHEMAS

MAX_TOOL_RESULT_CHARS = 4000


def _parse_sse_chunk(chunk_str: str) -> list[dict]:
    """Parse one SSE data chunk into a list of choice deltas."""
    if not chunk_str.strip() or chunk_str.strip() == "[DONE]":
        return []
    try:
        data = json.loads(chunk_str)
    except json.JSONDecodeError:
        return []
    return data.get("choices") or []


def _clip(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


async def _call_llm(messages: list[dict]) -> tuple[str, list[dict]]:
    """Gọi LLM stream, gom kết quả. Trả về (content, tool_calls).

    tool_calls: list của {"id", "name", "arguments"(dict)} — đã parse JSON args.
    """
    content_parts: list[str] = []
    tool_calls: dict[int, dict] = {}  # index -> {"id", "name", "args_str"}

    async for chunk_str in chat_completion_stream(messages, tools=TOOL_SCHEMAS):
        for choice in _parse_sse_chunk(chunk_str):
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(idx, {"id": "", "name": "", "args_str": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["args_str"] += fn["arguments"]

    parsed_calls = []
    for idx in sorted(tool_calls):
        slot = tool_calls[idx]
        try:
            args = json.loads(slot["args_str"]) if slot["args_str"].strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": slot["args_str"]}
        if slot["name"]:
            parsed_calls.append({"id": slot["id"], "name": slot["name"], "arguments": args})
    return "".join(content_parts), parsed_calls


async def run_agent(
    user_message: str,
    session_id: str | None,
    customer_id: int,
) -> AsyncGenerator[dict, None]:
    """ReAct loop chính. Yield các event dict cho SSE layer."""
    session = store.get_or_create(session_id, customer_id)

    # 1) build messages
    messages: list[dict] = [{"role": "system", "content": build_system_prompt(settings.max_agent_steps)}]
    messages.extend(store.history(session.session_id))
    messages.append({"role": "user", "content": user_message})

    # lưu user msg vào session
    store.append(session.session_id, {"role": "user", "content": user_message})

    final_content = ""
    try:
        for _step in range(settings.max_agent_steps):
            content, tool_calls = await _call_llm(messages)

            # không có tool call -> trả lời cuối
            if not tool_calls:
                final_content = content
                # stream lại từng đoạn (đã gom; demo đủ mượt với chunk ~câu)
                for i in range(0, len(content), 40):
                    yield {"type": "token", "content": content[i:i + 40]}
                break

            # assistant msg chứa tool_calls (đưa lại vào history cho LLM)
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
                    }
                    for tc in tool_calls
                ],
            })
            if content:
                yield {"type": "token", "content": content}

            # thực thi từng tool call
            for tc in tool_calls:
                yield {"type": "tool_call", "name": tc["name"], "args": tc["arguments"]}
                result = await dispatch_tool(tc["name"], customer_id, tc["arguments"])
                yield {"type": "tool_result", "name": tc["name"], "result": result}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": _clip(json.dumps(result, ensure_ascii=False, default=str)),
                })
        else:
            # vượt max_steps mà vẫn đòi tool -> buộc trả lời không tool
            messages.append({
                "role": "user",
                "content": "(Hệ thống: đã đạt giới hạn số bước. Hãy trả lời bằng thông tin đã có, không gọi tool thêm.)",
            })
            content, _ = await _call_llm(messages)
            final_content = content
            for i in range(0, len(content), 40):
                yield {"type": "token", "content": content[i:i + 40]}

        # lưu assistant msg
        if final_content:
            store.append(session.session_id, {"role": "assistant", "content": final_content})

            # TTS câu trả lời cuối (bỏ qua lỗi để text vẫn về được client)
            if settings.tts_enabled:
                try:
                    audio_b64, mime = await synthesize(final_content)
                    if "wav" not in mime.lower():
                        # Gemini trả raw PCM (audio/l16) — bọc header WAV để client phát được
                        audio_b64 = base64.b64encode(to_wav_bytes(audio_b64)).decode()
                        mime = "audio/wav"
                    yield {"type": "audio", "format": mime, "data": audio_b64}
                except TTSError as e:
                    yield {"type": "tts_error", "message": str(e)}

        yield {"type": "done", "session_id": session.session_id}

    except Exception as e:
        yield {"type": "error", "message": f"{type(e).__name__}: {e}", "session_id": session.session_id}
