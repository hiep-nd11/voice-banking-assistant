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
