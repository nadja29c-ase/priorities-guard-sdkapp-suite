"""
Configuration management for Priority Guardian SDK app Suite.

All configuration values loaded from environment variables.
"""

import base64
from typing import ClassVar
from urllib.parse import urlparse

from pydantic import Field, model_validator
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
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

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

    # RFC 9728 B2-8: Redirect URI allowlist for DCR
    # Only these URIs are accepted during dynamic client registration.
    # In dev mode, localhost URIs are also accepted for testing.
    # ChatGPT redirect URIs (production allowlist):
    # ClassVar ensures Pydantic v2 treats this as a class constant, not a field
    _CHATGPT_REDIRECT_URIS: ClassVar[list[str]] = [
        "https://chatgpt.com/connector/oauth/",  # prefix — any connector callback_id
        "https://chatgpt.com/connector_platform_oauth_redirect",  # legacy
        "https://platform.openai.com/apps-manage/oauth",  # review
    ]

    # Populated by build_allowed_redirect_uris validator at startup
    OAUTH_ALLOWED_REDIRECT_URIS: list[str] = Field(default_factory=list)

    # Public URL for browser-facing endpoints (Increment 18)
    # Used for constructing OAuth initiation URLs shown to users
    BACKEND_PUBLIC_URL: str = "https://www.priority-guard.com"

    # Internal API secret for MCP server -> backend communication
    # MCP servers send this in X-Internal-Secret header to authenticate internal calls
    INTERNAL_API_SECRET: str = ""  # Empty = disabled (dev only)

    # MCP Server URL for Priority Guardian (used for OAuth protected resource metadata)
    # This env var is shared with the MCP server deployment
    PG_MCP_SERVER_URL: str = "http://localhost:8003"

    @model_validator(mode='after')
    def validate_production_security(self) -> 'Settings':
        """Fail fast if production is missing required security settings.

        INTERNAL_API_SECRET protects internal endpoints (MCP -> backend).
        In dev, empty secret disables verification for convenience.
        In production, this MUST be set to prevent unauthorized access.
        """
        is_production = self.ENV.lower() in ("production", "prod")
        if is_production and not self.INTERNAL_API_SECRET:
            raise ValueError(
                "INTERNAL_API_SECRET is required in production. "
                "Set ENV=dev to disable this check for local development."
            )
        return self

    @model_validator(mode='after')
    def validate_production_urls(self) -> 'Settings':
        """Validate production URL requirements (Increment 52).

        In production only:
        - OAUTH_ISSUER must use HTTPS and have no path component (B2-2 invariant)
        - BACKEND_PUBLIC_URL must use HTTPS
        - PG_MCP_SERVER_URL must use HTTPS
        """
        is_production = self.ENV.lower() in ("production", "prod")
        if not is_production:
            return self

        # OAUTH_ISSUER: must be HTTPS
        issuer_parsed = urlparse(self.OAUTH_ISSUER)
        if issuer_parsed.scheme != "https":
            raise ValueError(
                f"OAUTH_ISSUER must use HTTPS in production. "
                f"Got: {self.OAUTH_ISSUER!r} (scheme: {issuer_parsed.scheme})"
            )

        # OAUTH_ISSUER: must have no path component (B2-2: issuer must be root domain)
        if issuer_parsed.path not in ("", "/"):
            raise ValueError(
                f"OAUTH_ISSUER must be a root domain with no path component (RFC 8414 B2-2). "
                f"Got: {self.OAUTH_ISSUER!r} (path: {issuer_parsed.path!r})"
            )

        # BACKEND_PUBLIC_URL: must be HTTPS
        backend_parsed = urlparse(self.BACKEND_PUBLIC_URL)
        if backend_parsed.scheme != "https":
            raise ValueError(
                f"BACKEND_PUBLIC_URL must use HTTPS in production. "
                f"Got: {self.BACKEND_PUBLIC_URL!r} (scheme: {backend_parsed.scheme})"
            )

        # PG_MCP_SERVER_URL: must be HTTPS
        mcp_parsed = urlparse(self.PG_MCP_SERVER_URL)
        if mcp_parsed.scheme != "https":
            raise ValueError(
                f"PG_MCP_SERVER_URL must use HTTPS in production. "
                f"Got: {self.PG_MCP_SERVER_URL!r} (scheme: {mcp_parsed.scheme})"
            )

        return self

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

    @model_validator(mode='after')
    def build_allowed_redirect_uris(self) -> 'Settings':
        """Build allowed redirect URIs based on environment.

        In production: Only ChatGPT redirect URIs.
        In dev mode: ChatGPT URIs + localhost URIs for testing.
        """
        allowed = list(self._CHATGPT_REDIRECT_URIS)
        is_dev = self.ENV.lower() in ("dev", "development", "local", "test")
        if is_dev:
            allowed.extend([
                "http://localhost:3000/callback",
                "http://localhost:8000/callback",
                "http://127.0.0.1:3000/callback",
                "http://127.0.0.1:8000/callback",
            ])
        object.__setattr__(self, 'OAUTH_ALLOWED_REDIRECT_URIS', allowed)
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

# Derived constants for OAuth WWW-Authenticate header (B2-7 compliance)
# Used by main.py oauth_exception_handler and token_endpoint.py
# Extract origin only (scheme + host) - /.well-known/* URLs must be at the root
_parsed_mcp_url = urlparse(settings.PG_MCP_SERVER_URL)
_MCP_ORIGIN = f"{_parsed_mcp_url.scheme}://{_parsed_mcp_url.netloc}"
RESOURCE_METADATA_URL = f"{_MCP_ORIGIN}/.well-known/oauth-protected-resource"
WWW_AUTHENTICATE_VALUE = f'Bearer resource_metadata="{RESOURCE_METADATA_URL}"'
