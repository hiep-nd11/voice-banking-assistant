FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# AgentBase Runtime yêu cầu: nghe cổng 8080 và có GET /health trả 200.
# (docker-compose.yml ghi đè CMD này để chạy local ở cổng 8000.)
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
