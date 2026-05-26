from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


DEFAULT_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/med"
DEFAULT_REDIS_URL = "redis://localhost:6379"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = DEFAULT_DATABASE_URL
    REDIS_URL: str = DEFAULT_REDIS_URL

    # Supabase Storage (S3-compatible)
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    STORAGE_BUCKET_NAME: str = "med-materials"

    NEXTAUTH_SECRET: str
    OPENAI_API_KEY: str = ""
    SENTRY_DSN: str = ""
    ENVIRONMENT: str = "development"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def non_empty_database_url(cls, value: str | None) -> str:
        if value is None:
            return DEFAULT_DATABASE_URL
        text = str(value).strip()
        return text or DEFAULT_DATABASE_URL

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def non_empty_redis_url(cls, value: str | None) -> str:
        if value is None:
            return DEFAULT_REDIS_URL
        text = str(value).strip()
        return text or DEFAULT_REDIS_URL


settings = Settings()
