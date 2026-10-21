"""Cấu hình tập trung — đọc từ biến môi trường / file .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Đường dẫn cố định theo source; biến môi trường thật ưu tiên hơn các file.
    model_config = SettingsConfigDict(
        env_file=(BE_ROOT / ".env", BE_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (OpenAI-compatible). Đặt LLM_API_KEY / LLM_BASE_URL trong .env hoặc biến môi trường.
    # Nhánh LLM cần API key; các workflow xác định vẫn xử lý trước nhánh LLM.
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "glm-4.6"

    allow_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    # MCP server (voice-banking-assistant) — nguồn dữ liệu khách hàng thật (mock).
    # Đặt MCP_BASE_URL / MCP_API_KEY trong .env.
    # Chạy backend trong Docker (MCP chạy local): MCP_BASE_URL=http://host.docker.internal:8080/mcp
    mcp_base_url: str = ""
    mcp_api_key: str = ""

    # ASR Voice WebSocket API (VNG Cloud agentbase) — /transcribe cho file, /ws/voice cho stream
    asr_base_url: str = ""

    # TTS (Gemini). Rỗng API key -> không phát audio, chỉ trả text.
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_voice: str = "Aoede"  # giọng nữ, nhẹ nhàng — hợp trợ lý ngân hàng

    @property
    def tts_enabled(self) -> bool:
        return bool(self.tts_api_key)

    # Giới hạn ReAct loop
    max_agent_steps: int = 5
    agent_timeout_s: int = 60

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


settings = Settings()
