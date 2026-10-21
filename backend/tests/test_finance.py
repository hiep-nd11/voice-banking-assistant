import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.tools.banking_catalog import FEATURES, TOOLS


class FinanceFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_all_upstream_tools_have_a_ui_feature(self):
        self.assertEqual({tool for _, tool in FEATURES.values()}, set(TOOLS))
        features = self.client.get("/api/banking/features").json()["features"]
        self.assertEqual(len(features), 21)
        self.assertFalse(
            next(row for row in features if row["id"] == "prepare-transfer")["read_only"]
        )

    def test_every_feature_dispatches_only_its_validated_arguments(self):
        samples = {
            "date_from": "2026-10-01",
            "date_to": "2026-10-21",
            "a_from": "2026-09-01",
            "a_to": "2026-09-30",
            "b_from": "2026-10-01",
            "b_to": "2026-10-21",
            "category": "electricity",
            "text": "500k",
            "amount": 100000,
            "name": "con",
            "action_id": "test-action",
        }
        for feature, (_, tool) in FEATURES.items():
            required = TOOLS[tool]["inputSchema"].get("required", [])
            args = {key: samples[key] for key in required}
            if feature in {"prepare-savings", "prepare-loan"}:
                args["amount"] = 10_000_000
            with (
                self.subTest(feature=feature),
                patch(
                    "app.api.banking.dispatch_tool", new=AsyncMock(return_value={"items": []})
                ) as dispatch,
            ):
                response = self.client.post(f"/api/banking/features/{feature}", json=args)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(dispatch.await_args.args[0], tool)
                self.assertTrue(args.items() <= dispatch.await_args.args[2].items())

    def test_invalid_inputs_never_reach_mcp(self):
        cases = [
            ("transactions", {}),
            ("recent", {"limit": 21}),
            ("recent", {"limit": "5"}),
            ("recent", {"direction": "invalid"}),
            ("month", {"month": "2026-13"}),
            ("income", {"date_from": "2026-10-22", "date_to": "2026-10-01"}),
            ("income", {"date_from": "2026-02-30", "date_to": "2026-10-01"}),
            ("prepare-transfer", {"amount": 999}),
            ("prepare-transfer", {"amount": 10000, "customer_id": 999}),
            ("cancel", {"action_id": ""}),
            ("trend", {"category": "electricity", "months": 19}),
            ("prepare-savings", {"amount": 999999}),
            ("prepare-loan", {"amount": 4999999}),
            ("budget", {"monthly_income": 0}),
        ]
        with patch("app.api.banking.dispatch_tool", new=AsyncMock()) as dispatch:
            for feature, args in cases:
                with self.subTest(feature=feature, args=args):
                    self.assertEqual(
                        self.client.post(f"/api/banking/features/{feature}", json=args).status_code,
                        422,
                    )
            self.assertEqual(
                self.client.post("/api/banking/features/delete_database", json={}).status_code, 404
            )
            dispatch.assert_not_awaited()

    def test_upstream_error_is_not_a_successful_result(self):
        with patch(
            "app.api.banking.dispatch_tool",
            new=AsyncMock(return_value={"error": "Không tìm thấy dữ liệu"}),
        ):
            self.assertEqual(
                self.client.post("/api/banking/features/profile", json={}).status_code, 502
            )
