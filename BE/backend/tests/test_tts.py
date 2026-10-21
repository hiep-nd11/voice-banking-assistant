import base64
import io
import unittest
import wave
from unittest.mock import AsyncMock, patch

from app.core import tts


class BrowserAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_pcm_is_wrapped_as_browser_playable_wav(self):
        pcm = b"\x01\x00" * 100
        with (
            patch.object(tts, "_working_impl", None),
            patch.object(
                tts,
                "_tts_generate_content",
                new=AsyncMock(
                    return_value=(base64.b64encode(pcm).decode(), "audio/L16;codec=pcm;rate=24000")
                ),
            ),
        ):
            audio, mime = await tts.synthesize("Xin chào")
        self.assertEqual(mime, "audio/wav")
        with wave.open(io.BytesIO(base64.b64decode(audio))) as wav:
            self.assertEqual(wav.getframerate(), 24000)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.readframes(100), pcm)


class TTSRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_endpoints_send_api_key(self):
        import httpx

        requests = []

        def respond(request):
            requests.append(request)
            if request.url.path.endswith(":generateContent"):
                return httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"inlineData": {"data": "AQAA", "mimeType": "audio/wav"}}
                                    ]
                                }
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "audio", "data": "AQAA", "mimeType": "audio/wav"}],
                        }
                    ]
                },
            )

        with (
            patch.object(tts.settings, "tts_api_key", "test-key"),
            patch.object(tts.settings, "tts_base_url", "https://tts.example"),
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                await tts._tts_generate_content(client, "Xin chào")
                await tts._tts_interactions(client, "Xin chào")
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(request.headers["x-goog-api-key"], "test-key")

    async def test_cached_endpoint_failure_tries_other_endpoint(self):
        fallback = AsyncMock(return_value=("AQAA", "audio/wav"))
        with (
            patch.object(tts, "_working_impl", "generateContent"),
            patch.object(tts, "_tts_generate_content", AsyncMock(side_effect=tts.TTSError("503"))),
            patch.object(tts, "_tts_interactions", fallback),
        ):
            self.assertEqual(await tts.synthesize("Xin chào"), ("AQAA", "audio/wav"))
            self.assertEqual(tts._working_impl, "interactions")
        fallback.assert_awaited_once()

    async def test_all_failures_clear_cache_and_report_both_errors(self):
        with (
            patch.object(tts, "_working_impl", "interactions"),
            patch.object(tts, "_tts_generate_content", AsyncMock(side_effect=tts.TTSError("401"))),
            patch.object(tts, "_tts_interactions", AsyncMock(side_effect=tts.TTSError("503"))),
        ):
            with self.assertRaises(tts.TTSError) as raised:
                await tts.synthesize("Xin chào")
            self.assertIsNone(tts._working_impl)
            self.assertIn("401", str(raised.exception))
            self.assertIn("503", str(raised.exception))
