"""
JWT Authentication and Authorization for Clarity MCP Server.

NOTE: This module is intentionally duplicated from mcp_server/focused/mcp_auth.py.
Future refactoring should extract shared auth logic to mcp_server/common/oauth_auth.py.
Duplication is acceptable for now to maintain app isolation during development.

Implements OAuth 2.0 Bearer Token Usage (RFC 6750) with:
- JWT validation using JWKS
- In-memory JWKS caching with TTL and stale age limits
- Per-tool scope enforcement
- RFC 6750-compliant error responses with WWW-Authenticate headers
- Correlation ID handling

Security:
- Never logs tokens or parts of tokens
- Fails closed on any validation error
- Uses PyJWT leeway for clock skew tolerance
"""

import asyncio
import time
from typing import Optional, Dict, List, Any, Set
from uuid import uuid4

import httpx
import jwt
import structlog
from jwt import PyJWK

from mcp_server.clarity.config import (
    CLARITY_JWKS_URL,
    CLARITY_ISSUER,
    CLARITY_AUDIENCE,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
    TOOL_SCOPES,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
)
from mcp_server.clarity.request_context import auth_header_var

logger = structlog.get_logger(__name__)


# ============================================================================
# JWKS Cache (In-Memory)
# ============================================================================

class JWKSCache:
    """
    In-memory JWKS cache with TTL and max stale age.

    Implements:
    - 24-hour TTL for cached JWKS
    - 7-day maximum stale age (fail closed if too old)
    - Retry on unknown kid
    - Thread-safe caching
    """

    def __init__(self):
        self._jwks: Optional[Dict[str, Any]] = None
        self._fetched_at: Optional[float] = None
        self._http_client = httpx.AsyncClient(timeout=JWKS_FETCH_TIMEOUT_SECONDS)
        self._lock = asyncio.Lock()  # Prevents thundering herd on cold start

    def is_cache_valid(self) -> bool:
        """Check if cache is still valid (within TTL)."""
        if self._jwks is None or self._fetched_at is None:
            return False

        age = time.time() - self._fetched_at
        return age < JWKS_CACHE_TTL_SECONDS

    def is_cache_too_old(self) -> bool:
        """Check if cache is too old to use (beyond max stale age)."""
        if self._fetched_at is None:
            return True

        age = time.time() - self._fetched_at
        return age > JWKS_MAX_STALE_SECONDS

    async def fetch_jwks(self, force: bool = False) -> Dict[str, Any]:
        """
        Fetch JWKS from backend, with caching.

        Args:
            force: If True, bypass cache and force refetch

        Returns:
            JWKS dictionary

        Raises:
            Exception: If fetch fails and cache is invalid/too old
        """
        # Fast path: use cache if valid and not forcing refresh (no lock needed)
        if not force and self.is_cache_valid():
            logger.debug("jwks.cache.hit")
            return self._jwks

        # Slow path: acquire lock to prevent thundering herd
        async with self._lock:
            # Double-check: another coroutine may have populated cache while we waited
            if not force and self.is_cache_valid():
                logger.debug("jwks.cache.hit_after_lock")
                return self._jwks

            # Check if cache is too old
            if self.is_cache_too_old():
                logger.warning("jwks.cache.too_old", age_days=int((time.time() - self._fetched_at) / 86400) if self._fetched_at else None)

            # Fetch fresh JWKS
            try:
                logger.debug("jwks.fetch.start", url=CLARITY_JWKS_URL)

                response = await self._http_client.get(CLARITY_JWKS_URL)
                response.raise_for_status()

                jwks = response.json()

                # Update cache
                self._jwks = jwks
                self._fetched_at = time.time()

                # info level: useful to know when cache was refreshed (infrequent)
                logger.info("jwks.fetch.success", keys_count=len(jwks.get("keys", [])))

                return jwks

            except Exception as e:
                logger.error("jwks.fetch.error", error=str(e))

                # If cache exists and not too old, use it despite fetch failure
                if self._jwks is not None and not self.is_cache_too_old():
                    logger.warning("jwks.fetch.failed_using_stale_cache")
                    return self._jwks

                # Fail closed: no valid cache available
                raise Exception(f"JWKS fetch failed and no valid cache available: {e}")

    def get_signing_key(self, kid: str) -> Optional[PyJWK]:
        """
        Get signing key from cached JWKS by kid.

        Args:
            kid: Key ID from JWT header

        Returns:
            PyJWK signing key or None if not found
        """
        if self._jwks is None:
            return None

        for key_data in self._jwks.get("keys", []):
            if key_data.get("kid") == kid:
                return PyJWK.from_dict(key_data)

        return None

    async def aclose(self):
        """Close the HTTP client to prevent connection leaks."""
        await self._http_client.aclose()


