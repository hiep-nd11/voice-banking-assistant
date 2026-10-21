"""Deterministic banking journeys. No journey executes a money transaction."""

from __future__ import annotations

import copy
import re
import time
import unicodedata
import uuid

from app.agent.workflow_config import CONFIG
from app.agent.workflow_config import message as workflow_message
from app.tools.mcp_client import call_mcp

TTL = CONFIG.ttl_seconds
TRANSACTIONS = {key for key, value in CONFIG.scenarios.items() if value.kind == "flow"}
INTENTS = set(CONFIG.scenarios)
BANKS = CONFIG.banks


def bank_from(text):
    norm = normalized(text)
    return next(
        (
            bank
            for bank, aliases in BANKS.items()
            if any(re.search(r"\b" + re.escape(alias) + r"\b", norm) for alias in aliases)
        ),
        None,
    )


def account_match(text, known_bank=None):
    norm = normalized(text)
    labeled = re.search(r"\b(?:tai khoan|stk|so tk|tk)\s*[:#-]?\s*(\d{6,20})\b", norm)
    if labeled:
        return labeled.span(1)
    direct = re.search(r"\b(?:cho|den)\s+(\d{6,20})\b", norm)
    if direct and not re.match(r"\s*(dong|vnd|trieu|nghin|ngan|ty|tr|k)\b", norm[direct.end() :]):
        return direct.span(1)
    if known_bank or bank_from(text):
        for match in re.finditer(r"\b\d{6,20}\b", norm):
            if not re.match(r"\s*(dong|vnd|trieu|nghin|ngan|ty|tr|k)\b", norm[match.end() :]):
                return match.span()
    return None


def destination_from(text, known_bank=None):
    span = account_match(text, known_bank)
    result = {}
    if span:
        result["account"] = normalized(text)[span[0] : span[1]]
    bank = bank_from(text)
    if bank:
        result["bank"] = bank
    return result


class WorkflowError(ValueError):
    pass


def normalized(text):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
        if unicodedata.category(c) != "Mn"
    ).strip()


def is_non_action(text):
    return bool(re.search(CONFIG.non_action_pattern, normalized(text)))


def matches_condition(condition, text):
    if condition.pattern is not None:
        return bool(re.search(condition.pattern, text))
    if condition.predicate == "has_destination":
        return bool(destination_from(text))
    if condition.predicate == "has_recipient":
        return bool(recipient_from(text))
    if condition.all is not None:
        return all(matches_condition(child, text) for child in condition.all)
    return any(matches_condition(child, text) for child in condition.any)


def intent_for(text):
    if is_non_action(text):
        return None
    text = normalized(text)
    return next((rule.intent for rule in CONFIG.rules if matches_condition(rule.when, text)), None)


def valid_terms(intent):
    scenario = CONFIG.scenarios[intent]
    return scenario.terms or range(1, scenario.max_term + 1)


async def tool(name, args=None):
    result = await call_mcp(name, args or {})
    if not isinstance(result, dict) or result.get("error"):
        raise WorkflowError(workflow_message("banking_unavailable"))
    return result


def state(session):
    return copy.deepcopy(session.workflow)


def events(session, text, screen=None, feature=None):
    if screen == "workflow" and session.workflow:
        scenario = CONFIG.scenarios[session.workflow["intent"]]
        screen = scenario.step_screens.get(session.workflow["step"], scenario.screen or screen)
    rows = [{"type": "flow_state", "session_id": session.session_id, "flow": state(session)}]
    if screen:
        rows.append(
            {
                "type": "ui_action",
                "action": "navigate",
                "screen": screen,
                "feature": feature,
                "session_id": session.session_id,
                "flow_id": session.workflow["id"] if session.workflow else None,
            }
        )
    if text:
        rows.append({"type": "token", "content": text})
    return rows


async def discard_pending(flow):
    if flow and flow.get("action_id"):
        await tool("cancel_pending_action", {"action_id": flow["action_id"]})
        flow.pop("action_id", None)
        flow.pop("prepared", None)
        flow["step"] = "editing"


