from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "production"
    app_debug: bool = False
    service_name: str = "kom-dom-b-api"
    service_port: int = 8100
    public_base_url: str = "https://aspect.komunal-dom.ru"
    channels_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
