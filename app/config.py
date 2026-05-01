from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qcmaster"
    db_echo: bool = False

    secret_key: str = "change-me-in-production-min-32-chars-long!!"
    redis_url: str = "redis://localhost:6379/0"

    access_token_expire_seconds: int = 900
    refresh_token_expire_seconds: int = 604800

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Anthropic API — dùng cho LLM chunker (Claude Haiku / third-party compatible)
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )
    anthropic_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_BASE_URL", "anthropic_base_url"),
    )

    @field_validator("anthropic_base_url", mode="before")
    @classmethod
    def empty_anthropic_base_url_to_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # Embedding service (FastAPI độc lập) để BE proxy gọi.
    embedding_service_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_SERVICE_URL", "embedding_service_url"),
    )
    embedding_service_internal_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_SERVICE_INTERNAL_KEY", "embedding_service_internal_key"),
    )

    @field_validator("embedding_service_url", mode="before")
    @classmethod
    def empty_embedding_service_url_to_none(cls, v: object) -> object:
        # docker compose có thể inject biến rỗng; coi như "chưa cấu hình".
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # R2 / Cloudflare — đọc env R2_* (hoặc tên snake_case tương đương)
    r2_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_ENDPOINT", "r2_endpoint_url"),
    )
    r2_region: str = Field(
        default="auto",
        validation_alias=AliasChoices("R2_REGION", "r2_region"),
    )
    r2_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_ACCESS_KEY_ID", "r2_access_key_id"),
    )
    r2_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_SECRET_ACCESS_KEY", "r2_secret_access_key"),
    )
    r2_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_BUCKET", "r2_bucket"),
    )
    r2_public_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_PUBLIC_BASE_URL", "r2_public_base_url"),
    )
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # strict | lax | none

    @field_validator("cookie_samesite")
    @classmethod
    def normalize_samesite(cls, v: str) -> str:
        s = v.lower().strip()
        if s not in ("strict", "lax", "none"):
            return "lax"
        return s

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
