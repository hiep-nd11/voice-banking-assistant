import copy
import json
import re
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus

from app.agent.memory import store
from app.agent.workflows import intent_for, normalized
from app.core.config import settings
from app.main import app

KHOA = {
    "beneficiary_id": 2,
    "name": "Trần Minh Khoa",
    "relationship": "con trai",
    "bank": "Vietcombank",
    "account_number": "****7890",
}
ANH = {
    "beneficiary_id": 3,
    "name": "Trần Ngọc Anh",
    "relationship": "con gái",
    "bank": "VietinBank",
    "account_number": "****0321",
}


class BankingWorkflowTests(unittest.TestCase):
    def setUp(self):
        AppStatus.should_exit_event = None
        self.client = self.enterContext(TestClient(app))
        self.enterContext(patch.object(settings, "tts_api_key", ""))
        self.mcp = self.enterContext(
            patch("app.agent.workflows.call_mcp", new=AsyncMock(side_effect=self.fake_tool))
        )
        self.llm = self.enterContext(
            patch(
                "app.agent.orchestrator._call_llm",
                new=AsyncMock(return_value=("Câu trả lời thông thường", [])),
            )
        )
        self.session = None
        self.flow = None
        self.preparations = 0
        self.cancellations = []
        self.risk = {"risk_level": "low", "reasons": [], "insufficient_balance": False}
        self.quick_recipients = [
            {
                "bank": "MB Bank",
                "account": "11111111",
                "recipient": "Người khác",
                "nickname": "Khác",
            },
            {
                "bank": KHOA["bank"],
                "account": "12347890",
                "recipient": KHOA["name"],
                "nickname": "Khoa",
            },
            {
                "bank": ANH["bank"],
                "account": "12340321",
                "recipient": ANH["name"],
                "nickname": "Ngọc Anh",
            },
        ]

    async def fake_tool(self, name, args):
        if name == "parse_vnd_amount":
            text = normalized(args["text"])
            if "mot trieu" in text:
                return {"ok": True, "amount": 1000000}
            match = re.search(r"(\d+)\s*(trieu|nghin|ngan|tr|k)?", text)
            if not match:
                return {"ok": False}
            return {
                "ok": True,
                "amount": int(match[1])
                * {"k": 1000, "nghin": 1000, "ngan": 1000, "tr": 1000000, "trieu": 1000000}.get(
                    match[2], 1
                ),
            }
        if name == "find_beneficiary":
            text = normalized(args["name"])
            matches = (
                [KHOA]
                if "khoa" in text or text == "con trai"
                else [ANH]
                if "ngoc anh" in text
                else [KHOA, ANH]
                if text == "con"
                else []
            )
            return {"matches": matches, "count": len(matches)}
        if name == "list_beneficiaries":
            return {"items": [KHOA, ANH]}
        if name == "check_transfer_risk":
            return copy.deepcopy(self.risk)
        if name.startswith("open_"):
            self.preparations += 1
            return {
                "executed": False,
                "ui_action": {
                    "action_id": f"act-{self.preparations}",
                    "type": "navigate",
                    "prefill": args,
                },
            }
        if name == "cancel_pending_action":
            self.cancellations.append(args["action_id"])
            return {"ui_action": {"type": "close", "action_id": args["action_id"]}}
        return {"speech": "Dữ liệu từ ngân hàng", "accounts": []}

    def chat(self, message):
        response = self.client.post(
            "/api/chat",
            json={
                "message": message,
                "session_id": self.session,
                "quick_recipients": self.quick_recipients,
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        self.assertFalse(any(row["type"] == "error" for row in rows), rows)
        self.session = rows[-1]["session_id"]
        for row in rows:
            if row["type"] == "flow_state":
                self.flow = row["flow"]
        return rows

    def request(self, event, payload=None, request_id=None):
        return {
            "flow_id": self.flow["id"],
            "version": self.flow["version"],
            "request_id": request_id or f"request-{self.flow['version']}-{event}",
            "event": event,
            "payload": payload or {},
        }

    def send(self, event, payload=None):
        response = self.client.post(
            f"/api/workflows/{self.session}/events", json=self.request(event, payload)
        )
        self.assertEqual(response.status_code, 200, response.text)
        for row in response.json()["events"]:
            if row["type"] == "flow_state":
                self.flow = row["flow"]
        return response.json()["events"]

    def test_qr_waits_for_scan_then_amount_and_review(self):
        rows = self.chat("Chuyển tiền bằng QR")
        self.assertEqual(rows[0]["type"], "session")
        self.assertEqual(self.flow["step"], "awaiting_qr")
        self.assertTrue(any(row.get("screen") == "qr" for row in rows))
        self.send(
            "qr_scanned",
            {"bank": "MB Bank", "account": "123456789", "recipient": "", "memo": "Thanh toán"},
        )
        self.assertEqual(self.flow["step"], "awaiting_amount")
        self.chat("500 nghìn")
        self.assertEqual(self.flow["slots"]["amount"], 500000)
        self.assertEqual(self.flow["step"], "review")
        response = self.client.post(
            f"/api/workflows/{self.session}/events", json=self.request("prepare")
        )
        self.assertEqual(response.status_code, 422)
        self.send(
            "form_updated", {"amount": 500000, "note": "Thanh toán", "recipient": "NGUYEN VAN A"}
        )
        self.send("prepare")
        self.assertEqual(self.flow["step"], "prepared")
        self.assertEqual(
            self.preparations, 0, "QR must not call a beneficiary-only upstream action"
        )

    def test_recipient_prefill_and_followup_amount(self):
        self.chat("Chuyển tiền cho anh Khoa")
        self.assertEqual(self.flow["slots"]["beneficiary"]["beneficiary_id"], 2)
        self.assertEqual(self.flow["step"], "awaiting_amount")
        self.chat("500k")
        self.assertEqual(self.flow["step"], "review")
        self.chat("đổi thành một triệu")
        self.assertEqual(self.flow["slots"]["amount"], 1000000)
        self.assertEqual(self.flow["slots"]["beneficiary"]["beneficiary_id"], 2)

    def test_middle_name_does_not_select_someone_else(self):
        rows = self.chat("chuyển tiền cho Minh 5tr")
        self.assertEqual(self.flow["intent"], "transfer_account")
        self.assertEqual(self.flow["step"], "awaiting_account")
        self.assertEqual(self.flow["slots"]["amount"], 5000000)
        self.assertNotIn("beneficiary", self.flow["slots"])
        self.assertNotIn("destination", self.flow["slots"])
        reply = "".join(row.get("content", "") for row in rows)
        self.assertIn("Không có ai tên Minh", reply)
        self.assertNotIn("Trần Minh Khoa", reply)
        self.assertTrue(any(row.get("screen") == "transfer" for row in rows))
        self.assertTrue(
            any(call.args[0] == "find_beneficiary" for call in self.mcp.await_args_list)
        )

    def test_exact_nickname_matches_only_the_current_quick_transfer_list(self):
        self.quick_recipients = [
            {
                "bank": "MB Bank",
                "account": "99999999",
                "recipient": "Lê Hoàng Minh",
                "nickname": "Minh",
            }
        ]
        self.chat("chuyển tiền cho minh 5tr")
        self.assertEqual(self.flow["slots"]["beneficiary"]["name"], "Lê Hoàng Minh")
        self.assertEqual(self.flow["slots"]["beneficiary"]["account_number"], "99999999")
        self.assertEqual(self.flow["slots"]["amount"], 5000000)
        self.quick_recipients = []
        self.chat("chuyển tiền cho Minh 5tr")
        self.assertEqual(self.flow["intent"], "transfer_account")
        self.assertNotIn("beneficiary", self.flow["slots"])

    def test_full_name_matches_locally_and_partial_name_resolves_via_mcp(self):
        self.chat("chuyển tiền cho Tran Minh Khoa 5tr")
        self.assertEqual(self.flow["slots"]["beneficiary"]["name"], KHOA["name"])
        self.chat("chuyển tiền cho Minh Khoa 5tr")
        self.assertEqual(self.flow["slots"]["beneficiary"]["name"], KHOA["name"])
        self.assertFalse(self.flow["demo_transfer"])

    def test_customer_son_resolves_without_browser_saved_recipients(self):
        self.quick_recipients = []
        self.chat("chuyển tiền cho con trai 5tr")
        self.assertEqual(self.flow["slots"]["beneficiary"], KHOA)
        self.assertEqual(self.flow["step"], "review")
        self.assertFalse(self.flow["demo_transfer"])
        self.assertTrue(any(
            call.args == ("find_beneficiary", {"name": "con trai"})
            for call in self.mcp.await_args_list
        ))
        self.send("prepare", {})
        self.assertEqual(self.flow["step"], "prepared")

    def test_customer_relationship_with_multiple_matches_requires_selection(self):
        self.quick_recipients = []
        self.chat("chuyển tiền cho con 5tr")
        self.assertEqual(self.flow["step"], "awaiting_recipient")
        self.assertEqual(len(self.flow["candidates"]), 2)
        self.assertNotIn("beneficiary", self.flow["slots"])
        self.send("recipient_selected", {"beneficiary_id": ANH["beneficiary_id"]})
        self.assertEqual(self.flow["slots"]["beneficiary"], ANH)

    def test_voice_uses_the_same_quick_transfer_context_and_missing_name_fallback(self):
        with patch(
            "app.api.voice.transcribe_file", new=AsyncMock(return_value="chuyển tiền cho Minh 5tr")
        ):
            response = self.client.post(
                "/api/voice",
                files={"audio": ("recording.wav", b"audio", "audio/wav")},
                data={"quick_recipients": json.dumps(self.quick_recipients)},
            )
        self.assertEqual(response.status_code, 200)
        rows = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        flow = next(row["flow"] for row in rows if row["type"] == "flow_state")
        self.assertEqual(flow["intent"], "transfer_account")
        self.assertEqual(flow["slots"]["amount"], 5000000)
        self.assertNotIn("beneficiary", flow["slots"])
        self.assertIn("Không có ai tên Minh", response.text)

    def test_ambiguous_recipient_must_be_selected_from_candidates(self):
        self.quick_recipients[1]["nickname"] = "con"
        self.quick_recipients[2]["nickname"] = "con"
        self.chat("Chuyển tiền cho con 500k")
        self.assertEqual(self.flow["step"], "awaiting_recipient")
        self.assertEqual(len(self.flow["candidates"]), 2)
        bad = self.client.post(
            f"/api/workflows/{self.session}/events",
            json=self.request("recipient_selected", {"beneficiary_id": 999}),
        )
        self.assertEqual(bad.status_code, 422)
        self.send("recipient_selected", {"beneficiary_id": 3})
        self.assertEqual(self.flow["slots"]["beneficiary"]["name"], ANH["name"])
        self.assertEqual(self.flow["step"], "review")

    def test_prepare_is_explicit_and_idempotent_and_changes_cancel_pending_action(self):
        self.chat("Chuyển cho Khoa 500k")
        self.chat("đồng ý")
        self.assertEqual(self.preparations, 0)
        request = self.request("prepare", request_id="one-click")
        one = self.client.post(f"/api/workflows/{self.session}/events", json=request)
        two = self.client.post(f"/api/workflows/{self.session}/events", json=request)
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json(), two.json())
        self.assertEqual(self.preparations, 1)
        self.chat("đổi thành một triệu")
        self.assertEqual(self.cancellations, ["act-1"])
        self.assertEqual(self.flow["step"], "review")
        stale = self.client.post(f"/api/workflows/{self.session}/events", json=request)
        self.assertEqual(stale.status_code, 409)

    def test_high_risk_requires_screen_acknowledgement_and_fresh_balance(self):
        self.risk = {
            "risk_level": "high",
            "reasons": ["Người nhận lạ"],
            "insufficient_balance": False,
        }
        self.chat("Chuyển cho Khoa 500k")
        self.send("prepare")
        self.assertEqual(self.preparations, 0)
        self.send("prepare", {"risk_acknowledged": True})
        self.assertEqual(self.preparations, 1)
        self.chat("đổi thành một triệu")
        self.risk["insufficient_balance"] = True
        self.send("prepare", {"risk_acknowledged": True})
        self.assertEqual(self.preparations, 1)

    def test_voice_cancel_and_readonly_detour(self):
        self.chat("Chuyển cho Khoa 500k")
        original_id = self.flow["id"]
        rows = self.chat("Cho tôi xem số dư")
        self.assertEqual(self.flow["id"], original_id)
        self.assertTrue(any(row.get("screen") == "assets" for row in rows))
        self.chat("hủy đi")
        self.assertIsNone(self.flow)

    def test_savings_spoken_term_and_loan_minimum(self):
        self.chat("Gửi tiết kiệm 10 triệu")
        self.assertEqual(self.flow["step"], "awaiting_term")
        self.chat("sáu tháng")
        self.assertEqual(self.flow["slots"]["term_months"], 6)
        self.assertEqual(self.flow["step"], "review")
        self.send("prepare")
        self.assertEqual(self.preparations, 1)
        self.chat("Tôi muốn vay 1 triệu")
        self.assertEqual(self.flow["step"], "awaiting_amount")

    def test_term_is_removed_before_amount_parser_is_called(self):
        self.chat("Tôi muốn vay 10 triệu 12 tháng")
        self.assertEqual(self.flow["slots"]["amount"], 10000000)
        self.assertEqual(self.flow["slots"]["term_months"], 12)
        parsed = [
            call.args[1]["text"]
            for call in self.mcp.await_args_list
            if call.args[0] == "parse_vnd_amount"
        ]
        self.assertTrue(parsed)
        self.assertFalse(any("12 thang" in normalized(text) for text in parsed))

    def test_stale_version_and_expiration_cannot_mutate_flow(self):
        self.chat("Chuyển tiền bằng QR")
        old_request = self.request(
            "qr_scanned", {"bank": "MB Bank", "account": "123456789"}, request_id="stale-unseen"
        )
        self.send("resume")
        # Resume does not mutate values; a form update does advance the version.
        self.send("qr_scanned", {"bank": "MB Bank", "account": "123456789"})
        response = self.client.post(f"/api/workflows/{self.session}/events", json=old_request)
        self.assertEqual(response.status_code, 409)
        store.get(self.session).workflow["expires_at"] = time.time() - 1
        response = self.client.post(
            f"/api/workflows/{self.session}/events", json=self.request("prepare")
        )
        self.assertEqual(response.status_code, 410)
        self.assertIsNone(store.get(self.session).workflow)

    def test_invalid_qr_and_form_payload_leave_state_unchanged(self):
        self.chat("Chuyển tiền bằng QR")
        original = copy.deepcopy(self.flow)
        for event, payload in [
            ("qr_scanned", {"bank": "MB", "account": "javascript:alert(1)"}),
            ("form_updated", {"amount": -100}),
            ("form_updated", {"account": "99999999"}),
        ]:
            response = self.client.post(
                f"/api/workflows/{self.session}/events", json=self.request(event, payload)
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(store.get(self.session).workflow, original)

    def test_howto_and_negation_do_not_start_a_journey(self):
        for text in [
            "Cách chuyển tiền bằng QR thế nào?",
            "Không chuyển tiền",
            "Nếu tôi chuyển tiền cho Khoa thì sao?",
        ]:
            self.assertIsNone(intent_for(text))
        rows = self.chat("Cách chuyển tiền bằng QR thế nào?")
        self.assertFalse(any(row["type"] == "ui_action" for row in rows))
        self.llm.assert_awaited_once()

    def test_conflicting_qr_amount_requires_explicit_form_review(self):
        self.chat("Chuyển tiền bằng QR 500k")
        self.send(
            "qr_scanned",
            {"bank": "MB Bank", "account": "123456789", "recipient": "A", "amount": "200000"},
        )
        self.assertEqual(self.flow["step"], "editing")
        response = self.client.post(
            f"/api/workflows/{self.session}/events", json=self.request("prepare")
        )
        self.assertEqual(response.status_code, 422)
        self.send("form_updated", {"amount": 200000})
        self.assertEqual(self.flow["step"], "review")
        self.send("rescan")
        self.assertEqual(self.flow["step"], "awaiting_qr")
        self.assertNotIn("amount", self.flow["slots"])

    def test_model_can_request_a_whitelisted_workflow_without_fabricating_recipient(self):
        self.llm.return_value = (
            "",
            [
                {
                    "id": "tc",
                    "name": "start_banking_workflow",
                    "arguments": {
                        "intent": "transfer_recipient",
                        "recipient_name": "Người không tồn tại trong câu",
                    },
                }
            ],
        )
        self.chat("Mở giúp tôi biểu mẫu nhé")
        self.assertEqual(self.flow["step"], "awaiting_account")
        self.assertTrue(
            any(call.args[0] == "find_beneficiary" for call in self.mcp.await_args_list)
        )

    def test_model_cannot_override_an_explicit_howto_or_negation(self):
        self.llm.return_value = (
            "",
            [
                {
                    "id": "tc",
                    "name": "start_banking_workflow",
                    "arguments": {"intent": "transfer_qr"},
                }
            ],
        )
        rows = self.chat("Không chuyển tiền bằng QR")
        self.assertFalse(any(row["type"] == "ui_action" for row in rows))
        self.assertIsNone(self.flow)

    def test_explicit_account_is_not_a_beneficiary_or_part_of_the_amount(self):
        rows = self.chat("chuyển cho tài khoản 22212132 vietcombank 5 triệu")
        self.assertEqual(self.flow["intent"], "transfer_account")
        self.assertEqual(
            self.flow["slots"]["destination"], {"account": "22212132", "bank": "Vietcombank"}
        )
        self.assertEqual(self.flow["slots"]["amount"], 5000000)
        self.assertTrue(any(row.get("screen") == "transfer" for row in rows))
        self.assertFalse(
            any(call.args[0] == "find_beneficiary" for call in self.mcp.await_args_list)
        )
        self.chat("đổi thành 5000000")
        self.assertEqual(self.flow["slots"]["destination"]["account"], "22212132")
        self.assertEqual(self.flow["slots"]["amount"], 5000000)
        self.send(
            "form_updated",
            {
                "bank": "Vietcombank",
                "account": "22212132",
                "recipient": "NGUYEN VAN A",
                "amount": 5000000,
            },
        )
        self.send("prepare")
        self.assertEqual(self.flow["step"], "prepared")
        self.assertEqual(self.preparations, 0)

    def test_normal_transfer_asks_for_account_then_bank_without_forcing_contacts(self):
        self.chat("Chuyển tiền")
        self.assertEqual(self.flow["step"], "awaiting_account")
        self.chat("22212132")
        self.assertEqual(self.flow["step"], "awaiting_bank")
        self.assertNotIn("amount", self.flow["slots"])
        self.chat("Vietcombank")
        self.assertEqual(self.flow["step"], "awaiting_amount")
        self.chat("5000000")
        self.assertEqual(self.flow["slots"]["amount"], 5000000)
        self.assertEqual(self.flow["slots"]["destination"]["account"], "22212132")
        self.assertEqual(self.flow["step"], "review")

    def test_quick_transfer_navigates_to_the_existing_quick_screen(self):
        rows = self.chat("Chuyển tiền nhanh")
        self.assertIsNone(self.flow)
        self.assertTrue(any(row.get("screen") == "recipients" for row in rows))
