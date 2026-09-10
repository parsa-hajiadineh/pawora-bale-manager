from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings come from environment variables (and optional .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "sqlite:///./data/bale.db"
    bale_account: str = ""
    bale_bot_token: str = ""
    bale_api_base_url: str = "https://tapi.bale.ai"
    bale_adapter: str = "http"
    group_id: str = ""
    invite_link: str = ""
    invite_interval: int = 5
    worker_poll_seconds: int = 2
    max_retries: int = 3
    job_retry_delay_seconds: int = 60
    log_level: str = "INFO"
    log_dir: str = "./logs"
    invite_strategy: str = "auto"
    auto_invite_on_start: bool = True
    invite_message: str = (
        "سلام همکار گرامی، برای عضویت در گروه از لینک زیر استفاده کنید:\n{invite_link}"
    )
    bot_start_message: str = (
        "سلام. برای عضویت در گروه همکاران لینک زیر را باز کنید "
        "یا شماره خود را با دکمه ارسال کنید تا شما را اضافه کنیم.\n{invite_link}"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
