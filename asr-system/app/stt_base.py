import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import sherpa_onnx

from .config import (
    ENCODER_MODEL_PATH,
    DECODER_MODEL_PATH,
    JOINER_MODEL_PATH,
    TOKENS_PATH,
    STT_DEVICE,
    STT_NUM_THREADS,
)

class ASR_Engine(ABC):
    @abstractmethod
    def infer(self, audio: np.ndarray[np.float32]) -> str:
        pass


class Zipformer_ASR_Engine(ASR_Engine):
    def __init__(self, device=STT_DEVICE, num_threads=STT_NUM_THREADS):
        print(f"/> init Zipformer_ASR_Engine (device={device})", flush=True)
        self.model = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=ENCODER_MODEL_PATH,
            decoder=DECODER_MODEL_PATH,
            joiner=JOINER_MODEL_PATH,
            tokens=TOKENS_PATH,
            num_threads=num_threads,
            sample_rate=16000,
            feature_dim=80,
            provider=device,
            decoding_method="greedy_search",
            hotwords_file="",
            hotwords_score=1.5,
            modeling_unit="",
            bpe_vocab="",
            blank_penalty=0,
            debug=False,
        )
        self.sr = 16000
        
    def infer(self, audio: np.ndarray[np.float32]) -> str:
        s = self.model.create_stream()
        s.accept_waveform(16000, audio)
        self.model.decode_streams([s])
        return s.result.text


class STTEngine(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        """
        Args:
            audio: Audio mono float32, shape (num_samples,).
                   Biên độ chuẩn hóa về khoảng [-1, 1].
            sample_rate: Sample rate của audio.

        Returns:
            Văn bản nhận dạng.
        """
        raise NotImplementedError

class ZipformerSTTEngine(STTEngine):
    def __init__(self, device=STT_DEVICE):
        self.engine = Zipformer_ASR_Engine(device=device)

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        if sample_rate != 16000:
            raise ValueError("Zipformer chỉ hỗ trợ sample rate 16 kHz.")
        # Chạy decode trong thread để không chặn event loop
        # (các kết nối WebSocket khác vẫn nhận audio bình thường).
        return await asyncio.to_thread(self.engine.infer, audio)
