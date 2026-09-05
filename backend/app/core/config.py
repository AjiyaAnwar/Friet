"""Centralized typed configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="FreightCore", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    debug: bool = Field(default=False, alias="DEBUG")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="freightcore", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="freightcore", alias="POSTGRES_DB")
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, alias="DATABASE_MAX_OVERFLOW")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL"
    )
    elasticsearch_url: str = Field(
        default="http://localhost:9200", alias="ELASTICSEARCH_URL"
    )

    jwt_secret_key: str = Field(
        default="dev-only-change-me-use-openssl-rand-hex-32", alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    encryption_key: str = Field(
        default="dev-only-generate-with-cryptography-fernet-generate-key", alias="ENCRYPTION_KEY"
    )

    cors_origins: list[str] = Field(
        default=["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    max_failed_login_attempts: int = Field(default=5, alias="MAX_FAILED_LOGIN_ATTEMPTS")
    account_lockout_minutes: int = Field(default=30, alias="ACCOUNT_LOCKOUT_MINUTES")

    rate_limit_internal: int = Field(default=1000, alias="RATE_LIMIT_INTERNAL")
    rate_limit_portal: int = Field(default=100, alias="RATE_LIMIT_PORTAL")
    rate_limit_unauth: int = Field(default=20, alias="RATE_LIMIT_UNAUTH")

    idempotency_ttl_seconds: int = Field(default=86400, alias="IDEMPOTENCY_TTL_SECONDS")
    max_request_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_REQUEST_BYTES")
    invoice_approval_threshold: float = Field(default=5000.0, alias="INVOICE_APPROVAL_THRESHOLD")

    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND"
    )

    @property
    def database_url_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: object) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on", "t")
        return bool(v)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        placeholders = {
            "dev-only-change-me-use-openssl-rand-hex-32",
            "dev-only-generate-with-cryptography-fernet-generate-key",
            "change_me_in_production",
        }
        if self.app_env == "production":
            if self.jwt_secret_key in placeholders or len(self.jwt_secret_key) < 32:
                raise ValueError("Production requires a strong JWT_SECRET_KEY (min 32 chars)")
            if self.encryption_key in placeholders:
                raise ValueError("Production requires a real ENCRYPTION_KEY")
            if self.postgres_password in placeholders:
                raise ValueError("Production requires a non-placeholder POSTGRES_PASSWORD")
        return self


@lru_cache
def get_settings() -> Settings:
    # Required secrets are supplied by pydantic-settings from environment variables.
    return Settings()  # type: ignore[call-arg]
