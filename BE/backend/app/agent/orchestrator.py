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

import json
from typing import AsyncGenerator

from app.agent.llm_client import chat_completion_stream
from app.agent.memory import store
from app.agent.prompts import build_system_prompt
from app.agent.workflows import WorkflowError, is_non_action, normalized, process_message, start
from app.core.config import settings
from app.core.tts import TTSError, synthesize

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
    quick_recipients: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """ReAct loop chính. Yield các event dict cho SSE layer."""
    session = store.get_or_create(session_id, customer_id)
    # Persist session identity before navigation or slow TTS can interrupt a stream.
    yield {"type": "session", "session_id": session.session_id}
    try:
        async with session.workflow_lock:
            if quick_recipients is not None:
                session.quick_recipients = quick_recipients
            workflow_events = await process_message(session, user_message)
    except Exception as e:
        # The UI must receive its current state even if an upstream lookup fails.
        if session.workflow:
            session.workflow["version"] += 1
            if session.workflow["step"] == "starting":
                session.workflow["step"] = "editing"
        workflow_events = [
            {"type": "flow_state", "session_id": session.session_id, "flow": session.workflow},
            {
                "type": "token",
                "content": str(e)
                if isinstance(e, WorkflowError)
                else "Không truy vấn được dữ liệu ngân hàng. Anh thử lại giúp em.",
            },
        ]
    if workflow_events is not None:
        store.append(session.session_id, {"role": "user", "content": user_message})
        reply = "".join(row["content"] for row in workflow_events if row["type"] == "token")
        if reply:
            store.append(session.session_id, {"role": "assistant", "content": reply})
        for row in workflow_events:
            yield row
        if reply and settings.tts_enabled:
            try:
                audio_b64, mime = await synthesize(reply)
                yield {"type": "audio", "format": mime, "data": audio_b64}
            except TTSError as e:
                yield {"type": "tts_error", "message": str(e)}
        yield {"type": "done", "session_id": session.session_id}
        return

    # 1) build messages
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(settings.max_agent_steps)}
    ]
    messages.extend(store.history(session.session_id))
    messages.append({"role": "user", "content": user_message})

    # lưu user msg vào session
    store.append(session.session_id, {"role": "user", "content": user_message})

    final_content = ""
    try:
        for _step in range(settings.max_agent_steps):
            content, tool_calls = await _call_llm(messages)
            workflow_call = next(
                (tc for tc in tool_calls if tc["name"] == "start_banking_workflow"), None
            )
            if workflow_call and is_non_action(user_message):
                workflow_call = None
                tool_calls = [tc for tc in tool_calls if tc["name"] != "start_banking_workflow"]
                content = (
                    content
                    or "Anh có thể mở mục Chuyển tiền và chọn quét QR hoặc người nhận. Khi anh muốn bắt đầu một yêu cầu, hãy nói rõ để em hỗ trợ."
                )
            if workflow_call:
                args = workflow_call["arguments"]
                name = args.get("recipient_name")
                if name and (
                    not isinstance(name, str) or normalized(name) not in normalized(user_message)
                ):
                    name = None
                async with session.workflow_lock:
                    rows = await start(session, args.get("intent"), user_message, name)
                reply = "".join(row["content"] for row in rows if row["type"] == "token")
                for row in rows:
                    yield row
                store.append(session.session_id, {"role": "assistant", "content": reply})
                if reply and settings.tts_enabled:
                    try:
                        audio_b64, mime = await synthesize(reply)
                        yield {"type": "audio", "format": mime, "data": audio_b64}
                    except TTSError as e:
                        yield {"type": "tts_error", "message": str(e)}
                yield {"type": "done", "session_id": session.session_id}
                return

            # không có tool call -> trả lời cuối
            if not tool_calls:
                final_content = content
                # stream lại từng đoạn (đã gom; demo đủ mượt với chunk ~câu)
                for i in range(0, len(content), 40):
                    yield {"type": "token", "content": content[i : i + 40]}
                break

            # assistant msg chứa tool_calls (đưa lại vào history cho LLM)
            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            if content:
                yield {"type": "token", "content": content}

            # thực thi từng tool call
            for tc in tool_calls:
                yield {"type": "tool_call", "name": tc["name"], "args": tc["arguments"]}
                result = await dispatch_tool(tc["name"], customer_id, tc["arguments"])
                yield {"type": "tool_result", "name": tc["name"], "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["name"],
                        "content": _clip(json.dumps(result, ensure_ascii=False, default=str)),
                    }
                )
        else:
            # vượt max_steps mà vẫn đòi tool -> buộc trả lời không tool
            messages.append(
                {
                    "role": "user",
                    "content": "(Hệ thống: đã đạt giới hạn số bước. Hãy trả lời bằng thông tin đã có, không gọi tool thêm.)",
                }
            )
            content, _ = await _call_llm(messages)
            final_content = content
            for i in range(0, len(content), 40):
                yield {"type": "token", "content": content[i : i + 40]}

        # lưu assistant msg
        if final_content:
            store.append(session.session_id, {"role": "assistant", "content": final_content})

            # TTS câu trả lời cuối (bỏ qua lỗi để text vẫn về được client)
            if settings.tts_enabled:
                try:
                    audio_b64, mime = await synthesize(final_content)
                    yield {"type": "audio", "format": mime, "data": audio_b64}
                except TTSError as e:
                    yield {"type": "tts_error", "message": str(e)}

        yield {"type": "done", "session_id": session.session_id}

    except Exception as e:
        if session.workflow:
            session.workflow["version"] += 1
            if session.workflow["step"] == "starting":
                session.workflow["step"] = "editing"
            yield {"type": "flow_state", "session_id": session.session_id, "flow": session.workflow}
        yield {
            "type": "error",
            "message": f"{type(e).__name__}: {e}",
            "session_id": session.session_id,
        }
