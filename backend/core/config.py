"""
Configuration management for Priority Guardian SDK app Suite.

All configuration values loaded from environment variables.
"""

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

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
