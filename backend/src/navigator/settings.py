"""Typed settings, read from the environment and the git-ignored .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://navigator:navigator@localhost:5432/navigator"

    s3_endpoint: str = "localhost:8333"
    s3_secure: bool = False
    s3_bucket: str = "navigator"
    s3_seed_bucket: str = "navigator-seed"
    s3_access_key: str = "navigator"
    s3_secret_key: str = "navigator-dev"

    package_dir: str = "../APETIT_CLIMATE_NATURE_NAVIGATOR_2026"

    catalogue_path: str = "../config/actions/catalogue.json"

    gemini_api_key: str = ""
    gemini_model: str = ""

    worker_poll_seconds: float = 2.0
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
