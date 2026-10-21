FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY models/stt ./models/stt
COPY app ./app

ENV STT_DEVICE=cpu \
    ENCODER_MODEL_PATH=models/stt/encoder.onnx \
    DECODER_MODEL_PATH=models/stt/decoder.onnx \
    JOINER_MODEL_PATH=models/stt/joiner.onnx \
    TOKENS_PATH=models/stt/tokens.txt \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -fs http://127.0.0.1:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
