"""Clarity MCP handlers."""

from .resources import (
    WIDGET_URI,
    WIDGET_HTML,
    WIDGET_VERSION,
    list_resources,
    list_resource_templates,
    handle_read_resource,
    embedded_widget_resource,
)
from .tools import call_tool_request

__all__ = [
    "WIDGET_URI",
    "WIDGET_HTML",
    "WIDGET_VERSION",
    "list_resources",
    "list_resource_templates",
    "handle_read_resource",
    "embedded_widget_resource",
    "call_tool_request",
]