# Global JWKS cache instance
_jwks_cache = JWKSCache()


async def cleanup_jwks_cache() -> None:
    """
    Close the JWKS cache HTTP client.

    Should be called on application shutdown to prevent connection leaks.
    """
    await _jwks_cache.aclose()
    logger.info("jwks.cache.closed")


# ============================================================================
# Header Extraction
# ============================================================================

def extract_authorization_header(headers: Dict[str, Any]) -> Optional[str]:
    """
    Extract Authorization header from request metadata.

    Normalizes header keys to lowercase for case-insensitive lookup.

    Args:
        headers: Request headers dictionary

    Returns:
        Authorization header value or None if not found
    """
    # Normalize header keys to lowercase
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    return normalized_headers.get("authorization")


def extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
    """
    Extract Bearer token from Authorization header.

    Expected format: "Bearer <access_token>"

    Args:
        auth_header: Authorization header value

    Returns:
        Access token or None if invalid format
    """
    if not auth_header:
        return None

    parts = auth_header.split()

    if len(parts) != 2:
        return None

    if parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()

    if not token:
        return None

    return token


# ============================================================================
# JWT Validation
# ============================================================================

async def validate_jwt(token: str, correlation_id: str) -> Dict[str, Any]:
    """
    Validate JWT access token.

    Validation steps:
    1. Decode JWT header to extract kid
    2. Fetch JWKS and lookup signing key
    3. If kid not found, refetch JWKS once and retry
    4. Verify signature, issuer, audience, expiry, nbf
    5. Extract azp claim (not validated — see remove_azp.md)
    6. Extract claims: sub (user_id), scope, jti

    Args:
        token: JWT access token
        correlation_id: Correlation ID for logging

    Returns:
        Dictionary with validated claims

    Raises:
        jwt.InvalidTokenError: If token is invalid
        Exception: If validation fails for any reason
    """
    try:
        # Step 1: Decode header without verification to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            logger.warning("jwt.validation.no_kid", correlation_id=correlation_id)
            raise jwt.InvalidTokenError("Missing kid in JWT header")

        # Step 2: Fetch JWKS and lookup signing key
        await _jwks_cache.fetch_jwks()
        signing_key = _jwks_cache.get_signing_key(kid)

        # Step 3: Retry on unknown kid
        if signing_key is None:
            logger.info("jwt.validation.unknown_kid_refetching", correlation_id=correlation_id, kid=kid)

            # Force refetch JWKS
            await _jwks_cache.fetch_jwks(force=True)
            signing_key = _jwks_cache.get_signing_key(kid)

            if signing_key is None:
                logger.warning("jwt.validation.unknown_kid", correlation_id=correlation_id, kid=kid)
                raise jwt.InvalidTokenError(f"Unknown kid: {kid}")

        # Step 4: Verify JWT with all required checks
        # RFC 9728 B2-5: Accept any valid audience for this resource
        # - aud = MCP_RESOURCE_URL (e.g. .../mcp) — current: client sends resource=
        #   in authorize request, backend echoes it into aud
        # - aud = MCP_SERVER_URL (origin without /mcp) — fallback
        # - aud = CLARITY_AUDIENCE (issuer URL) — legacy tokens without resource param
        # PyJWT accepts list of valid audiences for exact string matching
        # leeway: accepts tokens expired up to N seconds ago (handles clock skew)
        valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLARITY_ISSUER,
            audience=valid_audiences,
            leeway=TOKEN_EXPIRY_GRACE_SECONDS,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "iss", "aud", "sub", "scope", "jti"],
            }
        )

        # Step 5: Extract azp claim (logged but not validated - see remove_azp.md)
        # NOTE: azp validation removed because dynamic client registration assigns
        # different client_ids per user, making static validation impossible.
        azp = payload.get("azp")

        # Extract claims
        user_id = payload.get("sub")
        scope_str = payload.get("scope", "")
        scopes = set(scope_str.split()) if scope_str else set()
        jti = payload.get("jti")

        # debug level: detailed validation info (auth.success provides audit trail)
        logger.debug(
            "jwt.validation.success",
            correlation_id=correlation_id,
            user_id=user_id,
            jti=jti,
            azp=azp,
            scopes=list(scopes)
        )

        return {
            "user_id": user_id,
            "scopes": scopes,
            "jti": jti,
            "azp": azp,
            "claims": payload
        }

    except jwt.ExpiredSignatureError as e:
        logger.warning("jwt.validation.expired", correlation_id=correlation_id, error=str(e))
        raise

    except jwt.InvalidTokenError as e:
        logger.warning("jwt.validation.invalid", correlation_id=correlation_id, error=str(e))
        raise

    except Exception as e:
        logger.error("jwt.validation.error", correlation_id=correlation_id, error=str(e))
        raise


