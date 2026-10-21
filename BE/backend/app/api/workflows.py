"""Versioned browser callbacks for the current conversation's banking journey."""

import copy
import json
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.agent.memory import store
from app.agent.workflows import WorkflowError, discard_pending, handle_event, state

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    flow_id: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=100)
    event: Literal[
        "qr_scanned",
        "rescan",
        "recipient_selected",
        "recipient_search",
        "change_recipient",
        "form_updated",
        "prepare",
        "cancel",
        "resume",
    ]
    payload: dict = Field(default_factory=dict)


@router.get("/{session_id}")
async def current_workflow(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(404, "Phiên hội thoại đã hết hạn")
    async with session.workflow_lock:
        if session.workflow and session.workflow["expires_at"] < time.time():
            await discard_pending(session.workflow)
            session.workflow = None
        return {"session_id": session_id, "flow": state(session)}


@router.post("/{session_id}/events")
async def browser_event(session_id: str, req: WorkflowEvent):
    session = store.get(session_id)
    if not session:
        raise HTTPException(404, "Phiên hội thoại đã hết hạn")
    async with session.workflow_lock:
        fingerprint = json.dumps(req.model_dump(), sort_keys=True, ensure_ascii=False)
        cache_key = f"{req.flow_id}:{req.request_id}"
        cached = session.workflow_requests.get(cache_key)
        if cached:
            if cached["fingerprint"] != fingerprint:
                raise HTTPException(409, "Mã yêu cầu đã được sử dụng với thông tin khác")
            cached_flow = next(
                (
                    row["flow"]
                    for row in cached["response"]["events"]
                    if row["type"] == "flow_state"
                ),
                None,
            )
            current = session.workflow
            if cached_flow and (
                not current
                or current["id"] != req.flow_id
                or current["version"] != cached_flow["version"]
            ):
                raise HTTPException(409, "Kịch bản đã thay đổi sau yêu cầu này")
            return cached["response"]
        flow = session.workflow
        if not flow or flow["id"] != req.flow_id:
            raise HTTPException(409, "Kịch bản đã thay đổi hoặc đã hủy")
        if flow["expires_at"] < time.time():
            await discard_pending(flow)
            session.workflow = None
            raise HTTPException(410, "Kịch bản đã hết hạn. Anh bắt đầu lại giúp em.")
        if flow["version"] != req.version:
            raise HTTPException(409, "Thông tin đã thay đổi. Hãy kiểm tra lại biểu mẫu mới nhất.")
        previous = copy.deepcopy(flow)
        try:
            rows = await handle_event(session, req.event, req.payload)
        except WorkflowError as e:
            session.workflow = previous
            raise HTTPException(422, str(e))
        except (httpx.HTTPError, ValueError, KeyError):
            session.workflow = previous
            raise HTTPException(502, "Không kết nối được dịch vụ ngân hàng. Vui lòng thử lại.")
        reply = "".join(row["content"] for row in rows if row["type"] == "token")
        store.append(
            session_id, {"role": "user", "content": f"[Thao tác trên màn hình: {req.event}]"}
        )
        if reply:
            store.append(session_id, {"role": "assistant", "content": reply})
        response = {"events": rows + [{"type": "done", "session_id": session_id}]}
        session.workflow_requests[cache_key] = {"fingerprint": fingerprint, "response": response}
        while len(session.workflow_requests) > 32:
            session.workflow_requests.pop(next(iter(session.workflow_requests)))
        return response
