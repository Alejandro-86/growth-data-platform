"""Pipeline configuration from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the growth data platform."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    duckdb_path: str = "growth_platform.duckdb"
    sync_state_path: str = "sync_state.json"

    marttech_api_base_url: str = "http://localhost:8100"
    marttech_max_retries: int = 3
    marttech_retry_backoff_seconds: float = 0.5

    seed_num_users: int = 500
    seed_seed: int = 42


settings = Settings()
