from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