# ============================================================================
# Scope Enforcement
# ============================================================================

def check_scopes(token_scopes: Set[str], required_scopes: List[str]) -> bool:
    """
    Check if token has all required scopes.

    Args:
        token_scopes: Set of scopes from token
        required_scopes: List of required scopes for tool

    Returns:
        True if all required scopes present, False otherwise
    """
    return all(scope in token_scopes for scope in required_scopes)


def enforce_tool_scope(tool_name: str, token_scopes: Set[str], correlation_id: str) -> None:
    """
    Enforce scope requirements for a tool.

    Security: Fails closed on unknown tools. If a tool is not in TOOL_SCOPES,
    access is denied. This prevents typos or unknown tools from bypassing auth.

    Args:
        tool_name: Name of the tool being called
        token_scopes: Set of scopes from validated token
        correlation_id: Correlation ID for logging

    Raises:
        InsufficientScopeError: If required scopes not present OR tool unknown
    """
    # SECURITY: Fail closed on unknown tools
    if tool_name not in TOOL_SCOPES:
        logger.warning(
            "scope.enforcement.unknown_tool",
            correlation_id=correlation_id,
            tool=tool_name
        )
        raise InsufficientScopeError(
            required_scopes=["<tool not registered>"],
            actual_scopes=list(token_scopes)
        )

    required_scopes = TOOL_SCOPES[tool_name]

    if not check_scopes(token_scopes, required_scopes):
        logger.warning(
            "scope.enforcement.insufficient",
            correlation_id=correlation_id,
            tool=tool_name,
            required=required_scopes,
            actual=list(token_scopes)
        )

        raise InsufficientScopeError(
            required_scopes=required_scopes,
            actual_scopes=list(token_scopes)
        )

    logger.debug(
        "scope.enforcement.success",
        correlation_id=correlation_id,
        tool=tool_name,
        required=required_scopes
    )


# ============================================================================
# Correlation ID Handling
# ============================================================================

def extract_or_generate_correlation_id(meta: Optional[Dict[str, Any]]) -> str:
    """
    Extract correlation_id from request metadata or generate new UUID.

    Args:
        meta: Request metadata dictionary (_meta from FastMCP)

    Returns:
        Valid correlation_id (UUID string)
    """
    # Defensive: meta could be None or non-dict
    if not isinstance(meta, dict):
        correlation_id = str(uuid4())
        logger.debug("correlation.generated", correlation_id=correlation_id)
        return correlation_id

    # Try to extract from metadata
    correlation_id = meta.get("correlation_id")

    # Validate format (basic UUID check)
    if correlation_id and isinstance(correlation_id, str) and len(correlation_id) > 0:
        logger.debug("correlation.extracted", correlation_id=correlation_id)
        return correlation_id

    # Generate new if missing or malformed
    correlation_id = str(uuid4())
    logger.debug("correlation.generated_fallback", correlation_id=correlation_id)
    return correlation_id


# ============================================================================
# RFC 6750 Error Builders
# ============================================================================

class OAuthError(Exception):
    """Base class for OAuth errors."""
    pass


class UnauthorizedError(OAuthError):
    """Raised when token is invalid (401)."""

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        super().__init__(description)


class InsufficientScopeError(OAuthError):
    """Raised when token lacks required scopes (403)."""

    def __init__(self, required_scopes: List[str], actual_scopes: List[str]):
        self.required_scopes = required_scopes
        self.actual_scopes = actual_scopes
        self.error = "insufficient_scope"
        self.description = f"Required {required_scopes}, got {actual_scopes}"
        super().__init__(self.description)


def build_unauthorized_meta() -> Dict[str, Any]:
    """
    Build _meta dict for 401 Unauthorized responses.

    Returns dict to assign to CallToolResult._meta with mcp/www_authenticate
    containing RFC 7235 challenge string for ChatGPT OAuth re-auth flow.

    Format per OpenAI MCP Authentication spec:
    _meta["mcp/www_authenticate"] = ['Bearer resource_metadata="...", error="...", error_description="..."']

    Returns:
        Dict with mcp/www_authenticate key for CallToolResult._meta
    """
    return {
        "mcp/www_authenticate": [
            f'Bearer resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource", '
            f'error="invalid_token", error_description="Authentication required"'
        ]
    }


