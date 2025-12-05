"""
HTML rendering utilities for OAuth flows.

This module provides user-facing HTML pages for OAuth success and error states.
All HTML escaping happens here. No business logic.
"""

import html

from fastapi.responses import HTMLResponse


def render_error(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    """
    Return HTML error page for user-facing OAuth errors.

    Simple HTML page that displays the error to the user.
    Per Increment 11: HTML errors for browser redirect flow.

    Args:
        title: Error title (e.g., "Authorization Failed")
        message: User-friendly error message
        status_code: HTTP status code (default 400)

    Returns:
        HTMLResponse with error page
    """
    # Escape to prevent XSS if any future code passes user input
    safe_title = html.escape(title)
    safe_message = html.escape(message)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{safe_title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px; text-align: center; }}
        h1 {{ color: #dc3545; }}
        p {{ color: #666; max-width: 400px; margin: 20px auto; }}
    </style>
</head>
<body>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <p><small>You can close this window and try again.</small></p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status_code)


def render_success() -> HTMLResponse:
    """
    Return HTML success page after OAuth completes.

    Returns:
        HTMLResponse with success page
    """
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Connected Successfully</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px; text-align: center; }
        h1 { color: #28a745; }
        p { color: #666; max-width: 400px; margin: 20px auto; }
    </style>
</head>
<body>
    <h1>Connected Successfully</h1>
    <p>Your Google Calendar has been connected. You can close this window.</p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)
