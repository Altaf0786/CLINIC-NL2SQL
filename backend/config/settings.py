"""
Pydantic-based configuration with .env loading and validation.
Follows 12-factor app principles with secure defaults.
"""

import secrets
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

# Load .env early so os.getenv() fallbacks in service modules also work.
load_dotenv()


class Settings(BaseSettings):
    """Application configuration with environment-based overrides and validation.

    All settings can be overridden via environment variables or a ``.env`` file.
    Comma-separated values (e.g. ALLOWED_ORIGINS, MODEL_FALLBACKS) are
    automatically parsed into Python lists by field validators.
    """

    model_config = ConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # === API ===
    API_HOST: str = Field(default="0.0.0.0", description="API server host")
    API_PORT: int = Field(default=8000, description="API server port")
    ENVIRONMENT: str = Field(default="development")

    # === Security ===
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    ALLOWED_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8000")

    # === Groq / LLM ===
    GROQ_API_KEY: str = Field(default="")
    MODEL_NAME: str = Field(default="llama-3.3-70b-versatile")
    MODEL_FALLBACKS: str = Field(
        default="llama-3.3-70b-versatile,meta-llama/llama-4-scout-17b-16e-instruct,qwen/qwen3-32b,llama-3.1-8b-instant"
    )

    # === Database ===
    DATABASE_URL: str = Field(default="clinic.db")
    DATABASE_TIMEOUT: int = Field(default=30)

    # === Logging ===
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    LOG_FILE: Optional[str] = Field(default="app.log")

    # === Performance ===
    MAX_REQUEST_SIZE: int = Field(default=10485760)
    QUERY_TIMEOUT: int = Field(default=60)
    DB_POOL_SIZE: int = Field(default=5, description="SQLite connection pool size")
    QUERY_CACHE_SIZE: int = Field(default=128, description="LRU cache capacity for SQL results")

    # === Rate Limiting ===
    RATE_LIMITING_ENABLED: bool = Field(default=True)
    RATE_LIMIT_PER_MINUTE: int = Field(default=30)

    # === Monitoring ===
    REQUEST_LOGGING_ENABLED: bool = Field(default=True)

    # --- Validators ---

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure LOG_LEVEL is a standard Python logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Ensure ENVIRONMENT is one of development, staging, or production."""
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of {valid_envs}")
        return v.lower()

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("MODEL_FALLBACKS")
    @classmethod
    def parse_model_fallbacks(cls, v: str | list) -> list[str]:
        """Parse comma-separated fallback model names into a list."""
        if isinstance(v, str):
            return [model.strip() for model in v.split(",") if model.strip()]
        return v

    @property
    def is_production(self) -> bool:
        """Return True when running in the production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Return True when running in the development environment."""
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


settings = get_settings()
