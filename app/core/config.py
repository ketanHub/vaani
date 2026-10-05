from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vaani"
    environment: str = "development"
    log_level: str = "INFO"
    default_tenant_id: str = "demo-clinic"
    database_url: str = "sqlite+aiosqlite:///./vaani.db"
    auto_create_schema: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_enabled: bool = False

    local_voice_enabled: bool = False
    local_voice_warmup: bool = True
    whisper_model: str = "small"
    whisper_download_root: str = "models/whisper"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_num_workers: int = 1
    piper_english_model: str = "models/piper/en_US-lessac-medium.onnx"
    piper_hindi_model: str = "models/piper/hi_IN-priyamvada-medium.onnx"
    piper_use_cuda: bool = False
    piper_num_workers: int = 1

    exotel_shared_secret: str | None = None
    exotel_account_sid: str | None = None
    exotel_vad_threshold: float = 450.0
    exotel_endpoint_silence_ms: int = 600

    calendar_provider: str = "memory"
    google_calendar_id: str | None = None
    google_calendar_access_token: str | None = None

    whatsapp_messages_url: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_template_name: str = "appointment_confirmation"
    whatsapp_template_language: str = "en"
    notifications_auto_dispatch: bool = True
    notifications_poll_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_prefix="VAANI_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
