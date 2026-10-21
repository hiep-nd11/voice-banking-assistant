import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app


class BankingTests(unittest.TestCase):
    def test_reads_same_mcp_tools_as_chat(self):
        results = {
            "get_customer_profile": {"full_name": "Khách hàng MCP"},
            "get_account_balances": {
                "accounts": [{"type": "payment", "balance": 123}],
                "as_of": "2026-10-21",
            },
            "get_recent_transactions": {"items": [{"direction": "in", "amount": 100}]},
        }
        with patch(
            "app.api.banking.call_mcp", new=AsyncMock(side_effect=lambda name, *args: results[name])
        ) as call:
            response = TestClient(app).get("/api/banking/overview")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["full_name"], "Khách hàng MCP")
        self.assertEqual(response.json()["transactions"][0]["direction"], "in")
        self.assertEqual(call.await_count, 3)

    def test_upstream_errors_do_not_return_demo_data(self):
        for result in [{"error": "unavailable"}, {}, []]:
            with (
                self.subTest(result=result),
                patch("app.api.banking.call_mcp", new=AsyncMock(return_value=result)),
            ):
                self.assertEqual(TestClient(app).get("/api/banking/overview").status_code, 502)
        with patch(
            "app.api.banking.call_mcp", new=AsyncMock(side_effect=httpx.ConnectError("offline"))
        ):
            self.assertEqual(TestClient(app).get("/api/banking/overview").status_code, 502)
