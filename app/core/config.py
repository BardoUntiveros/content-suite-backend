from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Content Suite API"
    app_env: str = Field(default="development", alias="APP_ENV")
    secret_key: str = Field(default=..., alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(
        default=1440, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/contentsuite",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    groq_api_key: str = Field(default=..., alias="GROQ_API_KEY")
    groq_model: str = Field(
        default="moonshotai/kimi-k2-instruct-0905", alias="GROQ_MODEL"
    )

    google_api_key: str = Field(default=..., alias="GOOGLE_API_KEY")
    google_text_model: str = Field(
        default="gemini-2.5-flash", alias="GOOGLE_TEXT_MODEL"
    )
    google_vision_model: str = Field(
        default="gemini-2.5-flash", alias="GOOGLE_VISION_MODEL"
    )
    google_embedding_model: str = Field(
        default="gemini-embedding-001", alias="GOOGLE_EMBEDDING_MODEL"
    )

    langfuse_public_key: str = Field(default=..., alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default=..., alias="LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )

    seed_default_users: bool = Field(default=True, alias="SEED_DEFAULT_USERS")
    demo_users_json: str | None = Field(default=None, alias="DEMO_USERS_JSON")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if not value:
            raise ValueError("SECRET_KEY must be set")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
