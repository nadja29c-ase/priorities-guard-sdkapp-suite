"""
Configuration management for Priority Guardian SDK app Suite.

All configuration values loaded from environment variables.
"""

import base64
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application settings
    APP_NAME: str = "priority-guardian"
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database settings
    DATABASE_URL: str

    # Security settings
    ENCRYPTION_KEY: str

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/focused/google/callback"

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Webhook settings
    WEBHOOK_RENEWAL_THRESHOLD_HOURS: int = 48
    WEBHOOK_IDEMPOTENCY_TTL_SECONDS: int = 86400  # 24 hours
    WEBHOOK_RENEWAL_THROTTLE_SECONDS: int = 86400  # 24 hours
    WEBHOOK_NEEDS_SYNC_TTL_SECONDS: int = 300  # 5 minutes

    # OAuth Provider Settings (Increment 7A)
    OAUTH_RSA_PRIVATE_KEY: str  # Base64-encoded PEM (REQUIRED)
    OAUTH_RSA_PUBLIC_KEY: str   # Base64-encoded PEM (REQUIRED)
    OAUTH_JWT_KID: str = "focused-2025-11"
    OAUTH_ISSUER: str = "https://www.priority-guard.com"
    OAUTH_TOKEN_EXPIRY_SECONDS: int = 3600  # 1 hour
    OAUTH_REFRESH_TOKEN_EXPIRY_DAYS: int = 30

    @model_validator(mode='after')
    def validate_oauth_keys(self) -> 'Settings':
        """Validate OAuth keys are base64-encoded strings."""
        if self.OAUTH_RSA_PRIVATE_KEY:
            try:
                base64.b64decode(self.OAUTH_RSA_PRIVATE_KEY)
            except Exception:
                raise ValueError("OAUTH_RSA_PRIVATE_KEY must be valid base64-encoded PEM")

        if self.OAUTH_RSA_PUBLIC_KEY:
            try:
                base64.b64decode(self.OAUTH_RSA_PUBLIC_KEY)
            except Exception:
                raise ValueError("OAUTH_RSA_PUBLIC_KEY must be valid base64-encoded PEM")

        return self

    @model_validator(mode='after')
    def fix_database_url(self) -> 'Settings':
        """Convert postgresql:// to postgresql+asyncpg:// for SQLAlchemy async."""
        if self.DATABASE_URL and self.DATABASE_URL.startswith("postgresql://"):
            object.__setattr__(self, 'DATABASE_URL',
                self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1))
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
