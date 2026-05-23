from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/med"
    REDIS_URL: str = "redis://localhost:6379"

    # Supabase Storage (S3-compatible)
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    STORAGE_BUCKET_NAME: str = "med-materials"

    NEXTAUTH_SECRET: str
    OPENAI_API_KEY: str = ""
    SENTRY_DSN: str = ""
    ENVIRONMENT: str = "development"


settings = Settings()
