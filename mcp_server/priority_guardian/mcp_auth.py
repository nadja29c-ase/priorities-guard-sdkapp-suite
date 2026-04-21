"""
JWT Authentication and Authorization for Priority Guardian MCP Server.

Implements OAuth 2.0 Bearer Token Usage (RFC 6750) with:
- JWT validation using JWKS
- In-memory JWKS caching with TTL and stale age limits
- Per-tool scope enforcement via TOOL_REGISTRY
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
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import jwt
import structlog
from jwt import PyJWKClient, PyJWK

from mcp_server.priority_guardian.config import (
    PG_JWKS_URL,
    PG_ISSUER,
    PG_AUDIENCE,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
)
from mcp_server.priority_guardian.request_context import auth_header_var


def _extract_origin(url: str) -> str:
    """
    Extract origin (scheme + host) from URL, stripping any path.

    Used for constructing /.well-known/* URLs which must be at the root.
    Example: https://pg.priority-guard.com/mcp -> https://pg.priority-guard.com
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Origin for resource_metadata URLs (/.well-known/oauth-protected-resource)
# Must use host only, not full MCP_SERVER_URL which may include /mcp path
_MCP_ORIGIN = _extract_origin(MCP_SERVER_URL)

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
                logger.info("jwks.fetch.start", url=PG_JWKS_URL)

                response = await self._http_client.get(PG_JWKS_URL)
                response.raise_for_status()

                jwks = response.json()

                # Update cache
                self._jwks = jwks
                self._fetched_at = time.time()

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
    4. Verify signature, issuer, audience, expiry, nbf (with leeway for clock skew)
    5. Extract claims: sub (user_id), scope, jti, azp

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
        # - aud = MCP_RESOURCE_URL (https://pg.priority-guard.com/mcp) — current: ChatGPT
        #   sends resource= in authorize, backend echoes it into aud
        # - aud = MCP_SERVER_URL (https://pg.priority-guard.com) — origin without /mcp path
        # - aud = PG_AUDIENCE (https://www.priority-guard.com) — legacy fallback
        # PyJWT accepts list of valid audiences for exact string matching
        valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, PG_AUDIENCE]

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=PG_ISSUER,
            audience=valid_audiences,
            leeway=TOKEN_EXPIRY_GRACE_SECONDS,  # Allow clock skew/network jitter
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

    Uses TOOL_REGISTRY as the single source of truth for required scopes.
    Fails closed on unknown tools (raises UnauthorizedError).

    Args:
        tool_name: Name of the tool being called
        token_scopes: Set of scopes from validated token
        correlation_id: Correlation ID for logging

    Raises:
        UnauthorizedError: If tool is not found in registry (fail closed)
        InsufficientScopeError: If required scopes not present
    """
    # Late import to avoid circular imports
    from mcp_server.priority_guardian.tools import get_tool

    tool_def = get_tool(tool_name)

    # Fail closed: unknown tool is an auth failure
    if tool_def is None:
        logger.warning(
            "scope.enforcement.unknown_tool",
            correlation_id=correlation_id,
            tool=tool_name
        )
        raise UnauthorizedError("invalid_token", "Token validation failed")

    required_scopes = tool_def.required_scopes

    if not required_scopes:
        logger.warning(
            "scope.enforcement.no_requirements",
            correlation_id=correlation_id,
            tool=tool_name
        )
        return

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
    if meta is None:
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
            f'Bearer resource_metadata="{_MCP_ORIGIN}/.well-known/oauth-protected-resource", '
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
            f'Bearer resource_metadata="{_MCP_ORIGIN}/.well-known/oauth-protected-resource", '
            f'error="insufficient_scope", error_description="Insufficient permissions"'
        ]
    }


# ============================================================================
# Cross-Device Identity Reconciliation (Increment 78)
# ============================================================================

async def reconcile_user_via_backend(
    jwt_user_id: str,
    meta: Optional[Dict[str, Any]],
    correlation_id: str,
) -> str:
    """
    Reconcile JWT-resolved user_id against openai/subject by calling the backend.

    MCP server does not access the DB. All reconciliation state lives in the backend.

    Returns the canonical user_id. Falls back to jwt_user_id if:
    - subject is absent or empty
    - backend call fails (degrade gracefully — do not block the tool call)

    Does NOT raise on backend failure — logs at WARNING and returns jwt_user_id
    unchanged. Reconciliation failure must not break tool execution.
    """
    # Late import to avoid circular imports
    from mcp_server.priority_guardian.http_client import reconcile_user

    subject = (meta or {}).get("openai/subject")

    if not subject:
        logger.debug(
            "auth.reconcile.subject_absent",
            correlation_id=correlation_id,
        )
        return jwt_user_id

    try:
        response = await reconcile_user(jwt_user_id, subject, correlation_id)

        canonical_user_id = response["user_id"]
        case = response["case"]

        logger.info(
            "auth.reconcile.result",
            correlation_id=correlation_id,
            case=case,
            jwt_user_id=jwt_user_id,
            canonical_user_id=canonical_user_id,
        )

        return canonical_user_id

    except Exception as e:
        logger.warning(
            "auth.reconcile.backend_failed",
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return jwt_user_id


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
        # Step 2: Extract Authorization header from ContextVar (set by middleware)
        # NOTE: After refactoring to manual registry, FastMCP no longer injects
        # headers into meta. The middleware captures the Authorization header
        # from HTTP scope and sets it in auth_header_var.
        auth_header = auth_header_var.get(None)

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

        # Inc 78: Reconcile JWT user_id against openai/subject for cross-device continuity.
        # MCP server stays stateless — reconciliation happens in the backend.
        user_id = await reconcile_user_via_backend(user_id, meta, correlation_id)

        # Step 5: Enforce tool-specific scopes
        enforce_tool_scope(tool_name, scopes, correlation_id)

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

    except jwt.ExpiredSignatureError as e:
        logger.warning("auth.token_expired", correlation_id=correlation_id, tool=tool_name)
        raise UnauthorizedError("invalid_token", "Token expired")

    except jwt.InvalidTokenError as e:
        logger.warning("auth.invalid_token", correlation_id=correlation_id, tool=tool_name, error=str(e))
        raise UnauthorizedError("invalid_token", str(e))

    except Exception as e:
        logger.error("auth.error", correlation_id=correlation_id, tool=tool_name, error=str(e))
        raise UnauthorizedError("invalid_token", "Token validation failed")