async def amount_from(text, *, standalone=False):
    # The upstream amount parser otherwise reads "10 triệu 12 tháng" as
    # 10,120,000 VND. Remove non-money slots before asking it to parse money.
    span = account_match(text)
    if span:
        text = text[: span[0]] + text[span[1] :]
    norm = normalized(text)
    term_matches = list(
        re.finditer(r"\b(\d{1,3}|hai muoi bon|muoi hai|mot|ba|sau|chin)\s*thang\b", norm)
    )
    for match in reversed(term_matches):
        text = text[: match.start()] + text[match.end() :]
    note = re.search(r"\bnoi dung\b", normalized(text))
    if note:
        text = text[: note.start()]
    norm = normalized(text)
    if not (
        standalone
        or re.search(
            r"\d{4,}|\b(ty|trieu|nghin|ngan|dong|cu)\b|\d\s*(k|tr|trieu|nghin|ngan)\b", norm
        )
    ):
        return None
    result = await tool("parse_vnd_amount", {"text": text})
    amount = result.get("amount")
    if not result.get("ok") or not isinstance(amount, int) or isinstance(amount, bool):
        return None
    if amount < 1000 or amount > 9_007_199_254_740_991:
        raise WorkflowError(workflow_message("invalid_amount"))
    return amount


def term_from(text, standalone=False):
    norm = normalized(text)
    words = {"mot": 1, "ba": 3, "sau": 6, "chin": 9, "muoi hai": 12, "hai muoi bon": 24}
    match = re.search(r"\b(\d{1,3}|hai muoi bon|muoi hai|mot|ba|sau|chin)\s*thang\b", norm)
    value = match[1] if match else norm if standalone else None
    return int(value) if value and value.isdigit() else words.get(value)


def recipient_from(text):
    # Preserve accents and original case for the upstream beneficiary resolver.
    norm = normalized(text)
    match = re.search(r"\bcho\s+", norm)
    if not match:
        return None
    # NFD normalization removes accents without changing string length for Vietnamese.
    name = text[match.end() :].strip(" .,!?")
    stop = re.search(
        r"\s+(?:(?:so tien|voi|noi dung|de)\b|\d|(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|vai)\s+(?:tram|trieu|nghin|ngan)\b)",
        normalized(name),
    )
    if stop:
        name = name[: stop.start()]
    return name.strip(" ,.!?") or None


def quick_candidates(session):
    return [
        {
            "beneficiary_id": i + 1,
            "name": row["recipient"],
            "nickname": row.get("nickname", ""),
            "bank": row["bank"],
            "account_number": row["account"],
            "relationship": workflow_message("quick_transfer_label"),
            "source": "quick",
        }
        for i, row in enumerate(session.quick_recipients)
    ]


def mcp_beneficiary_id(slots):
    """beneficiary_id hợp lệ để gửi sang MCP, hoặc None.

    Người nhận chuyển nhanh (danh sách của FE) có beneficiary_id là VỊ TRÍ trong danh sách đó,
    không phải id trong danh bạ MCP. Gửi sang MCP sẽ điền nhầm người khác (id 1 = vợ...).
    """
    beneficiary = slots.get("beneficiary")
    if not beneficiary or beneficiary.get("source") == "quick":
        return None
    return beneficiary["beneficiary_id"]


async def choose_recipient(session, flow, name):
    query = normalized(name).strip(" .,!?")
    # Match a complete saved name or nickname, never an interior name token.
    queries = {query, re.sub(r"^(anh|chi|ong|ba|ban)\s+", "", query)}
    matches = [
        row
        for row in quick_candidates(session)
        if any(
            normalized(row.get(key, "")).strip() in queries
            for key in ("name", "nickname")
            if row.get(key, "").strip()
        )
    ]
    # Browser-saved recipients are optional; resolve customer relationships via MCP.
    flow["demo_transfer"] = bool(matches)
    if not matches:
        result = await tool("find_beneficiary", {"name": name})
        matches = result.get("matches")
        if not isinstance(matches, list):
            raise WorkflowError(workflow_message("banking_unavailable"))
    flow["candidates"] = matches
    flow["slots"].pop("beneficiary", None)
    flow["recipient_query"] = name
    if len(matches) == 1:
        flow["slots"]["beneficiary"] = matches[0]


async def advance(session):
    flow = session.workflow
    slots = flow["slots"]
    flow["version"] += 1
    flow["expires_at"] = time.time() + TTL
    if flow["intent"] == "transfer_recipient" and not slots.get("beneficiary"):
        flow["step"] = "awaiting_recipient"
        candidates = flow.get("candidates", [])
        if not candidates:
            name = flow.get("recipient_query", workflow_message("unknown_recipient_label"))
            flow["intent"] = "transfer_account"
            flow["step"] = "awaiting_account"
            flow["slots"].pop("destination", None)
            return events(session, workflow_message("recipient_not_found", name=name), "transfer")
        text = workflow_message("choose_duplicate_recipient")
        return events(session, text, "workflow")
    for requirement in CONFIG.scenarios[flow["intent"]].requirements:
        value = slots
        for part in requirement.slot.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if not value:
            flow["step"] = requirement.step
            return events(session, workflow_message(requirement.message), requirement.screen)
        if requirement.slot == "amount" and value < CONFIG.scenarios[flow["intent"]].minimum:
            flow["step"] = "awaiting_amount"
            return events(
                session,
                workflow_message(
                    "minimum_amount", minimum=CONFIG.scenarios[flow["intent"]].minimum
                ),
                "workflow",
            )
    if slots.get("term_months") and slots["term_months"] not in valid_terms(flow["intent"]):
        flow["step"] = "awaiting_term"
        return events(session, workflow_message("unsupported_term"), "workflow")
    if flow["intent"].startswith("transfer") and not flow.get("demo_transfer"):
        risk_args = {"amount": slots["amount"], "note": slots.get("note", "")}
        if mcp_beneficiary_id(slots) is not None:
            risk_args["beneficiary_id"] = mcp_beneficiary_id(slots)
        flow["risk"] = await tool("check_transfer_risk", risk_args)
        if flow["risk"].get("insufficient_balance"):
            flow["step"] = "awaiting_amount"
            return events(session, workflow_message("insufficient_balance"), "workflow")
    if flow.get("needs_review"):
        flow["step"] = "editing"
        return events(session, workflow_message("qr_amount_conflict"), "workflow")
    flow["step"] = "review"
    amount_text = f"{slots['amount']:,}".replace(",", ".")
    recipient = (
        slots.get("beneficiary", {}).get("name")
        or slots.get("qr", {}).get("recipient")
        or slots.get("destination", {}).get("recipient")
    )
    detail = f" cho {recipient}" if recipient else ""
    if slots.get("term_months"):
        detail += workflow_message("term_detail", term_months=slots["term_months"])
    return events(
        session,
        workflow_message("review_summary", amount_text=amount_text, detail=detail),
        "workflow",
    )


async def start(session, intent, text, recipient_name=None):
    text = unicodedata.normalize("NFC", text).strip()
    destination = destination_from(text)
    if intent in {"transfer_account", "transfer_recipient"} and (
        destination or re.search(r"\b(tai khoan|stk)\b", normalized(text))
    ):
        intent = "transfer_account"
    if not isinstance(intent, str) or intent not in INTENTS:
        raise WorkflowError(workflow_message("unsupported_scenario"))
    if intent not in TRANSACTIONS:
        scenario = CONFIG.scenarios[intent]
        if scenario.clear_pending:
            await discard_pending(session.workflow)
            session.workflow = None
        screen, feature = scenario.screen, scenario.feature
        lookup = scenario.lookup
        data = await tool(lookup) if lookup else {}
        text = data.get("speech") or workflow_message(scenario.message or "navigation_opened")
        return events(session, text, screen, feature)
    flow = {
        "id": str(uuid.uuid4()),
        "intent": intent,
        "step": "starting",
        "version": 0,
        "slots": {},
        "candidates": [],
        "expires_at": time.time() + TTL,
    }
    if intent == "transfer_account":
        flow["slots"]["destination"] = destination
    note = re.search(r"\bnoi dung\s*(?:(?:la|thanh)\s*)?", normalized(text))
    if note and intent.startswith("transfer"):
        value = text[note.end() :].strip()
        if len(value) > 140:
            raise WorkflowError(workflow_message("note_too_long"))
        flow["slots"]["note"] = value
    amount = await amount_from(text)
    if amount:
        flow["slots"]["amount"] = amount
    term = term_from(text)
    if term and intent in {"open_savings", "open_loan"}:
        flow["slots"]["term_months"] = term
    if intent == "transfer_recipient":
        name = recipient_from(text) or recipient_name
        if name:
            await choose_recipient(session, flow, name)
    await discard_pending(session.workflow)
    session.workflow = flow
    return await advance(session)


async def process_message(session, message):
    message = unicodedata.normalize("NFC", message).strip()
    norm = normalized(message)
    flow = session.workflow
    if flow and flow["expires_at"] < time.time():
        await discard_pending(flow)
        session.workflow = None
        return events(session, workflow_message("expired"), "home")
    if flow and re.search(r"\b(huy|thoi khong|khong chuyen nua|dung chuyen|bo qua)\b", norm):
        await discard_pending(flow)
        session.workflow = None
        return events(session, workflow_message("cancelled"), "home")
    if flow and flow["intent"] == "transfer_qr" and re.search(r"\b(doi|quet lai)\b.*\bqr\b", norm):
        return await handle_event(session, "rescan", {})
    intent = intent_for(message)
    # Contextual corrections take priority over starting a new transfer.
    correction = bool(flow and re.search(r"\b(doi|sua|thay|noi dung|quay lai)\b", norm))
    if intent and not correction:
        return await start(session, intent, message)
    if not flow:
        return None
    if re.search(r"\b(cach|huong dan|tai sao|thoi tiet)\b", norm):
        return None
    if re.fullmatch(r"(dong y|xac nhan|ok|dung roi|tiep tuc|chuyen di)[.! ]*", norm):
        return events(session, workflow_message("confirm_on_screen"), "workflow")
    changed = False
    destination = destination_from(
        message,
        flow["slots"].get("destination", {}).get("bank")
        if flow["step"] == "awaiting_account"
        else None,
    )
    if (
        flow["intent"] == "transfer_account"
        and flow["step"] == "awaiting_account"
        and re.fullmatch(r"\d{6,20}", norm)
    ):
        destination["account"] = norm
    if flow["intent"] in {"transfer_account", "transfer_recipient"} and destination:
        await discard_pending(flow)
        flow["intent"] = "transfer_account"
        flow["slots"].pop("beneficiary", None)
        flow["candidates"] = []
        flow["slots"].setdefault("destination", {}).update(destination)
        changed = True
    if "quay lai" in norm:
        await discard_pending(flow)
        flow["step"] = "editing"
        flow["version"] += 1
        return events(session, workflow_message("editing"), "workflow")
    if "noi dung" in norm:
        match = re.search(r"noi dung\s*(?:(?:la|thanh)\s*)?", norm)
        await discard_pending(flow)
        flow["slots"]["note"] = message[match.end() :].strip()[:140]
        changed = True
    recipient_change = re.search(
        r"(?:doi|thay) nguoi nhan\s+(?:(?:thanh|sang|la)\s+)?|(?:doi|thay) sang\s+", norm
    )
    if flow["intent"] == "transfer_recipient" and (
        flow["step"] == "awaiting_recipient" or correction and ("cho " in norm or recipient_change)
    ):
        name = recipient_from(message) or (
            message[recipient_change.end() :].strip() if recipient_change else message.strip()
        )
        await discard_pending(flow)
        await choose_recipient(session, flow, name)
        changed = True
    term = term_from(message, standalone=flow["step"] == "awaiting_term")
    if term and flow["intent"] in {"open_savings", "open_loan"}:
        await discard_pending(flow)
        flow["slots"]["term_months"] = term
        changed = True
    amount = (
        None
        if "noi dung" in norm
        or term
        and flow["step"] == "awaiting_term"
        or destination.get("account")
        and not re.search(r"\b(trieu|nghin|ngan|dong|ty)\b|\d\s*(k|tr)\b", norm)
        else await amount_from(message, standalone=flow["step"] == "awaiting_amount" and not term)
    )
    if amount:
        await discard_pending(flow)
        flow["slots"]["amount"] = amount
        changed = True
    if changed:
        return await advance(session)
    if flow["intent"] == "transfer_qr" and flow["step"] == "awaiting_qr":
        return events(session, workflow_message("resume_qr"), "qr")
    return None


