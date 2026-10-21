# Voice Banking MCP server - chạy trên GreenNode AgentBase Runtime (hoặc vServer)
# Yêu cầu của AgentBase Runtime: lắng nghe cổng 8080 và có GET /health trả 200.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    APP_TIMEZONE=Asia/Ho_Chi_Minh

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY db/schema.sql db/seed.sql db/load_db.py ./db/

# File trong repo có thể mang quyền 600 (chỉ chủ sở hữu đọc) -> mở quyền đọc cho appuser, nếu không container
# chết ngay lúc import với "Permission denied".
RUN chmod -R a+rX /app && useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "app.server"]
