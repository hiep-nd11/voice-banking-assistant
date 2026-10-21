import os
from dotenv import load_dotenv

load_dotenv()

# Zipformer
ENCODER_MODEL_PATH = os.environ.get("ENCODER_MODEL_PATH", "models/stt/encoder.onnx")
DECODER_MODEL_PATH = os.environ.get("DECODER_MODEL_PATH", "models/stt/decoder.onnx")
JOINER_MODEL_PATH = os.environ.get("JOINER_MODEL_PATH", "models/stt/joiner.onnx")
TOKENS_PATH = os.environ.get("TOKENS_PATH", "models/stt/tokens.txt")

# "cpu" hoặc "cuda". Runtime AgentBase mặc định chỉ có CPU.
STT_DEVICE = os.environ.get("STT_DEVICE", "cpu")
STT_NUM_THREADS = int(os.environ.get("STT_NUM_THREADS", 2))
