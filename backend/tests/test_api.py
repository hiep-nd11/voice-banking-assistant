"""Exercise the browser API contract without calling paid external services."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sse_starlette.sse import AppStatus

from app.core.stt import STTError
from app.main import app


class BrowserApiTests(unittest.TestCase):
    def setUp(self):
        # sse-starlette 2.x keeps its shutdown Event globally across test loops.
        AppStatus.should_exit_event = None
        self.client = self.enterContext(TestClient(app))

    def test_chat_stream_and_session_history(self):
        with (
            patch("app.agent.orchestrator._call_llm", new=AsyncMock(return_value=("Xin chào", []))),
            patch(
                "app.agent.orchestrator.synthesize",
                new=AsyncMock(return_value=("YQ==", "audio/wav")),
            ),
        ):
            response = self.client.post("/api/chat", json={"message": "Chào", "customer_id": 2})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        self.assertEqual("".join(e["content"] for e in events if e["type"] == "token"), "Xin chào")
        self.assertEqual(events[-1]["type"], "done")
        history = self.client.get(f"/api/sessions/{events[-1]['session_id']}/messages").json()[
            "messages"
        ]
        self.assertEqual([m["content"] for m in history], ["Chào", "Xin chào"])

    def test_voice_transcript_and_reply(self):
        with (
            patch("app.api.voice.transcribe_file", new=AsyncMock(return_value="Số dư")),
            patch(
                "app.agent.orchestrator._call_llm", new=AsyncMock(return_value=("Câu trả lời", []))
            ),
            patch(
                "app.agent.orchestrator.synthesize",
                new=AsyncMock(return_value=("YQ==", "audio/wav")),
            ),
        ):
            response = self.client.post(
                "/api/voice",
                files={"audio": ("recording.wav", b"wav", "audio/wav")},
                data={"customer_id": "2"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "transcript"', response.text)
        self.assertIn('"type": "done"', response.text)

    def test_voice_errors_are_json(self):
        response = self.client.post(
            "/api/voice", files={"audio": ("recording.wav", b"", "audio/wav")}
        )
        self.assertEqual(response.status_code, 400)
        with patch(
            "app.api.voice.transcribe_file", new=AsyncMock(side_effect=STTError("ASR unavailable"))
        ):
            response = self.client.post(
                "/api/voice", files={"audio": ("recording.wav", b"wav", "audio/wav")}
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("ASR unavailable", response.json()["detail"])

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
