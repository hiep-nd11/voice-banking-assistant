import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.core.config import settings
from app.core.stt import STTError, transcribe_file


class SttTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_configuration(self):
        with patch.object(settings, "asr_base_url", ""):
            with self.assertRaisesRegex(STTError, "ASR_BASE_URL"):
                await transcribe_file(b"pcm")

    async def test_connection_error(self):
        with (
            patch.object(settings, "asr_base_url", "http://asr"),
            patch(
                "httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("offline"))
            ),
        ):
            with self.assertRaisesRegex(STTError, "Không kết nối"):
                await transcribe_file(b"pcm")

    async def test_response_contract_and_url(self):
        for response, expected in [
            (httpx.Response(200, text="not json"), "JSON"),
            (httpx.Response(200, json={"text": 42}), "thiếu text"),
            (httpx.Response(200, json={"text": " "}), "text rỗng"),
        ]:
            with (
                self.subTest(expected=expected),
                patch.object(settings, "asr_base_url", "http://asr/"),
                patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)) as post,
            ):
                with self.assertRaisesRegex(STTError, expected):
                    await transcribe_file(b"pcm")
                post.assert_awaited_once_with("http://asr/transcribe", content=b"pcm")
