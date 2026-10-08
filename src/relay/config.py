from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RELAY_", env_file=".env", extra="ignore"
    )
    app_name: str = "Relay"
    environment: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "postgresql+asyncpg://relay:relay@localhost:5432/relay"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: SecretStr = SecretStr(
        "dev-only-insecure-secret-change-me-0123456789"
    )
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
