# (duplicate) — exists because it imports platform-specific config.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Logic mirrors mcp_server/priority_guardian/handlers/resources.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

"""
Resource handlers for Priority Guardian Claude MCP.

Handles widget resource discovery and serving.
Uses MCP Apps standard: ui:// URI scheme, text/html+mcp MIME type.
"""

import hashlib
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian_claude.config import MCP_RESOURCE_URL, MCP_SERVER_URL

logger = structlog.get_logger(__name__)


# ==========================================================================
# URI Sanitization for Logging (inc_99)
# ============================================================================

# Maximum URI length to log — prevents pathological inputs from bloating logs
_MAX_URI_LOG_LENGTH = 512


# inc_101: Allowlist of schemes safe to log with path/components.
# Everything else is redacted. Closes the class — no more whack-a-mole.
_SAFE_SCHEMES = frozenset({"http", "https", "ui", "file"})


def _sanitize_uri_for_logging(uri: str) -> str:
    """
    Sanitize URI for safe logging.

    inc_99: Defensive hygiene against pathological URIs from authenticated clients.
    inc_100: Strip query/fragment for all URIs, strip userinfo from netloc.
    inc_101: Switched from blocklist to allowlist. Only http/https/ui/file pass
             through with components; all other schemes (mailto:, blob:, data:,
             javascript:, etc.) are redacted. Closes the class of PII leaks.

    Args:
        uri: Raw URI string from request

    Returns:
        Sanitized URI safe for production logs
    """
    if not uri:
        return "[empty]"

    try:
        parsed = urlparse(uri)

        # inc_101: Allowlist approach — only known-safe schemes pass through
        # Everything else (mailto:, blob:, data:, javascript:, etc.) redacted
        if parsed.scheme and parsed.scheme not in _SAFE_SCHEMES:
            return f"{parsed.scheme}:[redacted]"

        # Build sanitized netloc: hostname + port only (strips userinfo)
        # parsed.netloc includes userinfo; parsed.hostname excludes it
        if parsed.hostname:
            sanitized_netloc = parsed.hostname
            if parsed.port:
                sanitized_netloc += f":{parsed.port}"
        else:
            sanitized_netloc = ""

        # Always reconstruct from components — NEVER fall back to raw uri
        # This ensures query/fragment are stripped even for non-netloc URIs
        if sanitized_netloc:
            clean_uri = f"{parsed.scheme}://{sanitized_netloc}{parsed.path}"
        elif parsed.scheme:
            # Scheme but no netloc (e.g., ui:widget/path or file:///path)
            clean_uri = f"{parsed.scheme}:{parsed.path}"
        elif parsed.path:
            # No scheme, just path (e.g., /path?token=x)
            clean_uri = parsed.path
        else:
            # Unparseable — return safe placeholder
            clean_uri = "[unparseable]"

    except Exception:
        # If parsing fails completely, return safe placeholder (not raw uri!)
        clean_uri = "[parse-error]"

    # Cap length
    if len(clean_uri) > _MAX_URI_LOG_LENGTH:
        return clean_uri[:_MAX_URI_LOG_LENGTH] + "...[truncated]"
    return clean_uri


# Ported VERBATIM from mcp_server/priority_guardian/handlers/resources.py (F1,
# 2026-08-09). It was absent here while this file's header claimed the file existed
# 'only because it imports platform-specific config'. Four call sites logged or
# reflected str(req.params.uri) raw — client-controlled input. Copied rather than
# reimplemented: it was hardened across inc_99/100/101 and reimplementing risks
# dropping a case someone already found. See DUPL_DIVERGENCE_SWEEP_2026-08-09.md F1.


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    MCP Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://pg-mcp-claude.priority-guard.com (not https://pg-mcp-claude.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
WIDGET_VERSION = "10"
WIDGET_MIME_TYPE = "text/html+mcp"  # MCP Apps standard
WIDGET_URI = "ui://pg-claude/dashboard-v10.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/pg-dashboard-claude.html")
WIDGET_DOMAIN = _extract_origin(MCP_SERVER_URL)

# Fallback HTML if widget file cannot be loaded
WIDGET_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>Priority Guardian</title></head>
<body style="font-family: system-ui; padding: 20px; text-align: center;">
<p style="color: #dc2626;">Widget failed to load. Please try again later.</p>
</body></html>"""


def _load_widget_html() -> str:
    """Load widget HTML with error handling."""
    try:
        return WIDGET_PATH.read_text()
    except FileNotFoundError:
        logger.error("widget.load.file_not_found", path=str(WIDGET_PATH))
        return WIDGET_FALLBACK_HTML
    except PermissionError:
        logger.error("widget.load.permission_denied", path=str(WIDGET_PATH))
        return WIDGET_FALLBACK_HTML
    except Exception as e:
        logger.error("widget.load.unexpected_error", path=str(WIDGET_PATH), error=str(e))
        return WIDGET_FALLBACK_HTML


# Load widget HTML at module import time
WIDGET_HTML = _load_widget_html()

# Claude app domain — SHA-256 of MCP resource URL (full /mcp endpoint, first 32 hex chars)
# Per Anthropic docs: hash the full server URL including /mcp path.
# Formula: sha256(MCP_RESOURCE_URL)[:32].claudemcpcontent.com
# Reference: https://docs.anthropic.com/en/docs/claude-ai-connectors/building/mcp-apps/cross-compatibility
_hash = hashlib.sha256(MCP_RESOURCE_URL.encode()).hexdigest()[:32]
WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com"


async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
    logger.info("resource.list.called")
    return [
        mcp_types.Resource(
            name="pg_dashboard_widget",
            title="Priority Guardian Dashboard",
            uri=WIDGET_URI,
            description="Widget for viewing priorities and Google Calendar time tracking",
            mimeType="text/html+mcp",  # MCP Apps standard MIME type
            _meta={
                "ui": {
                    "domain": WIDGET_APP_DOMAIN,
                    "prefersBorder": False,
                    "csp": {
                        "connectDomains": [],  # Widget uses postMessage, not HTTP
                        "resourceDomains": ["https://assets.claude.ai"],  # Host font loading
                    },
                },
            },
        )
    ]


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates (widget templates) for discovery."""
    logger.info("resource.list_templates.called")
    return [
        mcp_types.ResourceTemplate(
            name="Priority Guardian Dashboard",
            title="Priority Guardian Dashboard",
            uriTemplate=WIDGET_URI,
            description="Widget for viewing priorities and Google Calendar time tracking",
            mimeType="text/html+mcp",
            _meta={
                "ui": {
                    "domain": WIDGET_APP_DOMAIN,
                    "prefersBorder": False,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": ["https://assets.claude.ai"],
                    },
                },
            },
        )
    ]


async def handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    """
    Handle resource read requests.

    Called by Claude to load widget HTML for display.
    """
    uri_str = str(req.params.uri)
    safe_uri = _sanitize_uri_for_logging(uri_str)
    logger.info("resource.read.called", uri=safe_uri)

    logger.debug("resource.read.requested", uri=safe_uri, widget_version=WIDGET_VERSION)

    if uri_str == WIDGET_URI:
        logger.debug(
            "resource.read.serving_widget",
            uri=safe_uri,
            html_length=len(WIDGET_HTML),
            widget_version=WIDGET_VERSION,
        )

        # Build _meta for the widget resource
        resource_meta = {
            "ui": {
                "domain": WIDGET_APP_DOMAIN,
                "prefersBorder": False,
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": ["https://assets.claude.ai"],
                },
            },
        }

        contents = [
            mcp_types.TextResourceContents(
                uri=WIDGET_URI,
                mimeType="text/html+mcp",
                text=WIDGET_HTML,
                _meta=resource_meta,
            )
        ]
        return mcp_types.ReadResourceResult(contents=contents)

    # Unknown resource
    return mcp_types.ReadResourceResult(
        contents=[],
        # safe_uri, not uri_str: this one is REFLECTED BACK TO THE CLIENT, not just
        # logged. Raw client input echoed into a response body is a wider exposure
        # than a log line, and the source sanitises it here too.
        _meta={"error": f"Unknown resource: {safe_uri}"},
    )