async def handle_event(session, event, payload):
    flow = session.workflow
    slots = flow["slots"]
    if event == "cancel":
        await discard_pending(flow)
        session.workflow = None
        return events(session, workflow_message("event_cancelled"), "home")
    if event == "resume":
        return events(
            session,
            workflow_message("resumed"),
            "qr" if flow["step"] == "awaiting_qr" else "workflow",
        )
    if event == "rescan":
        if flow["intent"] != "transfer_qr":
            raise WorkflowError(workflow_message("not_qr_flow"))
        await discard_pending(flow)
        for key in ["qr", "amount", "note"]:
            slots.pop(key, None)
        flow.pop("needs_review", None)
        return await advance(session)
    if event in {"recipient_search", "change_recipient"}:
        if flow["intent"] != "transfer_recipient":
            raise WorkflowError(workflow_message("not_recipient_flow"))
        slots.pop("beneficiary", None)
        if event == "recipient_search":
            name = payload.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 150:
                raise WorkflowError(workflow_message("invalid_recipient_query"))
            await choose_recipient(session, flow, name)
        else:
            flow["candidates"] = quick_candidates(session)
            flow["demo_transfer"] = True
        await discard_pending(flow)
    elif event == "recipient_selected":
        if flow["intent"] != "transfer_recipient":
            raise WorkflowError(workflow_message("cannot_select_recipient"))
        choice = next(
            (
                row
                for row in flow["candidates"]
                if row["beneficiary_id"] == payload.get("beneficiary_id")
            ),
            None,
        )
        if not choice:
            raise WorkflowError(workflow_message("invalid_recipient_choice"))
        await discard_pending(flow)
        slots["beneficiary"] = choice
    elif event == "qr_scanned":
        if flow["intent"] != "transfer_qr":
            raise WorkflowError(workflow_message("invalid_qr"))
        qr = {key: str(payload.get(key, "")).strip() for key in ["bank", "account", "recipient"]}
        if (
            not re.fullmatch(r"\d{6,20}", qr["account"])
            or not qr["bank"]
            or len(qr["bank"]) > 100
            or len(qr["recipient"]) > 150
        ):
            raise WorkflowError(workflow_message("invalid_qr_information"))
        slots["qr"] = qr
        # A newly scanned QR may include an amount; the review form always
        # displays it, and never silently advances to execution.
        if payload.get("amount") not in (None, ""):
            amount = str(payload["amount"])
            if not re.fullmatch(r"\d+", amount) or not 1000 <= int(amount) <= 9_007_199_254_740_991:
                raise WorkflowError(workflow_message("invalid_qr_amount"))
            if slots.get("amount") and slots["amount"] != int(amount):
                flow["needs_review"] = True
            slots["amount"] = int(amount)
        slots["note"] = slots.get("note") or str(payload.get("memo") or "")[:140]
        await discard_pending(flow)
    elif event == "form_updated":
        allowed = {"amount", "term_months", "note", "recipient", "bank", "account"}
        if set(payload) - allowed:
            raise WorkflowError(workflow_message("invalid_fields"))
        if "amount" in payload:
            amount = payload["amount"]
            if type(amount) is not int or not 1000 <= amount <= 9_007_199_254_740_991:
                raise WorkflowError(workflow_message("invalid_form_amount"))
            slots["amount"] = amount
            flow.pop("needs_review", None)
        if "term_months" in payload:
            term = payload["term_months"]
            if type(term) is not int or term not in valid_terms(flow["intent"]):
                raise WorkflowError(workflow_message("invalid_term"))
            slots["term_months"] = term
        if "note" in payload:
            if not isinstance(payload["note"], str) or len(payload["note"]) > 140:
                raise WorkflowError(workflow_message("invalid_note"))
            slots["note"] = payload["note"]
        if "recipient" in payload:
            target = slots.get("qr") or slots.get("destination")
            if (
                target is None
                or not isinstance(payload["recipient"], str)
                or len(payload["recipient"]) > 150
            ):
                raise WorkflowError(workflow_message("invalid_recipient"))
            target["recipient"] = payload["recipient"].strip()
        if "bank" in payload or "account" in payload:
            target = slots.get("qr") or slots.get("destination")
            if target is None:
                raise WorkflowError(workflow_message("recipient_account_locked"))
            if "bank" in payload:
                if payload["bank"] not in BANKS:
                    raise WorkflowError(workflow_message("invalid_bank"))
                target["bank"] = payload["bank"]
            if "account" in payload:
                if not isinstance(payload["account"], str) or not re.fullmatch(
                    r"\d{6,20}", payload["account"]
                ):
                    raise WorkflowError(workflow_message("invalid_account"))
                target["account"] = payload["account"]
        await discard_pending(flow)
    elif event == "prepare":
        if flow["step"] != "review":
            raise WorkflowError(workflow_message("review_required"))
        beneficiary_id = mcp_beneficiary_id(slots)
        if flow["intent"].startswith("transfer"):
            risk_args = {"amount": slots["amount"], "note": slots.get("note", "")}
            if beneficiary_id is not None:
                risk_args["beneficiary_id"] = beneficiary_id
            flow["risk"] = await tool("check_transfer_risk", risk_args)
            if (
                flow["risk"].get("insufficient_balance")
                or flow["risk"].get("risk_level") == "high"
                and payload.get("risk_acknowledged") is not True
            ):
                flow["version"] += 1
                return events(session, workflow_message("risk_updated"), "workflow")
        if flow["intent"] in {"transfer_qr", "transfer_account"}:
            target = slots.get("qr") or slots.get("destination", {})
            if not target.get("recipient"):
                raise WorkflowError(workflow_message("recipient_name_required"))
            flow["step"] = "prepared"
            flow["version"] += 1
            return events(session, workflow_message("account_prepared"), "workflow")
        name = {
            "transfer_recipient": "open_transfer_screen",
            "open_savings": "open_savings_screen",
            "open_loan": "open_loan_screen",
        }[flow["intent"]]
        args = {"amount": slots["amount"]}
        if slots.get("term_months"):
            args["term_months"] = slots["term_months"]
        if flow["intent"] == "transfer_recipient":
            args.update(
                note=slots.get("note", ""),
                risk_acknowledged=payload.get("risk_acknowledged") is True,
            )
            if beneficiary_id is not None:
                args["beneficiary_id"] = beneficiary_id
        result = await tool(name, args)
        action_id = result.get("ui_action", {}).get("action_id")
        if not action_id or result.get("executed") is not False:
            raise WorkflowError(workflow_message("invalid_preparation_result"))
        flow["action_id"] = action_id
        flow["prepared"] = result
        flow["step"] = "prepared"
        flow["version"] += 1
        return events(session, workflow_message("request_prepared"), "workflow")
    else:
        raise WorkflowError(workflow_message("unsupported_event"))
    return await advance(session)