def build_forbidden_meta() -> Dict[str, Any]:
    """
    Build _meta dict for 403 Forbidden responses.

    Returns dict to assign to CallToolResult._meta with mcp/www_authenticate
    containing RFC 7235 challenge string for ChatGPT OAuth re-auth flow.

    Format per OpenAI MCP Authentication spec:
    _meta["mcp/www_authenticate"] = ['Bearer resource_metadata="...", error="...", error_description="..."']

    Returns:
        Dict with mcp/www_authenticate key for CallToolResult._meta
    """
    return {
        "mcp/www_authenticate": [
            f'Bearer resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource", '
            f'error="insufficient_scope", error_description="Insufficient permissions"'
        ]
    }


def build_invalid_params_error(
    message: str = "Invalid parameters",
    details: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build JSON-RPC error response for -32602 Invalid Params.

    Used when tool input validation fails and cannot be repaired.
    This is a standard JSON-RPC error code for malformed request parameters.

    Args:
        message: Human-readable error message
        details: Optional additional details about what was wrong

    Returns:
        JSON-RPC error response dictionary
    """
    error_data: Dict[str, Any] = {}
    if details:
        error_data["details"] = details

    result: Dict[str, Any] = {
        "error": {
            "code": -32602,
            "message": message,
        }
    }

    if error_data:
        result["error"]["data"] = error_data

    return result


# ============================================================================
# Main Authentication Function
# ============================================================================

async def authenticate_request(
    tool_name: str,
    meta: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Authenticate and authorize MCP tool request.

    This is the main entry point for authentication. It:
    1. Extracts correlation_id from metadata
    2. Extracts Authorization header
    3. Validates JWT token
    4. Enforces tool-specific scopes
    5. Returns validated user context

    Args:
        tool_name: Name of the tool being called
        meta: Request metadata from FastMCP (_meta)

    Returns:
        Dictionary with:
        - user_id: Validated user ID from token
        - correlation_id: Request correlation ID
        - scopes: Set of granted scopes
        - jti: Token ID

    Raises:
        UnauthorizedError: If token is invalid (401)
        InsufficientScopeError: If scopes are insufficient (403)
    """
    # Step 1: Extract/generate correlation ID
    correlation_id = extract_or_generate_correlation_id(meta)

    try:
        # Step 2: Extract Authorization header
        # Priority: context var (from HTTP request via middleware) > meta.headers
        # Context var is set by MCPContentTypeAndAcceptFixMiddleware for /mcp requests
        auth_header = auth_header_var.get(None)

        if not auth_header:
            # Fallback to meta.headers (for direct calls or testing)
            if not isinstance(meta, dict):
                headers = {}
            else:
                raw_headers = meta.get("headers")
                headers = raw_headers if isinstance(raw_headers, dict) else {}
            auth_header = extract_authorization_header(headers)

        if not auth_header:
            logger.warning("auth.missing_header", correlation_id=correlation_id, tool=tool_name)
            raise UnauthorizedError("invalid_token", "Missing Authorization header")

        # Step 3: Extract Bearer token
        token = extract_bearer_token(auth_header)

        if not token:
            logger.warning("auth.invalid_format", correlation_id=correlation_id, tool=tool_name)
            raise UnauthorizedError("invalid_token", "Invalid Authorization header format (expected: Bearer <token>)")

        # Step 4: Validate JWT
        validated = await validate_jwt(token, correlation_id)

        user_id = validated["user_id"]
        scopes = validated["scopes"]
        jti = validated["jti"]
        azp = validated["azp"]

        # Step 5: Enforce tool-specific scopes
        enforce_tool_scope(tool_name, scopes, correlation_id)

        # info level: audit trail for successful auth (one log per request)
        logger.info(
            "auth.success",
            correlation_id=correlation_id,
            tool=tool_name,
            user_id=user_id,
            jti=jti,
            azp=azp
        )

        return {
            "user_id": user_id,
            "correlation_id": correlation_id,
            "scopes": scopes,
            "jti": jti,
            "azp": azp
        }

    except UnauthorizedError:
        raise

    except InsufficientScopeError:
        raise

    except jwt.ExpiredSignatureError:
        logger.warning("auth.token_expired", correlation_id=correlation_id, tool=tool_name)
        raise UnauthorizedError("invalid_token", "Token expired")

    except jwt.InvalidTokenError as e:
        logger.warning("auth.invalid_token", correlation_id=correlation_id, tool=tool_name, error=str(e))
        raise UnauthorizedError("invalid_token", "Token validation failed")

    except Exception as e:
        logger.error("auth.error", correlation_id=correlation_id, tool=tool_name, error=str(e))
        raise UnauthorizedError("invalid_token", "Token validation failed")
