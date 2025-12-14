"""
Cookie helper functions for OAuth browser sessions (Increment 19).

Responsible ONLY for reading and writing the pg_session cookie on HTTP
requests/responses.

This module does NOT create, validate, or store OAuth sessions.
Session persistence and lookup is handled in session_service.py.

cookies.py = HTTP cookie mechanics only
"""

from fastapi import Request, Response

from backend.core.config import settings

# Cookie configuration
COOKIE_NAME = "pg_session" #pg=priority guardian
COOKIE_MAX_AGE = 2 * 365 * 24 * 60 * 60  # 2 years in seconds (63072000)
COOKIE_PATH = "/oauth"


def get_session_cookie(request: Request) -> str | None:
    """
    Read the session cookie from a request.

    Args:
        request: FastAPI request object

    Returns:
        Session token if cookie exists, None otherwise
    """
    return request.cookies.get(COOKIE_NAME)


def set_session_cookie(response: Response, token: str) -> None:
    """
    Set the session cookie on a response.

    Cookie attributes:
    - HttpOnly: true (no JavaScript access, XSS protection)
    - Secure: true in production (HTTPS only)
    - SameSite: Lax (sent on OAuth redirects, blocked on cross-site POST)
    - Path: /oauth (only sent on OAuth endpoints)
    - Max-Age: 2 years (sliding window, matches SESSION_LIFETIME_DAYS)

    Args:
        response: FastAPI response object
        token: Session token to store in cookie
    """
    # Only set Secure in production (not localhost dev)
    is_secure = settings.ENV != "dev"

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path=COOKIE_PATH,
    )


def delete_session_cookie(response: Response) -> None:
    """
    Delete the session cookie from a response.

    Sets the cookie with max_age=0 to clear it from the browser.
    Uses set_cookie instead of delete_cookie to preserve security attributes.

    Args:
        response: FastAPI response object
    """
    # Only set Secure in production (not localhost dev)
    is_secure = settings.ENV != "dev"

    # Note: delete_cookie() doesn't accept httponly/secure/samesite params,
    # so we use set_cookie with max_age=0 to properly clear the cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value="",
        max_age=0,
        expires=0,
        path=COOKIE_PATH,
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )
