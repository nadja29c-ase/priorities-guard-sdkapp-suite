# (duplicate) — exists because it imports platform-specific config.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Mirrors mcp_server/clarity/handlers/resources.py (OpenAI) and
# mcp_server/priority_guardian_claude/handlers/resources_dupl.py (Claude pattern).
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

"""
Resource handlers for MindSort Claude MCP.

Handles widget resource discovery and serving.
Uses MCP Apps standard: ui:// URI scheme.

MIME type note: The installed SDK (@modelcontextprotocol/ext-apps) declares
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app". PG's shipped resources_dupl.py
uses "text/html+mcp" and PG's tests assert that value. This file uses the SDK
value by default. If empirical host testing proves a different MIME is required,
update with evidence. See inc_03_widget0.md "MIME type" section.
"""

import hashlib
from pathlib import Path
from typing import List

import structlog
from mcp import types as mcp_types

from mcp_server.mindsort_claude.config import MCP_RESOURCE_URL

logger = structlog.get_logger(__name__)


# ============================================================================
# Widget Configuration — Single Production Definition
# ============================================================================
# CRITICAL: This is the SINGLE production definition of the Claude widget URI.
# Every production consumer (this module's handlers AND tools_list_dupl.py)
# must import WIDGET_URI from here. Do not duplicate this string elsewhere.
# See OPERATIONS_PREDEPLOY "Widget Bundle Changes" and ADR "Widget URI Consistency".

WIDGET_VERSION = "9"
WIDGET_URI = f"ui://mindsort-claude/dashboard-v{WIDGET_VERSION}.html"

# MIME type: SDK declares "text/html;profile=mcp-app", PG ships "text/html+mcp"
# Using SDK value by default. If host empirically requires +mcp, update with evidence.
WIDGET_MIME_TYPE = "text/html;profile=mcp-app"

WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/mindsort-dashboard-claude.html")

# Fallback HTML if widget file cannot be loaded
WIDGET_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>MindSort</title></head>
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


# ============================================================================
# ui.domain — SHA-256 hash of MCP_RESOURCE_URL (mandatory per §4K)
# ============================================================================
# Formula: sha256(MCP_RESOURCE_URL)[:32].claudemcpcontent.com
# MCP_RESOURCE_URL includes /mcp path (e.g., https://mindsort-claude.../mcp).
# Reference: compliance master §4K, structural guideline §5.
#
# NOTE: PG's resources_dupl.py also has a dead _extract_origin/WIDGET_DOMAIN pair
# that computes origin-only. We deliberately do NOT copy that — it's unused and
# origin-only is wrong for Claude (structural §5). Only the hash form is correct.

_hash = hashlib.sha256(MCP_RESOURCE_URL.encode()).hexdigest()[:32]
WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com"


# ============================================================================
# Resource Handlers
# ============================================================================

async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
    logger.info("resource.list.called")
    return [
        mcp_types.Resource(
            name="mindsort_dashboard_widget",
            title="MindSort Dashboard",
            uri=WIDGET_URI,
            description="Widget for viewing and prioritizing thoughts",
            mimeType=WIDGET_MIME_TYPE,
            _meta={
                "ui": {
                    "domain": WIDGET_APP_DOMAIN,
                    "prefersBorder": False,
                    "csp": {
                        # Widget uses postMessage via ext-apps bridge, not direct HTTP
                        "connectDomains": [],
                        # Host font loading per §4N ("optional but expected")
                        "resourceDomains": ["https://assets.claude.ai"],
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
            name="MindSort Dashboard",
            title="MindSort Dashboard",
            uriTemplate=WIDGET_URI,
            description="Widget for viewing and prioritizing thoughts",
            mimeType=WIDGET_MIME_TYPE,
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
    logger.info("resource.read.called", uri=uri_str)

    logger.debug("resource.read.requested", uri=uri_str, widget_version=WIDGET_VERSION)

    if uri_str == WIDGET_URI:
        logger.debug(
            "resource.read.serving_widget",
            uri=uri_str,
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
                mimeType=WIDGET_MIME_TYPE,
                text=WIDGET_HTML,
                _meta=resource_meta,
            )
        ]
        return mcp_types.ReadResourceResult(contents=contents)

    # Unknown resource — return gracefully (empty contents + error _meta), don't raise
    logger.warning("resource.read.unknown_uri", uri=uri_str)
    return mcp_types.ReadResourceResult(
        contents=[],
        _meta={"error": f"Unknown resource: {uri_str}"},
    )
