#!/usr/bin/env python3
"""
Focused MCP Server - Thin wrapper around backend REST API.

This MCP server forwards tool calls to the backend HTTP API.
No business logic, database access, or Google API calls happen here.

Usage:
    python -m mcp.focused.server

Or:
    python mcp/focused/server.py
"""

import json
import logging
import uvicorn
import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Create FastMCP instance
mcp = FastMCP("focused-mcp")

# Shared HTTP client for calling backend API
http_client: httpx.AsyncClient | None = None

# Backend URL (hardcoded for now, could come from config)
BACKEND_URL = "http://localhost:8000"


async def backend_post(path: str, json_data: dict) -> dict:
    """
    Send a POST request to the backend API.

    Args:
        path: API path (e.g., "/api/focused/check_calendar")
        json_data: Request payload

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    url = f"{BACKEND_URL}{path}"
    logger.info(f"Calling backend API: {url}")

    resp = await http_client.post(url, json=json_data)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
async def check_calendar(
    time_start: str | None = None,
    time_end: str | None = None,
    max_results: int = 20
) -> str:
    """
    Identify focus blocks in Google Calendar.

    Keywords are determined by the backend from:
    - System default keywords (e.g., "focus", "deep work")
    - User's custom keywords stored in the database

    This is a thin MCP wrapper that forwards the request to the backend API.

    Args:
        time_start: Start time (ISO8601), defaults to now
        time_end: End time (ISO8601), defaults to now + 7 days
        max_results: Max events to scan (1-50), defaults to 20

    Returns:
        JSON string with success status and data/error
    """
    logger.info(f"MCP check_calendar called for max_results={max_results}")

    try:
        # Forward request to backend API
        # Backend determines user_id and keywords internally
        response = await backend_post(
            "/api/focused/check_calendar",
            {
                "time_start": time_start,
                "time_end": time_end,
                "max_results": max_results
            }
        )

        # Backend already returns {success: bool, data/error: ...}
        # Just return it as JSON string
        return json.dumps(response)

    except httpx.HTTPStatusError as e:
        # Backend returned an error status
        logger.error(f"Backend API error: {e.response.status_code} - {e.response.text}")

        try:
            error_data = e.response.json()
            return json.dumps(error_data)
        except Exception:
            return json.dumps({
                "success": False,
                "error": {
                    "code": "BACKEND_ERROR",
                    "message": f"Backend API returned {e.response.status_code}"
                }
            })

    except Exception as e:
        # Unexpected error (network, etc.)
        logger.error(f"MCP server error: {e}")

        return json.dumps({
            "success": False,
            "error": {
                "code": "MCP_ERROR",
                "message": "Failed to communicate with backend API"
            }
        })


if __name__ == "__main__":
    # Initialize HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)

    logger.info("Starting Focused MCP server on http://0.0.0.0:8001/mcp")

    # Get FastMCP streamable HTTP app
    app = mcp.streamable_http_app()

    # Run with uvicorn on port 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)
